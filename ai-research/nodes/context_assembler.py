from graph.state import GraphState

def assemble_context(state: GraphState):
    print("🧩 [Node: Assembler] Formatting chunks for LLM...")
    chunks = state.get("retrieved_chunks", [])
    
    if not chunks:
        return {"formatted_context": ""}
        
    formatted_text = ""
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "Unknown_ID")        
        text = chunk["text"]
        formatted_text += f"[{chunk_id}]\n{text}\n\n"
        
    return {"formatted_context": formatted_text}