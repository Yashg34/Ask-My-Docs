import json
import os
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import numpy as np
import redis.asyncio as aioredis
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from config import settings
from ingestion.chunker import chunk_pages
from ingestion.indexer import build_indexes
from ingestion.parser import parse_pdf_slice
from observability import instrument_fastapi, setup_langsmith, setup_logfire
from events import (
    clear_query_events,
    latest_query_event,
    mark_query_done,
    register_query_events,
)
import queue as _queue

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_DIR = Path("data")
JOB_TTL_SECONDS = 86400

graph_app = None
redis_client: Optional[aioredis.Redis] = None


# ── App lifecycle ────────────────────────────────────────────────────────────

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
    if redis_client is not None:
        try:
            await redis_client.close()
            print("✅ Redis connection closed.")
        except Exception as e:
            print(f"⚠️ Error closing Redis: {e}")


app = FastAPI(title="Ask My Docs", lifespan=lifespan)

_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=("*" not in _origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error handling ───────────────────────────────────────────────────────────

def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": status_code, "message": message}},
    )


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


# ── Schemas ──────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    top_k: int = 15      # First-stage retrieval (wide fetch from Qdrant, narrowed by FlashRank)
    top_n: int = 5       # Post-reranking (sends the top-N best chunks to Gemini)
    threshold: float = 0.05
    chat_history: List[dict] = Field(default_factory=list)
    query_id: Optional[str] = None  # correlates this request with /query/events/{query_id} SSE progress


class QueryResponse(BaseModel):
    query: str
    answer: str
    latency_seconds: float
    retrieved_chunks: list


class ConfigUpdate(BaseModel):
    TOP_K_RETRIEVAL: Optional[int] = None
    TOP_K_RERANK: Optional[int] = None
    CHUNK_SIZE: Optional[int] = None
    CHUNK_OVERLAP: Optional[int] = None
    GUARDRAIL_FAIL_MODE: Optional[str] = None


# ── Job store (Redis, with in-memory fallback) ───────────────────────────────

_job_store: dict[str, str] = {}
_REDIS_AVAILABLE: Optional[bool] = None   # None = unknown, True/False after first probe
_LAST_REDIS_PROBE = 0.0                   # monotonic timestamp of the last probe
_REDIS_REPROBE_SECONDS = 30               # re-check a down Redis this often


async def get_redis_client() -> aioredis.Redis:
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


async def set_job(job_id: str, data: dict) -> None:
    payload = json.dumps(data)
    if await _redis_up():
        try:
            await (await get_redis_client()).set(f"job:{job_id}", payload, ex=JOB_TTL_SECONDS)
            return
        except Exception as e:
            print(f"⚠️ Redis set failed ({e}); falling back to memory for job {job_id}")
    _job_store[job_id] = payload


async def get_job(job_id: str) -> Optional[dict]:
    if await _redis_up():
        try:
            raw = await (await get_redis_client()).get(f"job:{job_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            print(f"⚠️ Redis get failed ({e}); checking memory for job {job_id}")
    raw = _job_store.get(job_id)
    return json.loads(raw) if raw else None


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "Ask My Docs pipeline running smoothly"}


# ── Soft-config endpoints (runtime, no restart) ──────────────────────────────
# Whitelisted knobs, validated then live-assigned to `settings`; nodes read them
# at call time. Guarded by ADMIN_API_TOKEN (X-Admin-Token header) when set.

_RUNTIME_KNOBS = {
    "TOP_K_RETRIEVAL": ("int", 1, 100),
    "TOP_K_RERANK": ("int", 1, 50),
    "CHUNK_SIZE": ("int", 64, 4096),
    "CHUNK_OVERLAP": ("int", 0, 1024),
    "GUARDRAIL_FAIL_MODE": ("enum", ["closed", "open"]),
}


def _config_view() -> dict:
    return {
        "TOP_K_RETRIEVAL": settings.TOP_K_RETRIEVAL,
        "TOP_K_RERANK": settings.TOP_K_RERANK,
        "CHUNK_SIZE": settings.CHUNK_SIZE,
        "CHUNK_OVERLAP": settings.CHUNK_OVERLAP,
        "GUARDRAIL_FAIL_MODE": settings.GUARDRAIL_FAIL_MODE,
        "QDRANT_COLLECTION_NAME": settings.QDRANT_COLLECTION_NAME,
        "ENV": settings.ENV,
    }


def _require_admin(request: Request) -> None:
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
        kind, *bounds = _RUNTIME_KNOBS[field]
        if kind == "int":
            lo, hi = bounds
            if not (lo <= value <= hi):
                raise HTTPException(status_code=422, detail=f"{field} must be between {lo} and {hi}")
        elif kind == "enum" and value not in bounds[0]:
            raise HTTPException(status_code=422, detail=f"{field} must be one of {bounds[0]}")
        setattr(settings, field, value)
        applied[field] = value
    print(f"⚙️ Soft-config updated: {applied}")
    return {"applied": applied, "config": _config_view()}


# ── Ingestion ────────────────────────────────────────────────────────────────

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
            document_name=original_filename,
        )
        if not chunks:
            raise ValueError("No extractable text found. This PDF may be scanned or image-only.")

        build_indexes(chunks)

        elapsed = round(time.time() - start_time, 2)
        print(f"✅ Successfully ingested '{original_filename}' in {elapsed}s!")
        return {"status": "COMPLETED", "message": f"Successfully ingested in {elapsed}s"}
    except Exception as e:
        print(f"❌ Ingestion pipeline failed for {original_filename}: {e}")
        traceback.print_exc()
        return {"status": "FAILED", "errorMessage": str(e)}
    finally:
        try:
            os.remove(file_path)
        except OSError as rm_err:
            print(f"⚠️ Could not remove temp file {file_path}: {rm_err}")


async def process_ingestion(file_path: str, user_id: str, document_id: str, original_filename: str, job_id: str):
    """Background driver for POST /ingest: offloads the blocking work to a
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


def _save_upload(file: UploadFile, destination: Path) -> None:
    """Stream the upload to disk, enforcing the size cap as we go."""
    size = 0
    try:
        with open(destination, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File too large. Maximum size is 20MB.")
                buffer.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as e:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


@app.post("/ingest")
async def upload_and_ingest(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_id: str = Form(...),
    x_user_id: str = Header(...),
):
    safe_name = Path(file.filename).name
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    magic_bytes = file.file.read(4)
    file.file.seek(0)
    if magic_bytes != b"%PDF":
        raise HTTPException(status_code=400, detail="Invalid file format. Not a true PDF.")

    job_id = uuid.uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / f"{job_id}_{safe_name}"
    _save_upload(file, file_path)

    await set_job(job_id, {"status": "PROCESSING", "message": "Ingestion started..."})
    background_tasks.add_task(
        process_ingestion,
        file_path=str(file_path),
        user_id=x_user_id,
        document_id=document_id,
        original_filename=safe_name,
        job_id=job_id,
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Ingestion for '{safe_name}' has been queued.",
    }


@app.get("/ingest/status/{job_id}")
async def get_ingest_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── Query ────────────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest, x_user_id: str = Header(...)):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if graph_app is None:
        raise HTTPException(status_code=503, detail="AI models are still loading, please try again in a moment.")

    query_id = request.query_id or ""
    start_time = time.time()
    initial_state = {
        "query": request.query,
        "user_id": x_user_id,
        "document_id": request.document_id,
        "chat_history": request.chat_history,
        "top_k": request.top_k,
        "top_n": request.top_n,
        "threshold": request.threshold,
        "revision_count": 0,
        "query_id": query_id,
    }

    try:
        final_state = await graph_app.ainvoke(initial_state)
    except Exception as e:
        mark_query_done(query_id, message=f"Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Give a slow SSE subscriber a moment to read the final event before the
        # queue disappears; the generator already holds its own queue reference,
        # so this is a memory-cleanup safeguard, not a correctness requirement.
        mark_query_done(query_id)
        clear_query_events(query_id)

    return QueryResponse(
        query=request.query,
        answer=_json_safe(final_state.get("draft_answer", "No answer generated.")),
        latency_seconds=round(time.time() - start_time, 2),
        retrieved_chunks=_json_safe(final_state.get("retrieved_chunks", [])),
    )


@app.get("/query/events/{query_id}")
async def stream_query_events(query_id: str):
    """SSE progress stream for a query in flight. The frontend opens this
    *before or alongside* POSTing to /query, using the same query_id for both.
    register_query_events() is idempotent, so it doesn't matter which of the
    two requests (this one, or the POST handler via the graph's node spans)
    reaches the shared queue first."""

    async def event_generator():
        q = register_query_events(query_id)

        # Late-connect fallback: if the POST request already progressed past
        # some stages before this SSE connection opened, immediately replay
        # the most recent known stage so the UI isn't stuck on "Starting...".
        cached = latest_query_event(query_id)
        if cached:
            yield f"data: {json.dumps(cached)}\n\n"
            if cached.get("stage") == "done":
                return

        deadline = time.time() + 600  # hard cap: never stream longer than 10 minutes
        while time.time() < deadline:
            try:
                event = await run_in_threadpool(q.get, True, 15)  # blocking get, 15s timeout
            except _queue.Empty:
                yield ": keepalive\n\n"  # SSE comment, ignored by EventSource, keeps proxies from closing idle conns
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("stage") == "done":
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    x_user_id: str = Header(...),
):
    try:
        from qdrant_client import models
        from retrieval.vector_store import get_qdrant_client

        result = get_qdrant_client().delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(
                                value=document_id
                            ),
                        ),
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(
                                value=x_user_id
                            ),
                        ),
                    ]
                )
            ),
        )

        print(
            f"🗑️ Deleted vectors for document "
            f"{document_id} belonging to user {x_user_id}"
        )

        return {
            "message": "Document vectors deleted successfully",
            "document_id": document_id,
        }

    except Exception as e:
        print(
            f"❌ Failed to delete vectors for "
            f"document {document_id}: {e}"
        )
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Failed to delete document vectors",
        )
    
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.ENV == "development")