import os
import shutil
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv

from retrieval.vector_retriever import VectorRetriever
from retrieval.bm25_retriever import BM25Retriever
from retrieval.fusion import reciprocal_rank_fusion
from retrieval.reranker import CrossEncoderReranker
from generation.generator import Generator
from ingestion.parser import parse_pdf_slice
from ingestion.chunker import chunk_pages
from ingestion.indexer import build_indexes

load_dotenv()

vector_retriever = None
bm25_retriever = None
reranker = None
generator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global vector_retriever, bm25_retriever, reranker, generator
    
    print("🚀 Initializing AI Components (Loading models into memory)...")
    vector_retriever = VectorRetriever()
    bm25_retriever = BM25Retriever()
    reranker = CrossEncoderReranker()
    generator = Generator()
    print("✅ All components loaded successfully!")
    
    yield  
    
    print("🛑 Shutting down AI components...")

app = FastAPI(title="Ask My Docs - Phase 2 (Hybrid & Rerank)", lifespan=lifespan)

class QueryRequest(BaseModel):
    query: str
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
    return {"status": "Phase 2 Pipeline running smoothly"}

@app.post("/ingest")
def upload_and_ingest(file: UploadFile = File(...)):
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
        chunks = chunk_pages(pages)
        
        build_indexes(chunks)
        
        # This will dynamically reload the BM25 index after new ingestion
        global bm25_retriever
        bm25_retriever = BM25Retriever()
        
        return {"message": f"✅ Successfully ingested '{file.filename}' into Vector & BM25 Indexes!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline failed: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/query", response_model=QueryResponse)
def handle_query(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    start_time = time.time()

    try:
        # Step 1: Retrieval
        vector_results = vector_retriever.retrieve(request.query, top_k=request.top_k)
        bm25_results = bm25_retriever.retrieve(request.query, top_k=request.top_k)

        # Step 2: Fusion
        fused_candidates = reciprocal_rank_fusion(vector_results, bm25_results)

        # Step 3: Reranking
        final_chunks = reranker.rerank(
            query=request.query, 
            candidates=fused_candidates, 
            top_n=request.top_n, 
            threshold=request.threshold
        )

        end_time = time.time()

        # Step 4: Generation
        answer = generator.generate_answer(request.query, final_chunks)

        return QueryResponse(
            query=request.query,
            answer=answer,
            latency_seconds=round(end_time - start_time, 2),
            retrieved_chunks=final_chunks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)