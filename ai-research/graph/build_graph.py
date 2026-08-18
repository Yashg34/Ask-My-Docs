from langgraph.graph import StateGraph, END
from graph.state import GraphState
from nodes.retriever_node import retrieve_documents
from nodes.reranker_node import rerank_documents
from nodes.context_assembler import assemble_context
from nodes.generator_node import generate_answer
from nodes.citation_validator import validate_citations 
from nodes.query_rewriter import rewrite_query
from nodes.input_guardrail import check_input_safety
from nodes.intent_routing import route_intent
from nodes.summarise import summarize_document
from nodes.context_safety_guardrail import check_context_safety

# Routing Logic
def route_validation(state: GraphState):
    if state.get("is_valid"):
        print("✅ Graph Routing: Answer is valid. Ending process.")
        return END
    
    if state["revision_count"] >= 3:
        print("🛑 Graph Routing: Revision cap hit! Forcing stop to prevent infinite loops.")
        return END
        
    print("🔄 Graph Routing: Validation failed. Routing back to Generator...")
    return "generator"

def guardrail_router(state: GraphState):
    if state.get("is_safe") is False:
        return END
    return "rewriter"

def route_context_safety(state: GraphState):
    if state.get("is_safe") is False:
        return END
    return "generator"

def intent_router(state: GraphState):
    if state.get("intent") == "GREETING":
        print("Graph Routing: Intent is GREETING. Bypassing RAG and ending.")
        return END
    elif state.get("intent") == "SUMMARY":
        print("Graph Routing: Intent is SUMMARY. Proceeding to Input Guardrail.")
        return "summarize"
    print("📚 Graph Routing: Intent is RAG. Proceeding to Input Guardrail.")
    return "guardrail"

def route_after_retrieval(state: GraphState):
    chunks = state.get("retrieved_chunks", [])
    
    if not chunks:
        print("🔀 [Router] No chunks found! Bypassing generation and ending.")
        return END
        
    print("🔀 [Router] Chunks found. Proceeding to Generation.")
    return "reranker"

# Construct the Graph
workflow = StateGraph(GraphState)

# Add Nodes
workflow.add_node("retriever", retrieve_documents)
workflow.add_node("reranker", rerank_documents)
workflow.add_node("assembler", assemble_context)
workflow.add_node("generator", generate_answer)
workflow.add_node("validator", validate_citations)
workflow.add_node("rewriter", rewrite_query)
workflow.add_node("guardrail", check_input_safety)
workflow.add_node("router", route_intent)
workflow.add_node("summarize", summarize_document)
workflow.add_node("context_guardrail", check_context_safety)

# Define the straight-line flow
workflow.set_entry_point("router")
workflow.add_conditional_edges(
    "router",
    intent_router,
    {
        END: END,
        "summarize": "summarize",
        "guardrail": "guardrail"
    }
)
workflow.add_edge("summarize", END)
workflow.add_conditional_edges(
    "guardrail",
    guardrail_router,
    {
        END: END,
        "rewriter": "rewriter"
    }
)
workflow.add_edge("rewriter", "retriever")
workflow.add_conditional_edges(
    "retriever",            
    route_after_retrieval,  
    {
        "reranker": "reranker", 
        END: END               
    }
)
workflow.add_edge("reranker", "assembler")
workflow.add_edge("assembler", "context_guardrail")
workflow.add_conditional_edges(
    "context_guardrail",
    route_context_safety,
    {
        END: END,
        "generator": "generator"
    }
)
workflow.add_edge("generator", "validator")

# Add the Conditional Loop
workflow.add_conditional_edges(
    "validator",
    route_validation,
    {
        END: END,
        "generator": "generator"
    }
)

# Compile the Graph
app = workflow.compile()


# To print the graph visually using mermaid
if __name__ == "__main__":
    try:
        image_data = app.get_graph().draw_mermaid_png()
        
        image_path = "langgraph_architecture.png"
        with open(image_path, "wb") as f:
            f.write(image_data)
            
        print(f"📸 Success! Graph architecture image saved as '{image_path}'")
    except Exception as e:
        print(f"❌ Failed to save graph image: {e}")
        print("Tip: Ensure you have an active internet connection as draw_mermaid_png() uses an external API by default.")