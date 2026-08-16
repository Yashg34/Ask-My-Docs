import os
import pickle
import chromadb
from rank_bm25 import BM25Okapi
from ingestion.embedder import LocalEmbedder

CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
MASTER_COLLECTION = "master_docs"
BM25_INDEX_PATH = os.path.join("data", "bm25_index.pkl")

def build_indexes(chunks):
    """
    Takes chunks and routes them to both Vector DB and BM25 index.
    """
    if not chunks:
        print("⚠️ No chunks provided to indexer.")
        return

    print("🧠 Generating local embeddings for Vector DB...")
    embedder = LocalEmbedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)

    print(f"💾 Storing in ChromaDB (Collection: '{MASTER_COLLECTION}')...")
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
    print("✅ Vector indexing complete!")

    
    print("🔤 Updating BM25 Keyword Index...")
    
    #  Check if previous BM25 data exists to prevent overwriting
    all_chunks = []
    if os.path.exists(BM25_INDEX_PATH):
        try:
            with open(BM25_INDEX_PATH, "rb") as f:
                existing_data = pickle.load(f)
                all_chunks = existing_data.get("chunks", [])
                print(f"🔄 Loaded {len(all_chunks)} existing chunks from BM25 index.")
        except Exception as e:
            print(f"⚠️ Could not load existing BM25 index, starting fresh. Error: {e}")

    # Combine old chunks with the new ones
    all_chunks.extend(chunks)

    # Rebuild the BM25 model with the complete dataset
    all_texts = [c["text"] for c in all_chunks]
    tokenized_corpus = [text.lower().split() for text in all_texts]
    bm25 = BM25Okapi(tokenized_corpus)

    # Save the updated BM25 model and the combined chunk data
    print(f"💾 Saving BM25 index with total {len(all_chunks)} chunks to {BM25_INDEX_PATH}...")
    os.makedirs("data", exist_ok=True)
    
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25, 
            "chunks": all_chunks  
        }, f)
    
    print("✅ BM25 indexing complete!")