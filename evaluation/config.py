import os
from pathlib import Path
from dotenv import load_dotenv

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
GOLDEN_DATASET_PATH = EVAL_DIR / "golden_dataset.json"

load_dotenv(EVAL_DIR.parent / ".env")   # shared repo-root .env (single source of truth)
load_dotenv(EVAL_DIR / ".env")          # fallback: local evaluation/.env


class EvalSettings:
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
    EVAL_EMAIL = os.environ.get("EVAL_EMAIL", "")
    EVAL_PASSWORD = os.environ.get("EVAL_PASSWORD", "")
    DOCUMENT_ID = os.environ.get("DOCUMENT_ID") or None

    BATCH_SIZE = int(os.environ.get("BATCH_SIZE", 8))
    SLEEP_BETWEEN_BATCHES_SEC = float(os.environ.get("SLEEP_BETWEEN_BATCHES_SEC", 8))
    REQUEST_TIMEOUT_SEC = float(os.environ.get("REQUEST_TIMEOUT_SEC", 90))

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "groq/openai/gpt-oss-120b")
    JUDGE_CONCURRENCY = int(os.environ.get("JUDGE_CONCURRENCY", 5))
    JUDGE_TIMEOUT_SEC = float(os.environ.get("JUDGE_TIMEOUT_SEC", 30))
    JUDGE_PACE_DELAY_SEC = float(os.environ.get("JUDGE_PACE_DELAY_SEC", 1.5))

settings = EvalSettings()
RESULTS_DIR.mkdir(exist_ok=True)

if not settings.EVAL_EMAIL or not settings.EVAL_PASSWORD:
    raise RuntimeError(
        "EVAL_EMAIL and EVAL_PASSWORD must be set. "
        "Copy evaluation/env.sample to evaluation/.env and fill them in before running the harness."
    )