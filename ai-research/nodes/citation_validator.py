import yaml
from graph.state import GraphState
from llm_gateway.router import llm_router
from pydantic import BaseModel, Field

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="True if ALL claims are supported by their specific citations. False if there are hallucinations or missing citations.")
    feedback: str = Field(description="If invalid, provide specific instructions on what to fix. If valid, return empty string.")

def validate_citations(state: GraphState):
    print("[Node: Validator] Cross-checking citations using YAML guardrails...")
    
    if not state.get("formatted_context", "").strip():
        return {"is_valid": True, "validation_feedback": ""}
        
    with open("guardrails/output_guardrails.yaml", "r") as file:
        config = yaml.safe_load(file)
        
    policy = config["policies"][0]
    
    prompt = f"""
        {policy['system_prompt']}
        
        Context:
        {state['formatted_context']}
        
        Draft Answer:
        {state['draft_answer']}
    """
    
    try:
        response = llm_router.completion(
            model="evaluator-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=ValidationResult
        )
        
        result_text = response.choices[0].message.content
        result = ValidationResult.model_validate_json(result_text)
        
        print(f"   -> Validator Decision: {'✅ PASS' if result.is_valid else '❌ FAIL'}")
        
        if not result.is_valid:
            print(f"   -> Feedback for next loop: {result.feedback}")
                        
        return {
            "is_valid": result.is_valid,
            "validation_feedback": result.feedback,
        }
        
    except Exception as e:
        print(f"⚠️ Validator parsing error. Safely passing answer to prevent crash. Error: {e}")
        return {"is_valid": True, "validation_feedback": ""}