import asyncio
import json
import re
import random

import litellm
from pydantic import BaseModel
from tqdm.asyncio import tqdm_asyncio  # <-- tqdm for async

from config import settings

JUDGE_PROMPT = """You are grading a RAG system's answer. Score each on 0, 0.5, or 1.

QUESTION: {question}

RETRIEVED CONTEXT:
{context}

GROUND TRUTH ANSWER: {ground_truth}

MODEL'S ANSWER: {answer}

Score:
- faithfulness: is every claim in the model's answer supported by the retrieved context? (1=fully grounded, 0.5=partially, 0=hallucinated/unsupported)
- answer_correctness: does the model's answer match the substance of the ground truth? (1=correct, 0.5=partially correct, 0=wrong)
- answer_relevancy: does the answer actually address the question asked? (1=on-topic, 0.5=partially, 0=off-topic)

Respond ONLY with JSON: {{"faithfulness": <float>, "faithfulness_reason": "<one line>", "answer_correctness": <float>, "correctness_reason": "<one line>", "answer_relevancy": <float>, "relevancy_reason": "<one line>"}}"""


class GenerationScores(BaseModel):
    faithfulness: float
    faithfulness_reason: str
    answer_correctness: float
    correctness_reason: str
    answer_relevancy: float
    relevancy_reason: str


def _judge_failure(error: Exception, phase: str = "call") -> dict:
    return {
        "faithfulness": None, "faithfulness_reason": f"judge {phase} error: {error}",
        "answer_correctness": None, "correctness_reason": "",
        "answer_relevancy": None, "relevancy_reason": "",
    }


async def judge_one(item: dict, semaphore: asyncio.Semaphore, max_retries: int = 20) -> dict:
    context = "\n---\n".join(c["text"] for c in item["retrieved_chunks"])
    prompt = JUDGE_PROMPT.format(
        question=item["question"], context=context,
        ground_truth=item["ground_truth_answer"], answer=item["answer"],
    )

    for attempt in range(max_retries):
        try:
            async with semaphore:
                resp = await litellm.acompletion(
                    model=settings.JUDGE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    api_key=settings.GROQ_API_KEY,
                    timeout=90,
                )
                
                # THE MAGIC PACER: 60 seconds / 4.5 requests = ~13.5 seconds
                # Yeh script ko automatically 1 min mein sirf 4-5 requests bhejney dega
                await asyncio.sleep(14.0)

            raw = resp.choices[0].message.content
            scores = GenerationScores(**json.loads(raw))
            return scores.model_dump()

        except litellm.RateLimitError as e:
            wait = 15.0 # Fallback wait
            m = re.search(r"try again in ([\d.]+)s", str(e))
            if m:
                # Add extra buffer time to Groq's requested wait
                wait = float(m.group(1)) + 3.0 
            
            if attempt < max_retries - 1:
                await asyncio.sleep(wait)
                continue
            return _judge_failure(e, phase="ratelimit")

        except (litellm.Timeout, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(5.0)
                continue
            return _judge_failure(e, phase="timeout")

        except Exception as e:
            return _judge_failure(e)

    return _judge_failure(RuntimeError(f"exhausted {max_retries} retries"))

async def score_generation_batch(items: list[dict]) -> list[dict]:
    # CRITICAL: Force concurrency down to survive Groq's 8000 TPM limit
    safe_concurrency = min(getattr(settings, "JUDGE_CONCURRENCY", 2), 2)
    semaphore = asyncio.Semaphore(safe_concurrency)
    
    # Removed 'return_exceptions=True' because tqdm doesn't support it 
    # and judge_one already handles its own exceptions safely.
    results = await tqdm_asyncio.gather(
        *(judge_one(item, semaphore) for item in items),
        desc="Judging Answers (Groq)"
    )
    return [r if not isinstance(r, Exception) else _judge_failure(r) for r in results]