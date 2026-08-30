"""Vector-only ingestion to Qdrant Cloud (embeddings + metadata)."""

from ingestion.embedder import get_embedder
from config import settings
from retrieval.vector_store import ensure_collection, upsert_vectors


def _update_vector_db(chunks):
    """Embed and upsert chunks into Qdrant Cloud."""
    print("[Vector DB] Generating local embeddings...")
    embedder = get_embedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)

    print("[Vector DB] Writing to Qdrant Cloud...")

    vector_size = len(embeddings[0]) if embeddings else 384  # all-MiniLM-L6-v2
    ensure_collection(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        vector_size=vector_size
    )

    ids = [c["chunk_id"] for c in chunks]
    payloads = []
    for c in chunks:
        payload = {"text": c["text"], **c["metadata"]}
        payloads.append(payload)

    upsert_vectors(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        ids=ids,
        vectors=embeddings,
        payloads=payloads
    )

    print("[Vector DB] Indexing complete (Qdrant Cloud)!")


def build_indexes(chunks):
    """Vector-only indexing to Qdrant Cloud (single store)."""
    if not chunks:
        print("⚠️ No chunks provided to indexer.")
        return

    print(f"Starting ingestion for {len(chunks)} chunks...")

    try:
        _update_vector_db(chunks)
        print("✅ Vector indexing completed successfully!")
    except Exception as e:
        print(f"Error during indexing: {e}")
        raise e
