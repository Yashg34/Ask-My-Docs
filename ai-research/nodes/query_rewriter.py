from graph.state import GraphState
from llm_gateway.router import llm_router

def rewrite_query(state: GraphState):
    print("[Node: Rewriter] Optimizing query using cheap-model...")
    original_query = state["query"]
    
    messages = [
        {
            "role": "system", 
            "content": (
                "You are a strict keyword extraction API. Your ONLY job is to extract the 3-5 most important search keywords from the user's query. "
                "DO NOT write sentences. DO NOT write questions. DO NOT use grammar. ONLY output space-separated keywords."
            )
        },
        # Few-shot examples
        {"role": "user", "content": "How do I reset my password for the company portal?"},
        {"role": "assistant", "content": "reset password company portal"},
        {"role": "user", "content": "If I select a control enhancement, do I still need the base control?"},
        {"role": "assistant", "content": "control enhancement base control"},
        
        # The actual query
        {"role": "user", "content": original_query}
    ]
    response = llm_router.completion(
        model="cheap-model", 
        messages=messages
    )
    
    optimized_query = response.choices[0].message.content.strip()
    print(f"   Original: {original_query}")
    print(f"   Optimized: {optimized_query}")
    
    return {"search_query": optimized_query}