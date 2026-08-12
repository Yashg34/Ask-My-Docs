import os
import sys
from dotenv import load_dotenv
from ingestion.parser import parse_pdf_slice
from ingestion.chunker import chunk_pages
from ingestion.indexer import build_indexes

load_dotenv()

def run_ingestion(pdf_path: str):
    print(f"📖 Parsing PDF: {pdf_path}...")
    pages = parse_pdf_slice(pdf_path)
    
    print(f"✂️ Chunking {len(pages)} pages...")
    chunks = chunk_pages(pages)
    print(f"Generated {len(chunks)} chunks.")

    build_indexes(chunks)
    print("✅ Entire ingestion pipeline completed successfully!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("⚠️ Usage: python -m ingestion.ingest <path_to_pdf>")
        sys.exit(1)
        
    pdf_file = sys.argv[1]
    
    if os.path.exists(pdf_file):
        run_ingestion(pdf_file)
    else:
        print(f"❌ File not found: {pdf_file}. Please check the path.")