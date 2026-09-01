"""Centralized env/config via pydantic-settings (single import point for settings)."""

import os
import sys

# Force UTF-8 stdout so emoji status prints don't crash on Windows (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized settings loaded from environment variables and .env file.
    """

    # ========== LLM Provider Keys ==========
    GROQ_API_KEY: str = Field(
        description="GROQ API key for cheap-model and evaluator-model (via LiteLLM)"
    )
    GEMINI_API_KEY: str = Field(
        description="Google Gemini API key for strong-model (via LiteLLM)"
    )
    HF_TOKEN: str = Field(
        default="",
        description="Hugging Face token (optional, for sentence-transformers model downloads)"
    )

    # ========== Vector Store (Qdrant Cloud) ==========
    QDRANT_URL: str = Field(
        description="Qdrant Cloud instance URL (e.g., https://xxx-xxx.aws.cloud.qdrant.io:6333)"
    )
    QDRANT_API_KEY: str = Field(
        description="Qdrant Cloud API key"
    )
    QDRANT_COLLECTION_NAME: str = Field(
        default="master_docs",
        description="Qdrant collection name for document embeddings"
    )

    # ========== Redis (Job Queue) ==========
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL for background job tracking (optional; app degrades if absent)"
    )

    # ========== Guardrails (NeMo Guardrails) ==========
    NEMO_GUARDRAILS_CONFIG_PATH: str = Field(
        default="guardrails",
        description="Path to NeMo Guardrails config directory (contains config.yml and rails/*.co)"
    )

    GUARDRAIL_FAIL_MODE: str = Field(
        default="closed",
        description="Guardrail behavior on LLM error: 'closed' (block, default) or 'open' (proceed)"
    )

    # Optional token guarding the soft-config endpoints (sent as X-Admin-Token);
    # empty = open (dev convenience).
    ADMIN_API_TOKEN: str = Field(
        default="",
        description="Optional bearer token for the soft-config endpoints (sent as X-Admin-Token)"
    )

    # ========== Observability (Logfire + LangSmith) ==========
    LOGFIRE_TOKEN: str = Field(
        default="",
        description="Logfire token (Pydantic Logfire). Leave empty to disable Logfire."
    )

    LANGSMITH_TRACING: bool = Field(
        default=False,
        description="Set to true to enable LangSmith tracing of LangChain/LangGraph runs"
    )
    LANGSMITH_ENDPOINT: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith API endpoint"
    )
    LANGSMITH_API_KEY: str = Field(
        default="",
        description="LangSmith API key"
    )
    LANGSMITH_PROJECT: str = Field(
        default="ask-my-docs",
        description="LangSmith project name for trace organization"
    )

    # ========== App Configuration ==========
    ENV: str = Field(
        default="production",
        description="Environment mode: 'development' enables uvicorn reload"
    )

    TOP_K_RETRIEVAL: int = Field(
        default=15,
        description="Chunks fetched from vector store (wide retrieval)"
    )

    TOP_K_RERANK: int = Field(
        default=5,
        description="Chunks kept after reranking (narrow precision)"
    )

    CHUNK_SIZE: int = Field(
        default=1500,
        description="Character count for document chunking during ingestion"
    )

    CHUNK_OVERLAP: int = Field(
        default=200,
        description="Character overlap between consecutive chunks"
    )

    # ========== CORS Configuration ==========
    ALLOWED_ORIGINS: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins, or '*' for all"
    )

    # ========== Pydantic Settings Configuration ==========
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )



try:
    settings = Settings()
except Exception as e:
    print("=" * 70)
    print("❌ CONFIGURATION ERROR: Failed to load environment variables")
    print("=" * 70)
    print(f"\nError: {e}\n")
    print("Please ensure your .env file exists and contains all required variables.")
    print("Refer to .env.sample for the complete list of required settings.\n")
    print("=" * 70)
    raise  # Re-raise to prevent the app from starting with broken config

# ========== Provider credentials visible to LiteLLM ==========
for _key in ("GROQ_API_KEY", "GEMINI_API_KEY", "HF_TOKEN", "QDRANT_API_KEY"):
    _value = getattr(settings, _key, None)
    if _value and not os.environ.get(_key):
        os.environ[_key] = _value
