import re

def parse_structured(model_cls, raw_text: str):
    """
    Strips markdown code fences (```json ... ```) from the LLM output 
    before attempting to parse it with Pydantic.
    """
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip())
    return model_cls.model_validate_json(cleaned)
