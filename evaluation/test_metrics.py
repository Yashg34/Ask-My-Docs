"""Offline self-test for the evaluation metrics. No network, no API keys —
the LLM judge is monkeypatched. Run from the `evaluation/` directory:

    python test_metrics.py
"""

import asyncio
import os

# Must be set before importing `metrics` (config.py fails fast without them).
os.environ.setdefault("EVAL_EMAIL", "test@example.com")
os.environ.setdefault("EVAL_PASSWORD", "test-password")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("JUDGE_MODEL", "groq/openai/gpt-oss-120b")

import litellm

from metrics.retrieval import hit_rate, context_recall, context_precision, mrr
from metrics.citations import citation_precision, citation_recall, citation_presence
from metrics.generation import _judge_failure, score_generation_batch

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}")


def test_retrieval():
    gold = ["doc1_2_abcdef1234567890", "doc1_3_ffffffffffffffff"]
    # Rank 1 holds a gold chunk, another gold missing entirely, plus one noise chunk.
    retrieved = [
        {"chunk_id": "doc1_2_abcdef1234567890", "text": "a"},
        {"chunk_id": "doc1_9_0000000000000000", "text": "b"},
    ]
    check("hit_rate single.",                                                     hit_rate(gold, retrieved) == 1.0)
    check("context_recall 1/2 gold.",                                              context_recall(gold, retrieved) == 0.5)
    check("context_precision 1/2 retrieved.",                                      context_precision(gold, retrieved) == 0.5)
    check("mrr rank1.",                                                           mrr(gold, retrieved) == 1.0)

    retrieved_rank2 = [
        {"chunk_id": "doc1_9_0000000000000000", "text": "b"},
        {"chunk_id": "doc1_2_abcdef1234567890", "text": "a"},
    ]
    check("mrr rank2.",                                                           mrr(gold, retrieved_rank2) == 0.5)

    none = [{"chunk_id": "doc1_9_0000000000000000", "text": "b"}]
    check("hit_rate none retrieved.",                                             hit_rate(gold, none) == 0.0)
    check("context_recall none.",                                                 context_recall(gold, none) == 0.0)
    check("context_precision none.",                                            context_precision(gold, none) == 0.0)
    check("mrr none.",                                                            mrr(gold, none) == 0.0)
    check("context_precision empty retrieved.",                          context_precision(gold, []) == 0.0)
    check("context_recall empty gold is 1.0.",                           context_recall([], retrieved) == 1.0)


def test_citations():
    answer = "It is [Random_Attention.pdf, Page 2] and [Context_Compression.pdf, Page 9]."
    chunks = [
        {"metadata": {"document_name": "Random_Attention.pdf", "page": 2}},
        {"metadata": {"document_name": "Context_Compression.pdf", "page": 9}},
        {"metadata": {"document_name": "Random_Attention.pdf", "page": 5}},  # present, not cited
    ]
    check("citation_presence found.",                                     citation_presence(answer) == 1.0)
    check("citation_precision all cited retrieved.",            citation_precision(answer, chunks) == 1.0)
    check("citation_recall gold page cited.",       citation_recall(answer, "Random_Attention.pdf", [2]) == 1.0)

    answer_fabricated = "[Random_Attention.pdf, Page 2] and [Random_Attention.pdf, Page 99]"
    chunks2 = [{"metadata": {"document_name": "Random_Attention.pdf", "page": 2}}]
    check("citation_precision half fabricated.",        citation_precision(answer_fabricated, chunks2) == 0.5)
    check("citation_recall wrong page 0.",      citation_recall(answer, "Random_Attention.pdf", [7]) == 0.0)
    check("citation_presence none.",                               citation_presence("No citations here") == 0.0)
    check("citation_precision no citation 0.",               citation_precision("No citations", chunks) == 0.0)


def test_judge_failure_is_isolated():
    async def scenario():
        orig = litellm.acompletion

        async def boom(**kwargs):
            raise RuntimeError("rate-limited")

        async def ok(**kwargs):
            class M:
                content = ('{"faithfulness": 1.0, "faithfulness_reason": "g", '
                           '"answer_correctness": 0.5, "correctness_reason": "c", '
                           '"answer_relevancy": 1.0, "relevancy_reason": "r"}')
            class C:
                message = M()
            class R:
                choices = [C()]
            return R()

        items = [
            {"question": "q1", "ground_truth_answer": "g1", "answer": "a1", "retrieved_chunks": [{"text": "c"}]},
            {"question": "q2", "ground_truth_answer": "g2", "answer": "a2", "retrieved_chunks": [{"text": "c"}]},
        ]

        # All judges fail -> no exception, one None-row per item.
        litellm.acompletion = boom
        try:
            scores = await score_generation_batch(items)
        finally:
            litellm.acompletion = orig
        check("judge all-fail returns no exception.",                        len(scores) == len(items))
        check("judge all-fail rows are None.",              all(s["faithfulness"] is None for s in scores))

        # One fails, one succeeds -> rows stay aligned with input order, no exception.
        litellm.acompletion = ok
        try:
            scores = await score_generation_batch(items)
        finally:
            litellm.acompletion = orig
        check("judge ok rows scored.",                                    scores[0]["faithfulness"] == 1.0)

        return True

    check("judge failure isolation scenario.", asyncio.run(scenario()))


if __name__ == "__main__":
    print("== offline metric self-test ==")
    test_retrieval()
    test_citations()
    test_judge_failure_is_isolated()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)