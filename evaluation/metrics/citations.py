import re

CITATION_RE = re.compile(r"\[([^,\]]+),\s*Page\s*(\d+)\]", re.IGNORECASE)


def _extract_citations(answer: str) -> set[tuple[str, int]]:
    return {(doc.strip(), int(page)) for doc, page in CITATION_RE.findall(answer)}


def _retrieved_pairs(retrieved_chunks: list[dict]) -> set[tuple[str, int]]:
    return {
        (c["metadata"]["document_name"], c["metadata"]["page"])
        for c in retrieved_chunks
    }


def citation_precision(answer: str, retrieved_chunks: list[dict]) -> float:
    """Of the citations printed, how many reference a (doc, page) that was
    actually in the retrieved context (i.e. not fabricated)."""
    cited = _extract_citations(answer)
    if not cited:
        return 0.0
    valid = _retrieved_pairs(retrieved_chunks)
    return sum(1 for c in cited if c in valid) / len(cited)


def citation_recall(answer: str, gold_document_name: str, gold_pages: list[int]) -> float:
    """Of the gold (doc, page) pairs for this question, how many were cited."""
    gold = {(gold_document_name, p) for p in gold_pages}
    if not gold:
        return 1.0
    cited = _extract_citations(answer)
    return sum(1 for g in gold if g in cited) / len(gold)


def citation_presence(answer: str) -> float:
    return 1.0 if _extract_citations(answer) else 0.0


def score_citations(item: dict) -> dict:
    answer = item["answer"]
    return {
        "citation_precision": citation_precision(answer, item["retrieved_chunks"]),
        "citation_recall": citation_recall(answer, item["gold_document_name"], item["gold_pages"]),
        "citation_presence": citation_presence(answer),
    }