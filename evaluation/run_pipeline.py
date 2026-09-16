"""BATCH 1 — exercises the live pipeline through the Node gateway's /query
endpoint (query.controller.js -> aiClient -> FastAPI -> strong-model/Gemini).

This is the phase bound by your Gemini free-tier quota, so it runs in
sub-batches of `BATCH_SIZE` with a `SLEEP_BETWEEN_BATCHES_SEC` pause between
them, and checkpoints each sub-batch to disk — if you get rate-limited or
kill the run partway through, re-running this script skips sub-batches
that already succeeded instead of re-spending quota on them.

Usage:
    python run_pipeline.py
"""

import asyncio
import json

from tqdm import tqdm

from auth import get_authenticated_client
from config import settings, RESULTS_DIR, GOLDEN_DATASET_PATH

RAW_PARTS_DIR = RESULTS_DIR / "raw_parts"
FINAL_OUTPUT_PATH = RESULTS_DIR / "raw_results.json"


def load_golden_items() -> list[dict]:
    dataset = json.loads(GOLDEN_DATASET_PATH.read_text())
    return dataset["items"]


def chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def run_one(client, item: dict) -> dict:
    """Call POST /query exactly as the frontend does, and unwrap the gateway's
    {message, history_id, data: {...}} envelope (see query.controller.js)."""
    payload = {
        "query": item["question"],
        "topK": 15,      # matches FastAPI QueryRequest defaults / backend README
        "topN": 5,
        "threshold": 0.05,
        "chatHistory": [],
        "queryId": "",
    }
    if settings.DOCUMENT_ID:
        payload["documentId"] = settings.DOCUMENT_ID

    resp = await client.post("/query", json=payload)

    if resp.status_code != 200:
        # Surfaces the gateway's { error: { code, message } } envelope
        # (forwarded verbatim from FastAPI or raised locally — see
        # query.controller.js's catch block) instead of a bare HTTPStatusError.
        detail = resp.json().get("error", {}).get("message", resp.text)
        raise RuntimeError(f"/query failed [{resp.status_code}] for {item['id']}: {detail}")

    body = resp.json()
    data = body["data"]

    return {
        "id": item["id"],
        "question": item["question"],
        "ground_truth_answer": item["ground_truth_answer"],
        "gold_chunk_ids": item["chunk_ids"],
        "gold_document_name": item["document_name"],
        "gold_pages": item["pages"],
        "history_id": body.get("history_id"),
        "answer": data["answer"],
        "latency_seconds": data["latency_seconds"],
        "retrieved_chunks": data["retrieved_chunks"],
    }


async def run_batch(client, batch: list[dict]) -> list[dict]:
    # Sequential, not gather() — concurrent requests would defeat the whole
    # point of BATCH_SIZE + SLEEP pacing your Gemini quota.
    results = []
    for item in batch:
        try:
            results.append(await run_one(client, item))
        except Exception as e:
            print(f"⚠️  {item['id']} failed: {e}")
            results.append({"id": item["id"], "question": item["question"], "error": str(e)})
    return results


async def main():
    RAW_PARTS_DIR.mkdir(exist_ok=True)
    golden_items = load_golden_items()
    batches = chunk(golden_items, settings.BATCH_SIZE)
    print(f"{len(golden_items)} questions -> {len(batches)} batches of ≤{settings.BATCH_SIZE}")

    client = await get_authenticated_client()
    try:
        for batch_idx, batch in enumerate(tqdm(batches, desc="Batches")):
            part_path = RAW_PARTS_DIR / f"batch_{batch_idx:03d}.json"
            if part_path.exists():
                continue  # resume: this sub-batch already succeeded in a prior run

            batch_results = await run_batch(client, batch)
            part_path.write_text(json.dumps(batch_results, indent=2))

            if batch_idx < len(batches) - 1:
                await asyncio.sleep(settings.SLEEP_BETWEEN_BATCHES_SEC)
    finally:
        await client.aclose()

    # Merge all sub-batch parts into one file for evaluate.py to consume.
    all_results = []
    for part_path in sorted(RAW_PARTS_DIR.glob("batch_*.json")):
        all_results.extend(json.loads(part_path.read_text()))
    FINAL_OUTPUT_PATH.write_text(json.dumps(all_results, indent=2))

    n_ok = sum(1 for r in all_results if "error" not in r)
    print(f"✅ Batch 1 done: {n_ok}/{len(all_results)} succeeded -> {FINAL_OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())