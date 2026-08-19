import yaml
import re
from graph.state import GraphState
from llm_gateway.router import llm_router
from pydantic import BaseModel, Field
from nodes.utils import parse_structured

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="True if ALL claims are supported by their specific citations. False if there are hallucinations or missing citations.")
    feedback: str = Field(description="If invalid, provide specific instructions on what to fix. If valid, return empty string.")

with open("guardrails/output_guardrails.yaml", "r") as f:
    _OUTPUT_POLICY = yaml.safe_load(f)["policies"][0]

async def validate_citations(state: GraphState):
    print("[Node: Validator] Cross-checking citations using YAML guardrails...")
    
    if not state.get("formatted_context", "").strip():
        return {"is_valid": True, "validation_feedback": ""}
        
    draft_answer = state.get("draft_answer", "")
    
    # Deterministic Structural Check
    # If the draft answer has no citations in brackets, fail immediately.
    citations = re.findall(r"\[.+?\]", draft_answer)
    if not citations:
        print("   -> Validator Decision: ❌ FAIL (Deterministic Check: No citations found)")
        return {
            "is_valid": False,
            "validation_feedback": "You failed to include any inline citations. You MUST cite your sources using the [Document Name, Page X] format."
        }
        
    # Deterministic Content Check
    formatted_context = state.get("formatted_context", "")
    for citation in citations:
        if citation not in formatted_context:
            print(f"   -> Validator Decision: ❌ FAIL (Fabricated Citation: {citation})")
            return {
                "is_valid": False,
                "validation_feedback": f"You cited {citation}, but this document/page does not exist in the provided context. Only cite from the provided sources."
            }
        
    prompt = f"""
        {_OUTPUT_POLICY['system_prompt']}
        
        Context:
        {state['formatted_context']}
        
        Draft Answer:
        {state['draft_answer']}
    """
    
    try:
        response = await llm_router.acompletion(
            model="evaluator-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=ValidationResult
        )
        
        result_text = response.choices[0].message.content
        result = parse_structured(ValidationResult, result_text)
        
        print(f"   -> Validator Decision: {'✅ PASS' if result.is_valid else '❌ FAIL'}")
        
        if not result.is_valid:
            print(f"   -> Feedback for next loop: {result.feedback}")
                        
        return {
            "is_valid": result.is_valid,
            "validation_feedback": result.feedback,
        }
        
    except Exception as e:
        print(f"Validator model failed. Failing closed. Error: {e}")
        return {
            "is_valid": False, 
            "validation_feedback": "Citation validation engine offline. Unable to verify facts."
        }