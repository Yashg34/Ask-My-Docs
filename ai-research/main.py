import os
import shutil
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from dotenv import load_dotenv

from retrieval.vector_retriever import VectorRetriever
from generation.generator import Generator
from ingestion.ingest import run_ingestion

load_dotenv()

app = FastAPI(title="Ask My Docs - Phase 1 MVP")

retriever = VectorRetriever()
generator = Generator()

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class QueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_chunks: list


@app.get("/health")
def health():
    return "App running smoothly"


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
        run_ingestion(file_path)
        return {"message": f"✅ Successfully ingested '{file.filename}' into master_docs!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline failed: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/query", response_model=QueryResponse)
def handle_query(request: QueryRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        # Step 1: Retrieve Chunks across ALL ingested documents
        chunks = retriever.retrieve(request.query, top_k=request.top_k)
        
        # Step 2: Generate Answer with Citations via LangChain
        answer = generator.generate_answer(request.query, chunks)

        return QueryResponse(
            query=request.query,
            answer=answer,
            retrieved_chunks=chunks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)