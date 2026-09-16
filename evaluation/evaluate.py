"""BATCH 2 — reads raw_results.json (from run_pipeline.py), scores every
item on retrieval + citation metrics (free, local) and generation metrics
(gpt-oss judge calls via litellm, decoupled from the app's own Gemini/Groq
usage). Writes results/scored_results.json.

Usage:
    python evaluate.py
"""

import asyncio
import json

from config import RESULTS_DIR
from metrics import score_retrieval, score_citations, score_generation_batch

RAW_PATH = RESULTS_DIR / "raw_results.json"
SCORED_PATH = RESULTS_DIR / "scored_results.json"


async def main():
    items = json.loads(RAW_PATH.read_text())
    ok_items = [i for i in items if "error" not in i]
    failed_items = [i for i in items if "error" in i]

    print(f"Scoring {len(ok_items)} items ({len(failed_items)} failed in Batch 1, skipped)")

    # deterministic — instant, no network
    for item in ok_items:
        item.update(score_retrieval(item))
        item.update(score_citations(item))

    # LLM-judged — concurrent, bounded by JUDGE_CONCURRENCY
    gen_scores = await score_generation_batch(ok_items)
    for item, scores in zip(ok_items, gen_scores):
        item.update(scores)

    SCORED_PATH.write_text(json.dumps(ok_items + failed_items, indent=2))
    print(f"✅ Batch 2 done -> {SCORED_PATH}")


if __name__ == "__main__":
    asyncio.run(main())