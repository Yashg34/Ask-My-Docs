"""Retriever node: vector-only fetch from Qdrant (FlashRank narrows after)."""

from graph.state import GraphState
from retrieval.vector_retriever import VectorRetriever
from config import settings

vec_retriever = VectorRetriever()


def retrieve_documents(state: GraphState):
    """Fetch wide top-K candidates from Qdrant, filtered by user/document."""
    print("[Node: Retriever] Fetching candidates via Vector (Qdrant Cloud)...")
    query = state["search_query"]
    top_k = state.get("top_k", settings.TOP_K_RETRIEVAL)
    user_id = state.get("user_id")
    document_id = state.get("document_id")

    where_filter = {"user_id": user_id}
    if document_id:
        where_filter["document_id"] = document_id

    vec_results = vec_retriever.retrieve(query, top_k=top_k, where_filter=where_filter)

    if not vec_results:
        rev_count = state.get("revision_count", 0)
        return {
            "retrieved_chunks": [],
            "formatted_context": "",
            "draft_answer": "I couldn't find any relevant information in your documents to answer this question. Could you please rephrase or check if the document contains this info?",
            "is_valid": True,
            "revision_count": rev_count + 1
        }

    print(f"[Node: Retriever] Retrieved {len(vec_results)} candidates from Qdrant Cloud")
    return {"retrieved_chunks": vec_results}
