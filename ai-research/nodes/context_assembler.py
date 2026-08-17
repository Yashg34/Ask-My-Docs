from graph.state import GraphState

def assemble_context(state: GraphState):
    print("[Node: Assembler] Formatting chunks for LLM...")
    
    chunks = state.get("retrieved_chunks", [])
    
    if not chunks:
        return {"formatted_context": ""}
        
    formatted_texts = []
    
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        page = metadata.get("page", "Unknown")
        
        doc_name = metadata.get("document_name", metadata.get("document_id", "Doc"))
        
        chunk_id = chunk.get("chunk_id", "UnknownID")
        
        formatted_chunk = (
            f"--- CHUNK ID: {chunk_id} ---\n"
            f"Source: {doc_name}, Page: {page}\n"
            f"Content: {chunk.get('text', '')}\n"
            f"---------------------------\n"
        )
        formatted_texts.append(formatted_chunk)
        
    final_context = "\n".join(formatted_texts)
    return {"formatted_context": final_context}