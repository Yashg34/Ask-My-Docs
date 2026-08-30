from typing import TypedDict, List, Dict, Any, Optional


class GraphState(TypedDict):
    # Request params
    query: str
    search_query: str
    top_k: int
    top_n: int
    threshold: float
    chat_history: List[Dict[str, str]]

    # Routing
    intent: str
    is_supported: bool  # domain-relevance check (telemetry only)

    # Guardrails
    is_safe: bool
    security_flag: str

    # User and document context
    user_id: str
    document_id: str

    # Retrieved data
    retrieved_chunks: List[Dict[str, Any]]
    formatted_context: str

    # Generation and validation loop
    draft_answer: Optional[str]
    validation_feedback: Optional[str]
    is_valid: bool
    revision_count: int
