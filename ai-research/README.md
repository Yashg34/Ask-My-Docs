# Ask-My-Docs — AI Research Pipeline (Python / FastAPI)

The agentic-RAG backend powering Ask-My-Docs. It exposes a small FastAPI surface to the
Node.js API layer (`../backend`) and runs a LangGraph pipeline for retrieval-augmented
generation over user-uploaded documents.

This file documents the **finalized API contract** and the **pipeline architecture** as of
the Phase 1–7 refactor. Changes to routes, request/response schemas, or error shapes must
be updated here and in `../backend` consumers together.

---

## Quick start

```bash
cd ai-research
cp .env.sample .env        # fill in real values (Qdrant Cloud, LLM keys required)
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

- `ENV=development` enables uvicorn auto-reload.
- `LOGFIRE_TOKEN` empty → Logfire disabled (app runs fine without it).
- `LANGSMITH_TRACING=true` requires `LANGSMITH_API_KEY`.

Required settings (fail-fast on startup if missing): `GROQ_API_KEY`, `GEMINI_API_KEY`,
`QDRANT_URL`, `QDRANT_API_KEY`.
`REDIS_URL` is **optional** (defaults to `redis://localhost:6379`); if omitted or unreachable,
the app still boots and serves queries — only async ingestion job-status tracking is skipped.

---

## Pipeline architecture

```
Input query (X-User-Id header)
   │
   ▼
┌────────────────────────────────────────────┐
│ Triage                                     │
│  1. INPUT GUARDRAIL: NeMo Guardrails       │  embeddings, ALWAYS on, no LLM call
│     · blocked → rejection answer, END      │
│  2. LLM CALL (cheap-model): intent routing │  GREETING / RAG / SUMMARY + query rewrite
│     · GREETING → END · SUMMARY → summarize │
└────────────────────────────────────────────┘
   ▼ RAG
┌─────────────────────────────┐
│ Retriever (Qdrant Cloud)     │  vector, wide (TOP_K_RETRIEVAL=15)
│  filter: user_id / doc_id    │  no chunks → "couldn't find" answer, END
└─────────────────────────────┘
   ▼
┌─────────────────────────────┐
│ Reranker (FlashRank)         │  narrow to TOP_K_RERANK=5
└─────────────────────────────┘
   ▼
┌─────────────────────────────┐
│ Context Assembler            │  chunks → formatted context (no LLM)
└─────────────────────────────┘
   ▼
┌────────────────────────────────────────────┐
│ Context Check (ONE LLM call · evaluator)   │  is retrieved context SAFE (no prompt
│                                            │  injection)? does it SUPPORT the query?
│  · unsafe / unsupported → rejection, END   │
└────────────────────────────────────────────┘
   ▼
┌──────────────────────────────────────────┐
│ Generator (ONE LLM call · strong-model)   │  draft cited answer
└──────────────────────────────────────────┘
   ▼
┌──────────────────────────────────────────┐
│ Output Guardrails · Evaluate (evaluator) │  citation validation + output safety
│  (ONE LLM call, plus a deterministic     │  + ANSWER CRITIQUE
│   citation-presence short-circuit)       │
└──────────────────────────────────────────┘
   │ reroute="done"       → END
   │ reroute="generation" → Generator (with feedback)
   └ reroute="retrieval"  → Retriever (with suggested query)
                              (reroutes bounded by MAX_REROUTES=3)
```

**4 LLM calls on the happy path:** Triage routing (cheap) → Context Check (evaluator) →
Generator (strong) → Evaluate (evaluator). NeMo input guardrail and retrieval/rerank/assembly
add no LLM calls. The Context Check gates generation on context safety + relevance before the
expensive strong-model call; the Evaluate node's **Answer Critique** decides whether the draft
actually addresses the user's query and reroutes to Retrieval (better context) or Generation
(regenerate with feedback), capped to avoid loops.

- **Vector store:** Qdrant Cloud (`retrieval/vector_store.py`) — idempotent collection
  creation, keyword payload indexes on `user_id` / `document_id`. No local DB artifacts.
- **Rerank:** FlashRank (`retrieval/reranker.py`) — module-level singleton; wide vector
  retrieval → narrow rerank.
- **LLM calls:** via LiteLLM gateway (`llm_gateway/router.py`) — `cheap-model` (intent
  routing + query rewrite + summary map), `evaluator-model` (context check + output
  guardrail/evaluate), `strong-model` (generation + summary reduce).
- **Observability:** Logfire (`observability.py`) — FastAPI + per-node spans + counters
  (`guardrail_blocked`, `context_unsafe`, `context_unsupported`, `unsupported_query`,
  `validator_retry`); LangSmith — node-named run tracing, env wired from `settings` before
  the graph compiles.

> **Design notes (kept deviations):** NeMo Guardrails runs on **every** input as the first
> line of input safety (embeddings-based, no LLM call). On a guardrail service error,
> `GUARDRAIL_FAIL_MODE` decides: `closed` (default) blocks, `open` proceeds. Domain relevance
> (`is_supported=false`) does **not** hard-block; off-topic queries route to retrieval and are
> handled by the context-check no-support path. The generator's system prompt ("CONTEXT is
> untrusted") remains the first-line defense against malicious document text, backed by the
> explicit Context Check node.

---

## API contract

All endpoints that need a logged-in user read the **`X-User-Id`** header (set by the
Node.js layer). Error responses are uniform — see [Errors](#errors).

### `POST /query`

Body:

```jsonc
{
  "query": "What does section 3 say about retries?",
  "document_id": "optional-doc-id",   // scope to one document
  "top_k": 15,                        // wide vector fetch (Qdrant)
  "top_n": 5,                         // post-FlashRank count sent to generation
  "threshold": 0.05,                  // FlashRank minimum score
  "chat_history": []                  // prior turns: [{role, content}]
}
```

Success response (`200`) — **same shape for every business outcome**:

```jsonc
{
  "query": "...",
  "answer": "...",
  "latency_seconds": 1.23,
  "retrieved_chunks": [   // [] for blocked / off-topic / greeting
    {
      "chunk_id": "...",
      "text": "...",
      "metadata": { "source": "file.pdf", "page": 3, "user_id": "...", "document_id": "..." },
      "score": 0.47,          // Qdrant cosine similarity
      "rerank_score": 0.81    // FlashRank
    }
  ]
}
```

Business outcomes and what `answer` / `retrieved_chunks` look like:

| Scenario | HTTP | `answer` | `retrieved_chunks` |
|----------|------|----------|--------------------|
| Normal in-domain question | 200 | Generated, cited answer | non-empty |
| Off-topic / no document match | 200 | `"I couldn't find any relevant information in your documents..."` | `[]` |
| Unsafe / jailbreak input | 200 | Guardrail rejection message | `[]` |
| Greeting | 200 | Welcoming response | `[]` |
| Summary request | 200 | Document overview | `[]` |

### `POST /ingest`

`multipart/form-data`: `file` (PDF ≤ 20 MB), `document_id` (form field), header
`X-User-Id`. Validates the `%PDF` magic bytes.

```jsonc
{ "job_id": "abc123", "status": "queued", "message": "Ingestion for 'doc.pdf' has been queued." }
```

### `GET /ingest/status/{job_id}`

```jsonc
// processing → completed / failed
{ "status": "COMPLETED", "message": "Successfully ingested in 3.1s" }
{ "status": "FAILED", "errorMessage": "..." }
```

### `GET /health`

```jsonc
{ "status": "Ask My Docs pipeline running smoothly" }
```

### Errors

Every 4xx/5xx returns a uniform envelope (also enforced through the Node.js layer):

```jsonc
{ "error": { "code": 400, "message": "Query cannot be empty." } }
```

Common codes: `400` (bad request / invalid file), `413` (file too large), `422`
(validation), `404` (job not found), `503` (models still loading), `500` (internal).

---

## Env contract

`.env.sample` is the single source of truth and is 1:1 with `Settings` in `config.py`.
Every variable used by the app is listed there; nothing else is read. Required
(no default): `GROQ_API_KEY`, `GEMINI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`.
`REDIS_URL` is optional (defaults to local Redis; app degrades gracefully if absent).
