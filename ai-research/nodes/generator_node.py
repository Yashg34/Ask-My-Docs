from graph.state import GraphState
from generation.generator import Generator

llm_generator = Generator()

def generate_answer(state: GraphState):
    rev_count = state.get("revision_count", 0)
    print(f"✍️ [Node: Generator] Drafting answer (Attempt: {rev_count + 1})...")
    
    context = state.get("formatted_context", "")
    
    if not context.strip():
        return {
            "draft_answer": "I do not have sufficient evidence in the provided documents to answer this question.",
            "revision_count": rev_count + 1,
            "is_valid": True 
        }
        
    query = state["query"]
    feedback = state.get("validation_feedback", "")
    
    if feedback:
        query += f"\n\n[CRITICAL FEEDBACK FROM VALIDATOR: {feedback}. Rewrite strictly fixing these errors.]"
        
    draft = llm_generator.generate_answer(query, context)
    
    return {
        "draft_answer": draft,
        "revision_count": rev_count + 1
    }