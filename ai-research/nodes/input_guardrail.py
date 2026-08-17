import yaml
from graph.state import GraphState
from llm_gateway.router import llm_router
from pydantic import BaseModel, Field

class SecurityCheck(BaseModel):
    is_safe: bool = Field(description="True if safe, False if malicious.")
    reason: str = Field(description="Brief reason for the decision.")

def check_input_safety(state: GraphState):
    print("[Node: Guardrail] Scanning input based on YAML policies...")
    
    with open("guardrails/input_guardrails.yaml", "r") as file:
        config = yaml.safe_load(file)
        
    policy = config["policies"][0] 
    
    query = state["query"]
    prompt = f"{policy['system_prompt']}\n\nUser Input: \"{query}\""

    try:
        response = llm_router.completion(
            model="evaluator-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=SecurityCheck
        )
        
        result_text = response.choices[0].message.content
        result = SecurityCheck.model_validate_json(result_text)
        
        if not result.is_safe:
            print(f"🚨 SECURITY ALERT: {result.reason}")
            return {
                "is_safe": False, 
                "security_flag": result.reason,
                "draft_answer": policy["rejection_message"]
            }
            
        print("✅ Input is safe.")
        return {"is_safe": True, "security_flag": "Passed"}
        
    except Exception as e:
        print(f"Guardrail model failed. Failing closed. Error: {e}")
        return {
            "is_safe": False, 
            "safety_feedback": "System safety check is temporarily unavailable. Please try again later."
        }