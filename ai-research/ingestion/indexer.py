import os
import pickle
import chromadb
import concurrent.futures
from rank_bm25 import BM25Okapi
from ingestion.embedder import LocalEmbedder

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
MASTER_COLLECTION = "master_docs"
BM25_INDEX_PATH = os.path.join("data", "bm25_index.pkl")


def _update_vector_db(chunks):
    """Helper function to run Vector DB indexing."""
    print("[Vector DB] Generating local embeddings...")
    embedder = LocalEmbedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=MASTER_COLLECTION)

    ids = [c["chunk_id"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas
    )
    print("[Vector DB] Indexing complete!")


def _update_bm25_index(chunks):
    """Helper function to run BM25 indexing."""
    print("[BM25] Updating Keyword Index...")
    
    all_chunks = []
    if os.path.exists(BM25_INDEX_PATH):
        try:
            with open(BM25_INDEX_PATH, "rb") as f:
                existing_data = pickle.load(f)
                all_chunks = existing_data.get("chunks", [])
                print(f"🔄 [BM25] Loaded {len(all_chunks)} existing chunks.")
        except Exception as e:
            print(f"[BM25] Could not load existing index, starting fresh. Error: {e}")

    # Remove existing chunks for the incoming document IDs (Deduplication)
    incoming_doc_ids = {
        c["metadata"]["document_id"] 
        for c in chunks 
        if "metadata" in c and "document_id" in c["metadata"]
    }

    if incoming_doc_ids:
        filtered_chunks = [
            c for c in all_chunks
            if c.get("metadata", {}).get("document_id") not in incoming_doc_ids
        ]
        
        removed_count = len(all_chunks) - len(filtered_chunks)
        if removed_count > 0:
            print(f"[BM25] Removed {removed_count} old chunks for document(s) {incoming_doc_ids} to prevent duplicates.")
        
        all_chunks = filtered_chunks

    all_chunks.extend(chunks)
    all_texts = [c["text"] for c in all_chunks]
    tokenized_corpus = [text.lower().split() for text in all_texts]
    bm25 = BM25Okapi(tokenized_corpus)

    # Save to disk
    print(f"[BM25] Saving index with total {len(all_chunks)} chunks...")
    os.makedirs("data", exist_ok=True)
    
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25, 
            "chunks": all_chunks  
        }, f)
    
    print("[BM25] Indexing complete!")


def build_indexes(chunks):
    """
    Takes chunks and routes them to both Vector DB and BM25 index IN PARALLEL.
    """
    if not chunks:
        print("⚠️ No chunks provided to indexer.")
        return

    print(f"Starting parallel ingestion for {len(chunks)} chunks...")

    # Run both indexing tasks at the same time using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_vector = executor.submit(_update_vector_db, chunks)
        future_bm25 = executor.submit(_update_bm25_index, chunks)
        
        # Wait for both tasks to complete and catch any errors
        try:
            future_vector.result()
            future_bm25.result()
        except Exception as e:
            print(f"Error during parallel indexing: {e}")
            raise e

    print("Both Vector and BM25 indexing completed successfully in parallel!")