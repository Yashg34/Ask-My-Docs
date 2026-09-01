from langgraph.graph import StateGraph, END
from graph.state import GraphState
from nodes.triage import triage
from nodes.retriever_node import retrieve_documents
from nodes.reranker_node import rerank_documents
from nodes.context_assembler import assemble_context
from nodes.generator_node import generate_answer
from nodes.context_check import check_context
from nodes.evaluator import evaluate
from nodes.summarise import summarize_document
from observability import logfire_span, increment_counter
import inspect

# Max times the evaluate loop may reroute back to retrieval/generation.
MAX_REROUTES = 3


# Wrap each node with a Logfire span 
def _with_span(node_func, span_name: str):
    async def wrapped(state):
        with logfire_span(span_name, node=span_name):
            result = node_func(state) 
            if inspect.isawaitable(result):
                result = await result
            return result
    return wrapped


spanned = {
    "triage":      _with_span(triage, "triage"),
    "retriever":   _with_span(retrieve_documents, "retriever_node"),
    "reranker":    _with_span(rerank_documents, "reranker_node"),
    "assembler":   _with_span(assemble_context, "context_assembler"),
    "context_check": _with_span(check_context, "context_check"),
    "generator":   _with_span(generate_answer, "generator_node"),
    "evaluate":    _with_span(evaluate, "evaluator"),
    "summarize":   _with_span(summarize_document, "summarize_node"),
}


# --- Routing logic ---
def intent_router(state: GraphState):
    if state.get("is_safe") is False:
        return END
    if state.get("intent") == "GREETING":
        return END
    if state.get("intent") == "SUMMARY":
        return "summarize"
    return "retriever"


def route_after_retrieval(state: GraphState):
    if not state.get("retrieved_chunks", []):
        print("🔀 [Router] No chunks found! Bypassing generation and ending.")
        return END
    print("🔀 [Router] Chunks found. Proceeding to Reranker.")
    return "reranker"


def context_router(state: GraphState):
    # Context check gate: only generate when the retrieved context is safe AND
    # actually supports the user's query (blocked / unsupported already set a
    # draft_answer and cleared retrieved_chunks).
    if state.get("context_supports_query") is not True or state.get("context_safe") is False:
        print("🔀 [Router] Context gate blocked — ending without generation.")
        return END
    print("🔀 [Router] Context is safe and supports the query. Proceeding to Generation.")
    return "generator"


def evaluate_router(state: GraphState):
    reroute = state.get("reroute")
    if reroute in ("retrieval", "generation") and state.get("revision_count", 0) < MAX_REROUTES:
        increment_counter("validator_retry")
        print(f"🔄 Evaluate: rerouting to {'retriever' if reroute == 'retrieval' else 'generator'} "
              f"(attempt {state.get('revision_count', 0)}/{MAX_REROUTES})")
        return reroute
    return END


# Build the graph: triage (safety+route) → retrieval → generation → evaluate (with reroutes).
workflow = StateGraph(GraphState)

workflow.add_node("triage", spanned["triage"])
workflow.add_node("retriever", spanned["retriever"])
workflow.add_node("reranker", spanned["reranker"])
workflow.add_node("assembler", spanned["assembler"])
workflow.add_node("context_check", spanned["context_check"])
workflow.add_node("generator", spanned["generator"])
workflow.add_node("evaluate", spanned["evaluate"])
workflow.add_node("summarize", spanned["summarize"])

workflow.set_entry_point("triage")
workflow.add_conditional_edges(
    "triage",
    intent_router,
    {
        END: END,
        "summarize": "summarize",
        "retriever": "retriever",
    },
)
workflow.add_edge("summarize", END)
workflow.add_conditional_edges(
    "retriever",
    route_after_retrieval,
    {
        "reranker": "reranker",
        END: END,
    },
)
workflow.add_edge("reranker", "assembler")
workflow.add_edge("assembler", "context_check")
workflow.add_conditional_edges(
    "context_check",
    context_router,
    {
        END: END,
        "generator": "generator",
    },
)
workflow.add_edge("generator", "evaluate")
workflow.add_conditional_edges(
    "evaluate",
    evaluate_router,
    {
        END: END,
        "retriever": "retriever",
        "generator": "generator",
    },
)

app = workflow.compile()
