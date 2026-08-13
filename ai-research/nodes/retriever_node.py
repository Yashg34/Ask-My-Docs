from graph.state import GraphState
from retrieval.vector_retriever import VectorRetriever
from retrieval.bm25_retriever import BM25Retriever
from retrieval.fusion import reciprocal_rank_fusion

# Initialize globally for this node
vec_retriever = VectorRetriever()
bm25_retriever = BM25Retriever()

def retrieve_documents(state: GraphState):
    print("🔍 [Node: Retriever] Fetching candidates via Vector & BM25...")
    query = state["query"]
    
    vec_results = vec_retriever.retrieve(query, top_k=state.get("top_k", 10))
    bm_results = bm25_retriever.retrieve(query, top_k=state.get("top_k", 10))
    
    fused = reciprocal_rank_fusion(vec_results, bm_results)
    
    # Update state
    return {"retrieved_chunks": fused}