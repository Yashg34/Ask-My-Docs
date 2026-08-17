import os
import shutil
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
    user_id: str         
    document_id: str = None
    top_k: int = 10      # First-stage retrieval (Pulls 10 from Vector, 10 from BM25)
    top_n: int = 3       # Post-reranking (Sends only the top 3 best chunks to Gemini)
    threshold: float = 0.05

class QueryResponse(BaseModel):
    query: str
    answer: str
    latency_seconds: float
    retrieved_chunks: list

@app.get("/health")
def health():
    return {"status": "Phase 3 LangGraph Pipeline running smoothly"}

@app.post("/ingest")
def upload_and_ingest(
    file: UploadFile = File(...),
    user_id: str = Form(...),      
    document_id: str = Form(...)   
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", file.filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
    try:
        pages = parse_pdf_slice(file_path)
        
        chunks = chunk_pages(
            pages=pages, 
            user_id=user_id, 
            document_id=document_id,
            document_name=file.filename 
        )
        
        build_indexes(chunks)
        
        import nodes.retriever_node as retriever_node
        from retrieval.bm25_retriever import BM25Retriever
        retriever_node.bm25_retriever = BM25Retriever()
        
        return {"message": f"✅ Successfully ingested '{file.filename}'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline failed: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/query", response_model=QueryResponse)
def handle_query(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if graph_app is None:
        raise HTTPException(status_code=503, detail="AI models are still loading, please try again in a moment.")

    start_time = time.time()

    try:
        initial_state = {
            "query": request.query,
            "user_id": request.user_id,
            "document_id": request.document_id,
            "top_k": request.top_k,
            "top_n": request.top_n,
            "threshold": request.threshold,
            "revision_count": 0  
        }

        # Use the globally loaded graph_app
        final_state = graph_app.invoke(initial_state)

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