"""Deterministic retrieval metrics — pure set/rank comparisons between the
gold `chunk_ids` in golden_dataset.json and the `chunk_id`s the pipeline
actually retrieved (ingestion/chunker.py's `{document_id}_{page}_{hash}`
format, unchanged as it flows through vector_retriever.py -> reranker.py ->
the /query response). No LLM calls, no network — safe to run as many times
as you want.
"""


def _retrieved_ids(retrieved_chunks: list[dict]) -> list[str]:
    """Preserves rank order — retrieved_chunks[0] is the top-ranked chunk
    after FlashRank reranking (reranker_node.py)."""
    return [c["chunk_id"] for c in retrieved_chunks]


def hit_rate(gold_chunk_ids: list[str], retrieved_chunks: list[dict]) -> float:
    """1.0 if at least one gold chunk was retrieved, else 0.0.
    Also called Context Recall@k when every question has exactly one gold
    chunk (62/66 of yours do)."""
    gold = set(gold_chunk_ids)
    retrieved = set(_retrieved_ids(retrieved_chunks))
    return 1.0 if gold & retrieved else 0.0


def context_recall(gold_chunk_ids: list[str], retrieved_chunks: list[dict]) -> float:
    """Fraction of gold chunks that were retrieved. Only diverges from
    hit_rate on multi-chunk questions (4/66 of yours)."""
    if not gold_chunk_ids:
        return 1.0
    gold = set(gold_chunk_ids)
    retrieved = set(_retrieved_ids(retrieved_chunks))
    return len(gold & retrieved) / len(gold)


def context_precision(gold_chunk_ids: list[str], retrieved_chunks: list[dict]) -> float:
    """Fraction of retrieved chunks that were actually gold. Low precision
    with high recall means the reranker/top_n is letting noise through even
    though the right chunk is in there somewhere."""
    retrieved = _retrieved_ids(retrieved_chunks)
    if not retrieved:
        return 0.0
    gold = set(gold_chunk_ids)
    hits = sum(1 for cid in retrieved if cid in gold)
    return hits / len(retrieved)


def mrr(gold_chunk_ids: list[str], retrieved_chunks: list[dict]) -> float:
    """1 / rank of the first gold chunk in the ranked retrieved list
    (rank 1 = top of the list), 0.0 if no gold chunk was retrieved at all."""
    gold = set(gold_chunk_ids)
    for rank, cid in enumerate(_retrieved_ids(retrieved_chunks), start=1):
        if cid in gold:
            return 1.0 / rank
    return 0.0


def score_retrieval(item: dict) -> dict:
    """Convenience wrapper: scores one row from raw_results.json (already
    joined to its gold chunk_ids by run_pipeline.py) against all 4 metrics."""
    gold_ids = item["gold_chunk_ids"]
    retrieved = item["retrieved_chunks"]
    return {
        "hit_rate": hit_rate(gold_ids, retrieved),
        "context_recall": context_recall(gold_ids, retrieved),
        "context_precision": context_precision(gold_ids, retrieved),
        "mrr": mrr(gold_ids, retrieved),
    }