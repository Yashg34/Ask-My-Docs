import os
import shutil
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

from ingestion.parser import parse_pdf_slice
from ingestion.chunker import chunk_pages
from ingestion.indexer import build_indexes

load_dotenv()

graph_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph_app
    print("🚀 Starting worker process: Initializing AI Components...")
    
    from graph.build_graph import app as compiled_graph
    graph_app = compiled_graph
    
    print("✅ All components loaded successfully!")
    yield 
    print("🛑 Shutting down AI components...")

# Pass the lifespan context manager to FastAPI
app = FastAPI(title="Ask My Docs - Phase 3 (Agentic RAG)", lifespan=lifespan)

class QueryRequest(BaseModel):
    query: str
    document_id: str = None
    top_k: int = 10      # First-stage retrieval (Pulls 10 from Vector, 10 from BM25)
    top_n: int = 3       # Post-reranking (Sends only the top 3 best chunks to Gemini)
    threshold: float = 0.05
    chat_history: list = []

class QueryResponse(BaseModel):
    query: str
    answer: str
    latency_seconds: float
    retrieved_chunks: list

job_store = {}

@app.get("/health")
def health():
    return {"status": "Phase 3 LangGraph Pipeline running smoothly"}

def process_ingestion(file_path: str, user_id: str, document_id: str, original_filename: str, job_id: str):
    try:
        print(f"🔄 Starting background ingestion for {original_filename}...")
        start_time = time.time()
        pages = parse_pdf_slice(file_path)
        
        chunks = chunk_pages(
            pages=pages, 
            user_id=user_id, 
            document_id=document_id,
            document_name=original_filename 
        )
        
        build_indexes(chunks)
        
        import nodes.retriever_node as retriever_node
        from retrieval.bm25_retriever import BM25Retriever
        retriever_node.bm25_retriever = BM25Retriever()

        end_time = time.time()
        print(f"✅ Successfully ingested '{original_filename}' in {round(end_time - start_time, 2)}s!")
        job_store[job_id] = {"status": "COMPLETED", "message": f"Successfully ingested in {round(end_time - start_time, 2)}s"}
    except Exception as e:
        print(f"❌ Ingestion pipeline failed for {original_filename}: {str(e)}")
        job_store[job_id] = {"status": "FAILED", "errorMessage": str(e)}
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.get("/ingest/status/{job_id}")
def get_ingest_status(job_id: str):
    job = job_store.get(job_id)
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
    job_store[job_id] = {"status": "PROCESSING", "message": "Ingestion started..."}
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", f"{job_id}_{safe_name}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
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
            answer=final_state.get("draft_answer", "No answer generated."),
            latency_seconds=round(end_time - start_time, 2),
            retrieved_chunks=final_state.get("retrieved_chunks", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)