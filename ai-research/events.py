"""Real-time event streaming for the RAG query pipeline.

LangGraph nodes push {stage, message} events here and the FastAPI SSE endpoint
(`/query/events/{query_id}`) streams them to the Node.js gateway. Uses
in-process queues so no Redis is required for single-process deployments.
"""

import queue as _queue
import time

_query_queues: dict[str, _queue.Queue] = {}
_query_results: dict[str, dict] = {}  # last-known event per query (late-connect fallback)

# Human-friendly labels for the LangGraph node/span names emitted by build_graph.
_STAGE_LABELS = {
    "triage": "Analyzing your question",
    "retriever_node": "Searching your documents",
    "reranker_node": "Ranking the best matches",
    "context_assembler": "Assembling context",
    "context_check": "Verifying context safety",
    "generator_node": "Writing your answer",
    "evaluator": "Reviewing answer quality",
    "summarize_node": "Summarizing your document",
}


def register_query_events(query_id: str) -> _queue.Queue:
    """Register a queue for a query; the SSE endpoint consumes from it."""
    q = _queue.Queue()
    _query_queues[query_id] = q
    return q


def clear_query_events(query_id: str):
    """Remove the queue + cached result once a query stream has finished."""
    _query_queues.pop(query_id, None)
    _query_results.pop(query_id, None)


def emit_query_event(query_id: str, stage: str, message: str = ""):
    """Push a stage event. No-ops when no query_id or no subscriber."""
    if not query_id:
        return
    event = {
        "stage": stage,
        "message": message or _STAGE_LABELS.get(stage, stage),
        "ts": round(time.time(), 3),
    }
    _query_results[query_id] = event  # allow a late-connecting SSE to catch up
    q = _query_queues.get(query_id)
    if q:
        q.put(event)


def mark_query_done(query_id: str, message: str = "Query complete"):
    """Terminal event emitted after the graph finishes."""
    if not query_id:
        return
    emit_query_event(query_id, "done", message)


def latest_query_event(query_id: str):
    """Most recent event for a query (used by a late-connecting SSE client)."""
    return _query_results.get(query_id)