"""FlashRank reranker: narrows vector candidates with a lightweight scoring model."""

from flashrank import Ranker, RerankRequest


class FlashRankReranker:
    """Fast, lightweight reranker over vector-retrieved candidates."""

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
        print("⏳ Loading FlashRank model (this might take a few seconds)...")
        self.model = Ranker(model_name=model_name, cache_dir=".flashrank_cache")
        print("✅ FlashRank model loaded successfully")

    def rerank(
        self,
        query: str,
        candidates: list,
        top_n: int = 5,
        threshold: float = 0.0
    ) -> list:
        """Rerank candidates by FlashRank score, keeping those above `threshold`,
        and return the top_n (default 5) as a subset of candidates."""
        if not candidates:
            return []

        passages = [
            {"id": i, "text": chunk.get("text", ""), "meta": chunk.get("metadata", {})}
            for i, chunk in enumerate(candidates)
        ]

        results = self.model.rerank(RerankRequest(query=query, passages=passages))

        reranked_chunks = []
        for result in results[:top_n]:
            if result["score"] < threshold:
                continue
            chunk = candidates[result["id"]]
            reranked_chunks.append({**chunk, "rerank_score": float(result["score"])})

        return reranked_chunks
