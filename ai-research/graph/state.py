from typing import TypedDict, List, Dict, Any, Optional

from httpcore import request

class GraphState(TypedDict):
    # Initial request parameters
    query: str
    search_query: str
    top_k: int
    top_n: int
    threshold: float

    # Guardrails 
    is_safe: bool          
    security_flag: str

    # User and document context
    user_id: str              
    document_id: str
    
    # Retrieved data
    retrieved_chunks: List[Dict[str, Any]]
    formatted_context: str         

    # Generation and Validation loop
    draft_answer: Optional[str]
    validation_feedback: Optional[str]
    is_valid: bool
    revision_count: int