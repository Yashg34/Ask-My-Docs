"""Reranker node: narrows vector candidates to top-N with FlashRank."""

from graph.state import GraphState
from retrieval.reranker import FlashRankReranker
from config import settings

reranker = FlashRankReranker()


def rerank_documents(state: GraphState):
    """Rerank wide retrieval results down to top_n using FlashRank."""
    print("[Node: Reranker] Filtering candidates via FlashRank...")
    candidates = state["retrieved_chunks"]
    top_n = state.get("top_n", settings.TOP_K_RERANK)

    final_chunks = reranker.rerank(
        query=state.get("search_query") or state["query"],
        candidates=candidates,
        top_n=top_n,
        threshold=state.get("threshold", 0.0)  # FlashRank scores are 0-1
    )

    print(f"[Node: Reranker] Narrowed down to {len(final_chunks)} high-quality chunks")
    return {"retrieved_chunks": final_chunks}
