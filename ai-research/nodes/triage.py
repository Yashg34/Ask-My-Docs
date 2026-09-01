"""Input stage: NeMo input guardrail (ALWAYS on) → one cheap-model LLM call for
intent routing + query rewrite. Input safety is handled by the NeMo rail, so this
LLM call no longer does security classification."""

from typing import Literal
from graph.state import GraphState
from config import settings
from pydantic import BaseModel, Field
from nodes.utils import parse_structured
from llm_gateway.router import llm_router
from observability import increment_counter

REJECTION_MESSAGE = (
    "I'm sorry, but I can't process that request — it looks like it may contain "
    "instructions that could compromise my safety. Please rephrase your question."
)


class RoutingResult(BaseModel):
    """Outcome of the intent-routing + query-rewrite LLM call. Input safety is not
    judged here — the NeMo input rail handles that before this call runs."""

    intent: Literal["GREETING", "RAG", "SUMMARY"] = Field(
        description="'GREETING' for casual hellos/thanks, 'RAG' for document questions, or 'SUMMARY' for overview requests."
    )
    is_supported: bool = Field(
        description=(
            "True if the query is about the UPLOADED DOCUMENTS. False if it is a general question, web search "
            "request, or coding help unrelated to the docs that cannot be answered from the document collection alone."
        )
    )
    reason: str = Field(
        default="", description="If is_supported=False, brief explanation of why the query is out of scope."
    )
    greeting_response: str = Field(
        default="", description="If intent is GREETING, a short polite welcoming response. Empty otherwise."
    )
    search_query: str = Field(
        default="",
        description=(
            "If intent is RAG and is_supported=True, optimized space-separated search keywords derived from the "
            "query and chat history. Empty otherwise."
        ),
    )


async def triage(state: GraphState):
    """1) Always run the NeMo input guardrail (embeddings-based, no LLM call).
    2) Then one cheap-model LLM call for intent routing + query rewrite."""
    query = state["query"]
    chat_history = state.get("chat_history", [])

    # ---- 1) INPUT GUARDRAIL: NeMo Guardrails (always on) ----
    from guardrails.guardrails_service import get_guardrails_service
    gr = await get_guardrails_service().check_input(query)
    if not gr.allowed:
        blocked_flow = gr.blocked_flow or "blocked"
        # Only a guardrail SERVICE ERROR can be overridden by GUARDRAIL_FAIL_MODE=open;
        # a genuine safety block always holds (fail-closed for real threats).
        if blocked_flow != "error_fail_closed" or settings.GUARDRAIL_FAIL_MODE == "closed":
            print(f"🚨 INPUT GUARDRAIL blocked query ({blocked_flow})")
            increment_counter("guardrail_blocked")
            return {
                "is_safe": False,
                "security_flag": blocked_flow,
                "draft_answer": gr.reason or REJECTION_MESSAGE,
            }
        # guardrail service error + fail_mode=open → fall through to routing.
        print("⚠️ NeMo input guardrail unavailable — fail_mode=open, proceeding")
        increment_counter("guardrail_unavailable")

    # ---- 2) INTENT ROUTING + QUERY REWRITE (cheap model) ----
    history_text = ""
    if isinstance(chat_history, list):
        # Skip malformed history entries so a bad message never 500s the query.
        for msg in chat_history[-4:]:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "user").capitalize()
            content = str(msg.get("content") or "")
            history_text += f"{role}: {content}\n"

    prompt = f"""
You route a user's input to a technical document assistant and, when needed, rewrite it
into search keywords. Produce ALL of these decisions in one pass:
1. INTENT: GREETING, RAG, or SUMMARY.
2. DOMAIN: does it concern the UPLOADED DOCUMENTS?
3. If RAG + in-domain, rewrite it into optimal search keywords.

Intent classification:
- GREETING: casual greetings, thanks, pleasantries.
- RAG: specific questions asking for facts, document details, code snippets, or focused explanations.
- SUMMARY: requests for a general overview or abstract of the entire document.

Domain relevance (is_supported):
Set is_supported=True ONLY if the query asks for information that would be IN THE UPLOADED DOCUMENTS.
Set is_supported=False for general web search, coding help unrelated to the docs, current events,
news, weather, or anything outside the document domain.

Query rewriting (only for RAG + is_supported=True):
Extract the most important space-separated search keywords. Use the Chat History to resolve
follow-ups and include missing context. Do NOT write sentences — keywords only, in `search_query`.

Chat History:
{history_text or 'None'}

User Query: "{query}"
"""

    try:
        response = await llm_router.acompletion(
            model="cheap-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=RoutingResult,
        )
        result = parse_structured(RoutingResult, response.choices[0].message.content)
        print(f"   -> Intent: {result.intent} | Supported: {result.is_supported}")

        if result.intent == "GREETING":
            return {
                "intent": "GREETING",
                "is_safe": True,
                "retrieved_chunks": [],
                "draft_answer": result.greeting_response or "Hello! How can I help you with your documents today?",
            }

        if result.intent == "SUMMARY":
            return {"intent": "SUMMARY", "is_safe": True}

        # RAG: always proceed to retrieval; is_supported is telemetry only.
        if not result.is_supported:
            print(f"   -> Out-of-scope ({result.reason}) — routing to retriever to let retrieval decide")
            increment_counter("unsupported_query")
        return {
            "intent": "RAG",
            "is_safe": True,
            "is_supported": result.is_supported,
            "search_query": result.search_query or query,
        }

    except Exception as e:
        print(f"❌ Routing call failed: {e}")
        increment_counter("guardrail_unavailable")
        if settings.GUARDRAIL_FAIL_MODE == "open":
            print("⚠️ guardrail_fail_mode=open — proceeding as RAG without a routing verdict")
            return {"intent": "RAG", "is_safe": True, "search_query": query}
        print("   Failing closed (GUARDRAIL_FAIL_MODE=closed).")
        return {
            "is_safe": False,
            "security_flag": "guardrail_unavailable",
            "draft_answer": "Our safety check is temporarily unavailable. Please try again shortly.",
        }
