"""Qdrant Cloud vector store: singleton client, collection setup, upsert, search."""

from typing import List, Dict, Optional
import time
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from config import settings


def string_to_uuid(s: str) -> str:
    """Deterministic UUID v5 for a string (Qdrant requires UUID point IDs), so
    the same chunk_id always maps to the same UUID."""
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
    return str(uuid.uuid5(namespace, s))


# --- Singleton Qdrant client ---

_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get or create the singleton Qdrant Cloud client."""
    global _qdrant_client

    if _qdrant_client is None:
        if not settings.QDRANT_URL or not settings.QDRANT_API_KEY:
            raise ValueError(
                "Qdrant Cloud credentials not configured. "
                "Set QDRANT_URL and QDRANT_API_KEY in your .env file."
            )

        print(f"🔗 Connecting to Qdrant Cloud at {settings.QDRANT_URL}...")
        # 120s: the first upsert into a fresh collection (incl. building payload
        # indexes) can exceed 30s on a remote cluster — let ingestion take time.
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=120
        )
        print("✅ Connected to Qdrant Cloud successfully")

    return _qdrant_client


def ensure_collection(
    collection_name: str,
    vector_size: int,
    distance: Distance = Distance.COSINE
) -> None:
    """Create the collection if missing (idempotent) and ensure payload indexes."""
    client = get_qdrant_client()

    try:
        collections = client.get_collections().collections
        existing = [c for c in collections if c.name == collection_name]

        if not existing:
            print(f"📦 Creating Qdrant collection '{collection_name}' (vector_size={vector_size}, distance={distance.name})...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=distance)
            )
            print(f"✅ Collection '{collection_name}' created successfully")
        else:
            print(f"✅ Collection '{collection_name}' already exists (idempotent check passed)")
    except Exception as e:
        print(f"❌ Failed to ensure collection '{collection_name}': {e}")
        raise

    _ensure_payload_indexes(client, collection_name)


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Create keyword payload indexes on filter fields (required for filtered
    search); idempotent — existing-index errors are swallowed."""
    from qdrant_client.models import PayloadSchemaType

    for field in ["user_id", "document_id"]:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD
            )
            print(f"✅ Created keyword payload index on '{field}'")
        except Exception:
            pass  # index already exists or creation failed — non-fatal


def upsert_vectors(
    collection_name: str,
    ids: List[str],
    vectors: List[List[float]],
    payloads: List[Dict]
) -> None:
    """Upsert vectors into a Qdrant collection (batched with retries)."""
    client = get_qdrant_client()

    if not ids or not vectors or not payloads:
        print("⚠️  No vectors to upsert (empty input)")
        return

    if not (len(ids) == len(vectors) == len(payloads)):
        raise ValueError(
            f"Length mismatch: ids={len(ids)}, vectors={len(vectors)}, payloads={len(payloads)}"
        )

    # Convert chunk_ids to deterministic UUIDs; keep the original in the payload.
    points = []
    for chunk_id, vector, payload in zip(ids, vectors, payloads):
        points.append(PointStruct(
            id=string_to_uuid(chunk_id),
            vector=vector,
            payload={"chunk_id": chunk_id, **payload}
        ))

    # Batch upserts: keeps each call small and lets a slow batch retry
    # independently. Retries are safe since UUIDs are deterministic.
    total = len(points)
    batch_size = 64
    print(f"📤 Upserting {total} vectors to Qdrant collection '{collection_name}' (batches of {batch_size})...")

    for i in range(0, total, batch_size):
        batch = points[i : i + batch_size]
        batch_no = i // batch_size + 1
        for attempt in range(3):
            try:
                client.upsert(collection_name=collection_name, points=batch)
                print(f"    ✅ batch {batch_no} ({(i + 1)}–{min(i + len(batch), total)}) upserted")
                break
            except Exception as e:
                if attempt >= 2:
                    print(f"❌ Upsert batch {batch_no} failed after 3 attempts: {e}")
                    raise
                print(f"⚠️ Upsert batch {batch_no} attempt {attempt + 1} failed ({e}); retrying...")
                time.sleep(2 * (attempt + 1))

    print(f"✅ Successfully upserted {total} vectors")


def search_vectors(
    collection_name: str,
    query_vector: List[float],
    top_k: int = 5,
    filter_dict: Optional[Dict] = None
) -> List[Dict]:
    """Search for similar vectors, returning chunk dicts
    (chunk_id, text, metadata, score)."""
    client = get_qdrant_client()

    collection_info = client.get_collection(collection_name)
    if collection_info.points_count == 0:
        print(f"⚠️  Collection '{collection_name}' is empty, returning no results")
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue
    search_filter = None
    if filter_dict:
        conditions = [
            FieldCondition(key=key, match=MatchValue(value=value))
            for key, value in filter_dict.items()
        ]
        search_filter = Filter(must=conditions)

    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        query_filter=search_filter
    ).points

    retrieved_chunks = []
    for hit in results:
        retrieved_chunks.append({
            "chunk_id": hit.payload.get("chunk_id", str(hit.id)),
            "text": hit.payload.get("text", ""),
            "metadata": {
                k: v for k, v in hit.payload.items() if k not in ["text", "chunk_id"]
            },
            "score": hit.score
        })

    return retrieved_chunks
