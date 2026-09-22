#!/usr/bin/env python3
"""
LLM-judge Faithfulness, Correctness, and Answer Relevancy for a RAG eval file,
using Groq's OpenAI-compatible chat completions API.

Each of the 3 metrics is scored 0 / 0.5 / 1 per question, by a single judge call
that returns strict JSON. Results merge with the retrieval/citation metrics from
rag_metrics.py if that file's per_question_metrics.csv is present.

Setup
-----
    pip install groq                 # official SDK (falls back to `requests` if absent)
    export GROQ_API_KEY="gsk_..."    # https://console.groq.com/keys

Usage
-----
    python judge_with_groq.py [raw_results.json] [output_dir] [--model MODEL] [--workers N]

Notes
-----
- Uses a strong Groq-hosted model by default (see MODEL below); override with --model.
- Temperature 0, JSON-mode response, retried on transient errors / malformed JSON.
- Concurrency via a thread pool, since each judge call is independent.
- Idempotent: writes one row per question id; re-running overwrites the same file.
"""
import argparse
import json
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from groq import Groq
    _HAS_SDK = True
except ImportError:
    import urllib.request
    _HAS_SDK = False

MODEL = "llama-3.3-70b-versatile"          # good default judge; try "llama-3.1-70b-versatile" or larger if available on your account
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_RETRIES = 4
RETRY_BASE_DELAY = 2.0          # seconds, exponential backoff
MAX_CONTEXT_CHARS = 6000        # truncate very long retrieved context per chunk to keep prompts small


JUDGE_SYSTEM_PROMPT = """You are a strict, impartial evaluator for a RAG (Retrieval-Augmented Generation) system.
You will be given a QUESTION, the system's ANSWER, the RETRIEVED CONTEXT the system had access to,
and a GROUND_TRUTH reference answer written by a human.

Score the ANSWER on three metrics, each on a 0 / 0.5 / 1 scale:

1. faithfulness — Is every factual claim in the ANSWER actually supported by the RETRIEVED CONTEXT?
   - 1  = fully grounded; no claim goes beyond what the context supports (a truthful "I don't know"
          when the context lacks the answer also scores 1 here).
   - 0.5 = mostly grounded, but includes at least one minor unsupported detail or an inference that
           goes slightly beyond the context.
   - 0  = contains a claim that contradicts the context, or is fabricated with no support in it.

2. correctness — Does the ANSWER convey the same substantive information as GROUND_TRUTH?
   - 1  = matches the key facts/claims of GROUND_TRUTH (wording can differ).
   - 0.5 = partially correct: gets some required facts right but misses, or gets wrong, others
           (e.g. answers only half of a multi-part question, omits a required number/name).
   - 0  = wrong, contradicts GROUND_TRUTH, answers a different question, or is a non-answer/refusal
          where GROUND_TRUTH shows the question was answerable.

3. answer_relevancy — Does the ANSWER actually address what the QUESTION asked (regardless of correctness)?
   - 1  = directly addresses the question asked.
   - 0.5 = partially addresses it, is vague, or answers an adjacent/broader question.
   - 0  = does not address the question at all (e.g. answers a different topic entirely).

Judge ONLY from the given materials. Do not use outside knowledge of the source document.
Be strict: partial credit (0.5) should be used whenever the answer is not fully right or fully wrong.

Respond with STRICT JSON ONLY, no markdown fences, no commentary, matching exactly this schema:
{"faithfulness": 0|0.5|1, "correctness": 0|0.5|1, "answer_relevancy": 0|0.5|1, "rationale": "<one short sentence>"}
"""

JUDGE_USER_TEMPLATE = """QUESTION:
{question}

ANSWER:
{answer}

RETRIEVED CONTEXT:
{context}

GROUND_TRUTH:
{ground_truth}

Return the JSON verdict now."""


def build_context_block(chunks, max_chars=MAX_CONTEXT_CHARS):
    if not chunks:
        return "(no chunks were retrieved)"
    parts = []
    budget = max_chars
    for c in chunks:
        text = c.get("text", "")
        meta = c.get("metadata", {})
        header = f"[{meta.get('document_name', '?')}, p.{meta.get('page_start', '?')}-{meta.get('page_end', '?')}]"
        snippet = text[: max(0, budget)]
        parts.append(f"{header}\n{snippet}")
        budget -= len(snippet)
        if budget <= 0:
            break
    return "\n---\n".join(parts)


def extract_json(raw: str) -> dict:
    """Groq's JSON mode should return pure JSON, but strip code fences defensively."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def call_groq_sdk(client, model, system_prompt, user_prompt):
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def call_groq_http(api_key, model, system_prompt, user_prompt):
    import urllib.request
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        GROQ_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def judge_one(record, model, api_key=None, sdk_client=None):
    question = record["question"]
    answer = record["answer"]
    ground_truth = record["ground_truth_answer"]
    context = build_context_block(record.get("retrieved_chunks", []))

    user_prompt = JUDGE_USER_TEMPLATE.format(
        question=question, answer=answer, context=context, ground_truth=ground_truth
    )

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if sdk_client is not None:
                raw = call_groq_sdk(sdk_client, model, JUDGE_SYSTEM_PROMPT, user_prompt)
            else:
                raw = call_groq_http(api_key, model, JUDGE_SYSTEM_PROMPT, user_prompt)
            verdict = extract_json(raw)
            # validate / coerce scores
            out = {"id": record["id"]}
            for key in ("faithfulness", "correctness", "answer_relevancy"):
                v = float(verdict[key])
                if v not in (0, 0.5, 1):
                    raise ValueError(f"{key} out of range: {v}")
                out[key] = v
            out["rationale"] = str(verdict.get("rationale", ""))[:300]
            return out
        except Exception as e:  # noqa: BLE001 - want to catch and retry any transient failure
            last_err = e
            time.sleep(RETRY_BASE_DELAY * attempt)
    return {"id": record["id"], "faithfulness": None, "correctness": None,
            "answer_relevancy": None, "rationale": f"JUDGE_FAILED: {last_err}"}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 4) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="/results/raw_results.json")
    ap.add_argument("outdir", nargs="?", default="/results")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = [r for r in data if "error" not in r and "answer" in r]
    skipped = [r.get("id", "?") for r in data if r not in records]

    import os
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Set GROQ_API_KEY in your environment first: export GROQ_API_KEY=gsk_...")

    sdk_client = Groq(api_key=api_key) if _HAS_SDK else None

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(judge_one, r, args.model, api_key, sdk_client): r["id"]
            for r in records
        }
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            print(f"[{i}/{len(records)}] {res['id']}: "
                  f"F={res['faithfulness']} C={res['correctness']} R={res['answer_relevancy']}")

    results.sort(key=lambda r: r["id"])

    # write per-question CSV
    import csv
    csv_path = outdir / "generation_judgments_groq.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "faithfulness", "correctness", "answer_relevancy", "rationale"])
        for r in results:
            w.writerow([r["id"], r["faithfulness"], r["correctness"], r["answer_relevancy"], r["rationale"]])

    failed = [r["id"] for r in results if r["faithfulness"] is None]

    summary = {
        "model": args.model,
        "n_questions_in_file": len(data),
        "n_skipped_errored_records": len(skipped),
        "skipped_ids": skipped,
        "n_judged": len(results) - len(failed),
        "n_judge_failures": len(failed),
        "failed_ids": failed,
        "faithfulness_mean": mean([r["faithfulness"] for r in results]),
        "correctness_mean": mean([r["correctness"] for r in results]),
        "answer_relevancy_mean": mean([r["answer_relevancy"] for r in results]),
    }
    (outdir / "generation_metrics_groq_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nPer-question results: {csv_path}")


if __name__ == "__main__":
    main()