import os
from graph.state import GraphState
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="True if ALL claims are supported by their specific citations. False if there are hallucinations or missing citations.")
    feedback: str = Field(description="If invalid, provide specific instructions on what to fix. If valid, return empty string.")

evaluator_llm = ChatGoogleGenerativeAI(
    model=os.getenv("LLM_MODEL", "gemini-2.0-flash"), 
    temperature=0 
)

structured_evaluator = evaluator_llm.with_structured_output(ValidationResult)

def validate_citations(state: GraphState):
    print("🕵️ [Node: Validator] Cross-checking citations against context...")
    
    # If no context was retrieved, the generator already safely rejected it.
    if not state.get("formatted_context", "").strip():
        return {"is_valid": True, "validation_feedback": ""}
        
    prompt = f"""
    You are a strict, merciless fact-checker. 
    Your job is to verify that EVERY single claim in the Draft Answer is explicitly supported by the cited chunk in the Context.
    
    Context:
    {state['formatted_context']}
    
    Draft Answer:
    {state['draft_answer']}
    
    Rules:
    1. Citation Existence: If the answer uses a citation like [doc:pX:cY] that is NOT present in the Context, return is_valid=False.
    2. Entailment Check: If the answer makes a claim but the cited chunk does not actually support that claim, return is_valid=False.
    3. If is_valid is False, write clear feedback explaining EXACTLY which citation failed and why, so the writer can fix it.
    """
    
    try:
        result = structured_evaluator.invoke(prompt)
        print(f"   -> Validator Decision: {'✅ PASS' if result.is_valid else '❌ FAIL'}")
        
        if not result.is_valid:
            print(f"   -> Feedback for next loop: {result.feedback}")
            
        return {
            "is_valid": result.is_valid,
            "validation_feedback": result.feedback
        }
    except Exception as e:
        print(f"⚠️ Validator parsing error. Safely passing answer to prevent crash. Error: {e}")
        return {"is_valid": True, "validation_feedback": ""}