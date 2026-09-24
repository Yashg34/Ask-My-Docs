#!/usr/bin/env python3
"""
Algorithmic RAG metrics from raw_results.json.

Retrieval : Hit Rate@K, Context Recall@K, Context Precision@K, MRR@K   (chunk-id based)
Citation  : Citation Presence, Citation Precision, Citation Recall     (document + page based)
Performance: Mean / P50 / P95 / P99 latency

Usage: python rag_metrics.py [path/to/raw_results.json] [output_dir]
"""
import csv
import json
import re
import statistics
import sys
from pathlib import Path


RESULTS_DIR = Path("results")  # adjust if your layout differs
IN_PATH = RESULTS_DIR / "raw_results.json"
OUT_DIR = RESULTS_DIR

# ----------------------------------------------------------------------------
# Citation parsing
# ----------------------------------------------------------------------------
def normalise(text: str, fullwidth_brackets: bool = True) -> str:
    """Fold typographic variants the LLM emitted (narrow NBSP, non-breaking hyphen, 【】)."""
    text = re.sub(r"[\u202f\u00a0\u2009\u2002\u2003]", " ", text)   # odd spaces -> space
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)              # odd hyphens/dashes -> '-'
    if fullwidth_brackets:
        text = text.replace("\u3010", "[").replace("\u3011", "]")   # 【 】 -> [ ]
    return text


BRACKET = re.compile(r"\[[^\[\]]*\]")
# e.g. "Doc.pdf, Page 4" | "Doc.pdf, Pages 4-5" | "Doc.pdf, Page 5-6, Chunk 5-6_0011_ab.."
# A bracket may hold several citations (each restarts with "<name>.pdf,"), so use finditer.
CITE = re.compile(r"([A-Za-z0-9_.\-]+\.pdf)\s*,\s*Pages?\s*(\d+)(?:\s*-\s*(\d+))?", re.I)


def parse_citations(answer: str, fullwidth_brackets: bool = True):
    """Return list of (doc_name, frozenset(pages)) - one entry per citation instance."""
    out = []
    for br in BRACKET.findall(normalise(answer, fullwidth_brackets)):
        for m in CITE.finditer(br):
            doc, lo = m.group(1), int(m.group(2))
            hi = int(m.group(3)) if m.group(3) else lo
            lo, hi = min(lo, hi), max(lo, hi)
            out.append((doc, frozenset(range(lo, hi + 1))))   # "Pages 4-5" -> {4, 5}
    return out


# ----------------------------------------------------------------------------
# Latency percentiles (linear interpolation == numpy default)
# ----------------------------------------------------------------------------
def percentile(values, p):
    xs = sorted(values)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


# ----------------------------------------------------------------------------
# Per-question metrics
# ----------------------------------------------------------------------------
def score_question(r, fullwidth_brackets=True):
    gold_ids = list(r["gold_chunk_ids"])
    gold_doc = r["gold_document_name"]
    gold_pages = list(r["gold_pages"])                # kept exactly as provided
    chunks = r["retrieved_chunks"]
    ret_ids = [c["chunk_id"] for c in chunks]
    K = len(ret_ids)

    # ---- retrieval (chunk-id based) ----
    hits_in_ret = [g for g in gold_ids if g in ret_ids]
    hit = 1.0 if hits_in_ret else 0.0
    recall = len(hits_in_ret) / len(gold_ids) if gold_ids else None
    n_rel = sum(1 for cid in ret_ids if cid in gold_ids)
    precision = (n_rel / K) if K else 0.0             # K=0 -> nothing relevant retrieved -> 0
    rr = 0.0
    for rank, cid in enumerate(ret_ids, 1):
        if cid in gold_ids:
            rr = 1.0 / rank
            break

    # diagnostic (NOT one of the requested metrics): page-overlap lenient hit
    lenient = 0.0
    for c in chunks:
        m = c["metadata"]
        if m["document_name"] == gold_doc and any(
            m["page_start"] <= p <= m["page_end"] for p in gold_pages
        ):
            lenient = 1.0
            break
    hit_at = {k: float(any(cid in gold_ids for cid in ret_ids[:k])) for k in (1, 3, 5)}

    # ---- citations ----
    cites = parse_citations(r["answer"], fullwidth_brackets)
    presence = 1.0 if cites else 0.0
    cited_pairs = {(d, p) for d, pages in cites for p in pages}
    gold_set = set(gold_pages)
    correct = {(d, p) for d, p in cited_pairs if d == gold_doc and p in gold_set}
    cit_precision = (len(correct) / len(cited_pairs)) if cited_pairs else None   # undefined w/o citations
    cit_recall = len({p for d, p in correct}) / len(gold_set) if gold_set else None

    # diagnostic: cited page not covered by any retrieved chunk (ungrounded citation)
    ret_pairs = {
        (c["metadata"]["document_name"], p)
        for c in chunks
        for p in range(c["metadata"]["page_start"], c["metadata"]["page_end"] + 1)
    }
    ungrounded = (len(cited_pairs - ret_pairs) / len(cited_pairs)) if cited_pairs else None

    return {
        "id": r["id"], "K": K,
        "hit_rate": hit, "context_recall": recall, "context_precision": precision, "rr": rr,
        "citation_presence": presence, "citation_precision": cit_precision,
        "citation_recall": cit_recall, "latency_seconds": r["latency_seconds"],
        # diagnostics
        "lenient_page_hit": lenient, "hit@1": hit_at[1], "hit@3": hit_at[3], "hit@5": hit_at[5],
        "n_citations": len(cites), "ungrounded_cite_frac": ungrounded,
        "gold_doc": gold_doc, "gold_pages": gold_pages,
        "cited": sorted({f"{d}:{p}" for d, p in cited_pairs}),
    }


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    errored = [r for r in data if "error" in r or "retrieved_chunks" not in r]
    valid = [r for r in data if r not in errored]
    rows = [score_question(r) for r in valid]
    strict_rows = [score_question(r, fullwidth_brackets=False) for r in valid]

    lat = [r["latency_seconds"] for r in rows]
    n = len(rows)
    Ks = [r["K"] for r in rows]

    overall = {
        "n_records_in_file": len(data),
        "n_errored_excluded": len(errored),
        "errored_ids": [r["id"] for r in errored],
        "n_questions_evaluated": n,
        "avg_K_retrieved_all": mean(Ks),
        "avg_K_retrieved_nonempty": mean([k for k in Ks if k > 0]),
        "n_empty_retrieval": sum(1 for k in Ks if k == 0),
        "K_distribution": {str(k): Ks.count(k) for k in sorted(set(Ks))},
        # retrieval
        "hit_rate@K": mean([r["hit_rate"] for r in rows]),
        "context_recall@K": mean([r["context_recall"] for r in rows]),
        "context_precision@K": mean([r["context_precision"] for r in rows]),
        "context_precision@K_excl_empty": mean([r["context_precision"] for r in rows if r["K"] > 0]),
        "mrr@K": mean([r["rr"] for r in rows]),
        # citation
        "citation_presence": mean([r["citation_presence"] for r in rows]),
        "citation_precision_macro": mean([r["citation_precision"] for r in rows]),
        "n_questions_with_citations": sum(1 for r in rows if r["citation_presence"]),
        "citation_recall": mean([r["citation_recall"] for r in rows]),
        "citation_recall_among_cited": mean([r["citation_recall"] for r in rows if r["citation_presence"]]),
        # latency
        "latency_mean": statistics.fmean(lat),
        "latency_p50": percentile(lat, 50),
        "latency_p95": percentile(lat, 95),
        "latency_p99": percentile(lat, 99),
        "latency_min": min(lat), "latency_max": max(lat),
        # diagnostics
        "diag_hit@1": mean([r["hit@1"] for r in rows]),
        "diag_hit@3": mean([r["hit@3"] for r in rows]),
        "diag_hit@5": mean([r["hit@5"] for r in rows]),
        "diag_lenient_page_hit": mean([r["lenient_page_hit"] for r in rows]),
        "diag_ungrounded_cite_frac": mean([r["ungrounded_cite_frac"] for r in rows]),
        "strict_ascii_brackets_only": {
            "citation_presence": mean([r["citation_presence"] for r in strict_rows]),
            "citation_precision_macro": mean([r["citation_precision"] for r in strict_rows]),
            "citation_recall": mean([r["citation_recall"] for r in strict_rows]),
            "n_questions_with_citations": sum(1 for r in strict_rows if r["citation_presence"]),
        },
    }

    # ---- write outputs ----
    (OUT_DIR / "overall_metrics.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    cols = ["id", "K", "hit_rate", "context_recall", "context_precision", "rr",
            "citation_presence", "citation_precision", "citation_recall", "latency_seconds",
            "lenient_page_hit", "n_citations", "ungrounded_cite_frac", "gold_doc", "gold_pages", "cited"]
    with open(OUT_DIR / "per_question_metrics.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] if r[c] is not None else "" for c in cols])
        for e in errored:
            w.writerow([e["id"], "ERROR"] + [""] * (len(cols) - 2))

    print(json.dumps(overall, indent=2))
    return rows, errored, overall


if __name__ == "__main__":
    main()