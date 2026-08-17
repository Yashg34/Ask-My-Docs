from graph.state import GraphState
from retrieval.reranker import CrossEncoderReranker

reranker = CrossEncoderReranker()

def rerank_documents(state: GraphState):
    print("[Node: Reranker] Filtering noise via Cross-Encoder...")
    candidates = state["retrieved_chunks"]
    
    final_chunks = reranker.rerank(
        query=state["query"], 
        candidates=candidates, 
        top_n=state.get("top_n", 3), 
        threshold=state.get("threshold", 0.05)
    )
    
    return {"retrieved_chunks": final_chunks}