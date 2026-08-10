import sys
import os
import chromadb
from dotenv import load_dotenv
from ingestion.parser import parse_pdf_slice
from ingestion.chunker import chunk_pages
from ingestion.embedder import LocalEmbedder

load_dotenv()

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
MASTER_COLLECTION = "master_docs"

def run_ingestion(pdf_path: str):
    print(f"📖 Parsing PDF: {pdf_path}...")
    pages = parse_pdf_slice(pdf_path)
    
    print(f"✂️ Chunking {len(pages)} pages...")
    chunks = chunk_pages(pages)
    print(f"Generated {len(chunks)} chunks.")

    print("🧠 Generating local embeddings...")
    embedder = LocalEmbedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)

    print(f"💾 Storing in ChromaDB (Collection: '{MASTER_COLLECTION}')...")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Only one master collection will hold all data
    collection = client.get_or_create_collection(name=MASTER_COLLECTION)

    ids = [c["chunk_id"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas
    )
    print(f"✅ Successfully ingested {len(chunks)} chunks into '{MASTER_COLLECTION}'!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("⚠️ Usage: python -m ingestion.ingest <path_to_pdf>")
        sys.exit(1)
        
    pdf_file = sys.argv[1]
    
    if os.path.exists(pdf_file):
        run_ingestion(pdf_file)
    else:
        print(f"❌ File not found: {pdf_file}. Please check the path.")