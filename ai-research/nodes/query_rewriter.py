from graph.state import GraphState
from llm_gateway.router import llm_router

def rewrite_query(state: GraphState):
    print("[Node: Rewriter] Resolving context & extracting keywords...")
    original_query = state["query"]
    chat_history = state.get("chat_history", [])
    
    history_text = ""
    if chat_history:
        for msg in chat_history[-4:]:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

    messages = [
        {
            "role": "system", 
            "content": (
                "You are a strict keyword extraction API. Your job is to extract the most important search keywords for a database query. "
                "CRITICAL INSTRUCTION: You must look at the Chat History. If the user's latest query is a follow-up (e.g., 'and what about X', 'how does it work'), "
                "you MUST include the missing context keywords from the history. "
                "DO NOT write sentences. DO NOT write questions. ONLY output space-separated keywords."
            )
        },
        {"role": "user", "content": "Chat History:\nNone\n\nLatest: How do I reset my password for the company portal?"},
        {"role": "assistant", "content": "reset password company portal"},
        
        {"role": "user", "content": "Chat History:\nUser: What is Apple's total revenue in 2023?\nAssistant: Apple's revenue was $383 Billion.\n\nLatest: And what about Microsoft?"},
        {"role": "assistant", "content": "Microsoft total revenue 2023"}, 
        
        # The actual query
        {"role": "user", "content": f"Chat History:\n{history_text or 'None'}\n\nLatest: {original_query}"}
    ]
    
    try:
        response = llm_router.completion(
            model="cheap-model", 
            messages=messages,
            temperature=0.1
        )
        
        optimized_query = response.choices[0].message.content.strip()
        print(f"   -> Original: {original_query}")
        print(f"   -> Optimized (Context Aware): {optimized_query}")
        
        return {"search_query": optimized_query}
        
    except Exception as e:
        print(f"Rewriter Error: {e}. Falling back to original.")
        return {"search_query": original_query}