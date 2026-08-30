import os
import shutil
import time
import traceback
import uuid
import numpy as np
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from starlette.concurrency import run_in_threadpool

from config import settings
from ingestion.parser import parse_pdf_slice
from ingestion.chunker import chunk_pages
from ingestion.indexer import build_indexes
from observability import setup_logfire, instrument_fastapi, setup_langsmith

graph_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    print("🚀 Starting worker process: Initializing AI Components...")

    setup_langsmith()
    if setup_logfire():
        instrument_fastapi(app)

    from graph.build_graph import app as compiled_graph
    graph_app = compiled_graph

    print("✅ All components loaded successfully!")
    yield
    print("🛑 Shutting down AI components...")
    try:
        client = await get_redis_client()
        await client.close()
        print("✅ Redis connection closed.")
    except Exception as e:
        print(f"⚠️ Error closing Redis: {e}")

# Pass the lifespan context manager to FastAPI
app = FastAPI(title="Ask My Docs", lifespan=lifespan)

_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=("*" not in _origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

def _error_response(status_code: int, message: str):
    return JSONResponse(status_code=status_code, content={"error": {"code": status_code, "message": message}})


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", [])) or "body"
    return _error_response(422, f"Invalid value for '{loc}': {first.get('msg', 'validation error')}")


@app.exception_handler(HTTPException)
async def _http_error_handler(request: Request, exc: HTTPException):
    return _error_response(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
async def _unhandled_error_handler(request: Request, exc: Exception):
    print(f"❌ Unhandled {type(exc).__name__} on {request.method} {request.url.path}: {exc}")
    traceback.print_exc()
    return _error_response(500, "Internal server error")

def _json_safe(value):
    """Recursively coerce numpy scalars to native Python so Pydantic/JSON
    serialization never trips on np.float32 etc. (e.g. FlashRank rerank scores)."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


class QueryRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    top_k: int = 15      # First-stage retrieval (wide fetch from Qdrant, narrowed by FlashRank)
    top_n: int = 5       # Post-reranking (sends the top-N best chunks to Gemini; default matches backend/README)
    threshold: float = 0.05
    chat_history: List[dict] = Field(default_factory=list)

class QueryResponse(BaseModel):
    query: str
    answer: str
    latency_seconds: float
    retrieved_chunks: list

import json
import redis.asyncio as aioredis

redis_client = None
_job_store = {}
_REDIS_AVAILABLE = None  # None = unknown, True/False after first probe
_LAST_REDIS_PROBE = 0.0  # monotonic timestamp of the last probe
_REDIS_REPROBE_SECONDS = 30  # re-check a down Redis this often (e.g. once Docker tries it)

async def get_redis_client():
    global redis_client
    if redis_client is None:
        # Short timeouts so a down/hung Redis never holds up a request.
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return redis_client

async def _redis_up() -> bool:
    """Probe Redis without blocking; re-probe a down Redis every 30s so a
    container started after the app is picked up without a restart."""
    global _REDIS_AVAILABLE, _LAST_REDIS_PROBE
    now = time.monotonic()
    if _REDIS_AVAILABLE is True:
        return True
    if _REDIS_AVAILABLE is False and (now - _LAST_REDIS_PROBE) < _REDIS_REPROBE_SECONDS:
        return False
    try:
        await (await get_redis_client()).ping()
        if _REDIS_AVAILABLE is not True:
            print("✅ Redis connected — using Redis job store")
        _REDIS_AVAILABLE = True
    except Exception as e:
        if _REDIS_AVAILABLE is not False:
            print(f"⚠️ Redis unreachable ({e}) — using in-memory job store (single-process only)")
        _REDIS_AVAILABLE = False
    _LAST_REDIS_PROBE = now
    return _REDIS_AVAILABLE

async def set_job(job_id: str, data: dict):
    payload = json.dumps(data)
    if await _redis_up():
        try:
            await (await get_redis_client()).set(f"job:{job_id}", payload, ex=86400)
            return
        except Exception as e:
            print(f"⚠️ Redis set failed ({e}); falling back to memory for job {job_id}")
    _job_store[job_id] = payload

async def get_job(job_id: str):
    if await _redis_up():
        try:
            raw = await (await get_redis_client()).get(f"job:{job_id}")
            return json.loads(raw) if raw else None
        except Exception as e:
            print(f"⚠️ Redis get failed ({e}); checking memory for job {job_id}")
    raw = _job_store.get(job_id)
    return json.loads(raw) if raw else None

@app.get("/health")
def health():
    return {"status": "Ask My Docs pipeline running smoothly"}


# ============ Soft-config endpoints (runtime, no restart) ============
# Whitelisted knobs, validated then live-assigned to `settings`; nodes read them
# at call time. Guarded by ADMIN_API_TOKEN (X-Admin-Token header) when set.
_RUNTIME_KNOBS = {
    "TOP_K_RETRIEVAL": ("int", 1, 100),
    "TOP_K_RERANK": ("int", 1, 50),
    "CHUNK_SIZE": ("int", 64, 4096),
    "CHUNK_OVERLAP": ("int", 0, 1024),
    "GUARDRAIL_FAIL_MODE": ("enum", ["closed", "open"]),
    "USE_NEMO_GUARDRAILS": ("bool", None),
}

class ConfigUpdate(BaseModel):
    TOP_K_RETRIEVAL: int | None = None
    TOP_K_RERANK: int | None = None
    CHUNK_SIZE: int | None = None
    CHUNK_OVERLAP: int | None = None
    GUARDRAIL_FAIL_MODE: str | None = None
    USE_NEMO_GUARDRAILS: bool | None = None


def _config_view() -> dict:
    return {
        "TOP_K_RETRIEVAL": settings.TOP_K_RETRIEVAL,
        "TOP_K_RERANK": settings.TOP_K_RERANK,
        "CHUNK_SIZE": settings.CHUNK_SIZE,
        "CHUNK_OVERLAP": settings.CHUNK_OVERLAP,
        "GUARDRAIL_FAIL_MODE": settings.GUARDRAIL_FAIL_MODE,
        "USE_NEMO_GUARDRAILS": settings.USE_NEMO_GUARDRAILS,
        "QDRANT_COLLECTION_NAME": settings.QDRANT_COLLECTION_NAME,
        "ENV": settings.ENV,
    }


def _require_admin(request: Request):
    if settings.ADMIN_API_TOKEN and request.headers.get("X-Admin-Token") != settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


@app.get("/config")
async def get_config(request: Request):
    _require_admin(request)
    return _config_view()


@app.patch("/config")
async def patch_config(request: Request, updates: ConfigUpdate):
    _require_admin(request)
    applied = {}
    for field, value in updates.model_dump(exclude_none=True).items():
        kind = _RUNTIME_KNOBS[field][0]
        if kind == "int":
            lo, hi = _RUNTIME_KNOBS[field][1], _RUNTIME_KNOBS[field][2]
            if not (lo <= value <= hi):
                raise HTTPException(status_code=422, detail=f"{field} must be between {lo} and {hi}")
        elif kind == "enum" and value not in _RUNTIME_KNOBS[field][1]:
            raise HTTPException(status_code=422, detail=f"{field} must be one of {_RUNTIME_KNOBS[field][1]}")
        setattr(settings, field, value)
        applied[field] = value
    print(f"⚙️ Soft-config updated: {applied}")
    return {"applied": applied, "config": _config_view()}

def _run_ingestion_sync(file_path: str, user_id: str, document_id: str, original_filename: str) -> dict:
    """Blocking ingestion work (parse, chunk, embed, Qdrant write). Runs in a
    worker thread so it never freezes the event loop."""
    print(f"🔄 Starting background ingestion for {original_filename}...")
    start_time = time.time()
    try:
        pages = parse_pdf_slice(file_path)
        chunks = chunk_pages(
            pages=pages,
            user_id=user_id,
            document_id=document_id,
            document_name=original_filename
        )
        build_indexes(chunks)
        elapsed = round(time.time() - start_time, 2)
        print(f"✅ Successfully ingested '{original_filename}' in {elapsed}s!")
        return {"status": "COMPLETED", "message": f"Successfully ingested in {elapsed}s"}
    except Exception as e:
        print(f"❌ Ingestion pipeline failed for {original_filename}: {e}")
        traceback.print_exc()
        return {"status": "FAILED", "errorMessage": str(e)}
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as rm_err:
                print(f"⚠️ Could not remove temp file {file_path}: {rm_err}")


async def process_ingestion(file_path: str, user_id: str, document_id: str, original_filename: str, job_id: str):
    """Background driver for the /ingest POST: offloads the blocking work to a
    thread pool, then persists the job result (Redis or memory fallback)."""
    try:
        result = await run_in_threadpool(
            _run_ingestion_sync, file_path, user_id, document_id, original_filename
        )
    except Exception as e:
        print(f"❌ Ingestion driver failed for {original_filename}: {e}")
        traceback.print_exc()
        result = {"status": "FAILED", "errorMessage": f"Unexpected driver error: {e}"}
    try:
        await set_job(job_id, result)
    except Exception as e:
        print(f"⚠️ Could not persist job status for {job_id}: {e}")

@app.get("/ingest/status/{job_id}")
async def get_ingest_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/ingest")
async def upload_and_ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_id: str = Form(...),
    x_user_id: str = Header(...)
):
    user_id = x_user_id
    safe_name = Path(file.filename).name
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    magic_bytes = file.file.read(4)
    file.file.seek(0)
    if magic_bytes != b"%PDF":
        raise HTTPException(status_code=400, detail="Invalid file format. Not a true PDF.")
    
    job_id = uuid.uuid4().hex
    await set_job(job_id, {"status": "PROCESSING", "message": "Ingestion started..."})
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", f"{job_id}_{safe_name}")
    
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024
    size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    buffer.close()
                    os.remove(file_path)
                    raise HTTPException(status_code=413, detail="File too large. Maximum size is 20MB.")
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    background_tasks.add_task(
        process_ingestion, 
        file_path=file_path, 
        user_id=user_id, 
        document_id=document_id, 
        original_filename=file.filename,
        job_id=job_id
    )
    
    return {"job_id": job_id, "status": "queued", "message": f"Ingestion for '{file.filename}' has been queued."}

@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest, x_user_id: str = Header(...)):
    user_id = x_user_id
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if graph_app is None:
        raise HTTPException(status_code=503, detail="AI models are still loading, please try again in a moment.")

    start_time = time.time()

    try:
        initial_state = {
            "query": request.query,
            "user_id": user_id,
            "document_id": request.document_id,
            "chat_history": request.chat_history,
            "top_k": request.top_k,
            "top_n": request.top_n,
            "threshold": request.threshold,
            "revision_count": 0  
        }

        # Use the globally loaded graph_app
        final_state = await graph_app.ainvoke(initial_state)

        end_time = time.time()

        return QueryResponse(
            query=request.query,
            answer=_json_safe(final_state.get("draft_answer", "No answer generated.")),
            latency_seconds=round(end_time - start_time, 2),
            retrieved_chunks=_json_safe(final_state.get("retrieved_chunks", []))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.ENV == "development")