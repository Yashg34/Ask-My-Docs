"""Vector retriever using Qdrant Cloud."""

from typing import List, Dict
from ingestion.embedder import get_embedder
from config import settings
from retrieval.vector_store import search_vectors


class VectorRetriever:
    """Retrieves similar chunks from Qdrant Cloud via vector search."""

    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        self.embedder = get_embedder()

    def retrieve(self, query: str, top_k: int = 5, where_filter: dict = None) -> List[Dict]:
        """Return top_k chunk dicts (chunk_id, text, metadata, score) for the query."""
        query_embedding = self.embedder.embed_query(query)

        return search_vectors(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            top_k=top_k,
            filter_dict=where_filter
        )
