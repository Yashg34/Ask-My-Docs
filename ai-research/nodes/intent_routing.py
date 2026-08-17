from typing import Literal
from llm_gateway.router import llm_router
from graph.state import GraphState
from pydantic import BaseModel, Field


class IntentResult(BaseModel):
    intent: Literal["GREETING", "RAG", "SUMMARY"] = Field(
        description="Classify as 'GREETING' for casual hellos/thanks, 'RAG' for document questions/tasks, or 'SUMMARY' for overview requests."
    )
    greeting_response: str = Field(
        default="",
        description="If intent is GREETING, provide a short, polite, welcoming response. Empty if RAG or SUMMARY."
    )


def route_intent(state: GraphState):
    print("[Node: Router] Detecting user intent using cheap-model...")
    query = state["query"]

    prompt = f"""
        You are an intent router for a technical document assistant.
        Classify the user query into one of three categories:
        1. GREETING: Casual greetings, thanks, pleasantries (e.g., 'Hi', 'Thanks', 'How are you?').
        2. RAG: Specific questions asking for facts, targeted document details, code snippets, or focused explanations.
        3. SUMMARY: Requests asking for a general overview, high-level summary, or abstract of the entire document (e.g., 'Summarize this PDF', 'What is this document about?', 'Give me a brief overview of the file').

        User Query: "{query}"
    """

    try:
        response = llm_router.completion(
            model="cheap-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=IntentResult
        )

        result_text = response.choices[0].message.content
        result = IntentResult.model_validate_json(result_text)

        print(f"   -> Detected Intent: {result.intent}")

        if result.intent == "GREETING":
            return {
                "intent": "GREETING",
                "draft_answer": result.greeting_response or "Hello! How can I help you with your documents today?",
                "retrieved_chunks": []
            }
        else:
            return {"intent": result.intent}

    except Exception as e:
        print(f"⚠️ Router parsing error. Safely defaulting to RAG pipeline. Error: {e}")
        return {"intent": "RAG"}