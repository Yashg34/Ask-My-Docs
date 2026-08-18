from graph.state import GraphState
from retrieval.vector_retriever import VectorRetriever
from retrieval.bm25_retriever import BM25Retriever
from retrieval.fusion import reciprocal_rank_fusion

# Initialize globally for this node
vec_retriever = VectorRetriever()
bm25_retriever = BM25Retriever()

def retrieve_documents(state: GraphState):
    print("[Node: Retriever] Fetching candidates via Vector & BM25...")
    query = state["search_query"]
    top_k = state.get("top_k", 10)
    
    user_id = state.get("user_id")
    document_id = state.get("document_id")
    
    if document_id:
        where_filter = {"$and": [{"user_id": user_id}, {"document_id": document_id}]}
    else:
        where_filter = {"user_id": user_id}

    vec_results = vec_retriever.retrieve(query, top_k=top_k, where_filter=where_filter)
    
    # Secure BM25 Search (Fetch extra, filter manually in Python)
    raw_bm_results = bm25_retriever.retrieve(query, top_k=top_k * 5)
    
    bm_results = []
    for chunk in raw_bm_results:
        meta = chunk.get("metadata", {})
        # Strict checking for owner
        if meta.get("user_id") == user_id:
            # If chatting with a specific document, filter by that too
            if document_id and meta.get("document_id") != document_id:
                continue
            bm_results.append(chunk)
            
    bm_results = bm_results[:top_k]
    fused = reciprocal_rank_fusion(vec_results, bm_results)
    
    rev_count = state.get("revision_count", 0)

    if not fused:
        return {
            "retrieved_chunks": [],
            "formatted_context": "",
            "draft_answer": "I couldn't find any relevant information in your documents to answer this question. Could you please rephrase or check if the document contains this info?",
            "is_valid": True,
            "revision_count": rev_count + 1 
        }
    
    return {"retrieved_chunks": fused}