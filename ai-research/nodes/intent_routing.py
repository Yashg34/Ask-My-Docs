from typing import Literal
from llm_gateway.router import llm_router
from graph.state import GraphState
from pydantic import BaseModel, Field
from nodes.utils import parse_structured


class RouteAndRewrite(BaseModel):
    intent: Literal["GREETING", "RAG", "SUMMARY"] = Field(
        description="Classify as 'GREETING' for casual hellos/thanks, 'RAG' for document questions, or 'SUMMARY' for overview requests."
    )
    greeting_response: str = Field(
        default="",
        description="If intent is GREETING, provide a short, polite, welcoming response. Empty otherwise."
    )
    search_query: str = Field(
        default="",
        description="If intent is RAG, provide optimized search keywords based on the query and chat history. ONLY output space-separated keywords, no sentences."
    )

async def route_intent(state: GraphState):
    print("[Node: Router & Rewriter] Detecting intent and extracting keywords...")
    query = state["query"]
    chat_history = state.get("chat_history", [])
    
    history_text = ""
    if chat_history:
        for msg in chat_history[-4:]:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

    prompt = f"""
        You are a technical document assistant. Your job is to classify the user query into one of three categories:
        1. GREETING: Casual greetings, thanks, pleasantries.
        2. RAG: Specific questions asking for facts, targeted document details, code snippets, or focused explanations.
        3. SUMMARY: Requests asking for a general overview or abstract of the entire document.

        CRITICAL INSTRUCTION FOR RAG:
        If the intent is RAG, you must also extract the most important search keywords. 
        You must look at the Chat History to resolve follow-ups (e.g., 'and what about X', 'how does it work') and include missing context keywords.
        DO NOT write sentences. ONLY output space-separated keywords in the `search_query` field.

        Chat History:
        {history_text or 'None'}

        User Query: "{query}"
    """

    try:
        response = await llm_router.acompletion(
            model="cheap-model",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format=RouteAndRewrite
        )

        result_text = response.choices[0].message.content
        result = parse_structured(RouteAndRewrite, result_text)

        print(f"   -> Detected Intent: {result.intent}")
        if result.intent == "RAG":
            print(f"   -> Optimized Query: {result.search_query}")

        if result.intent == "GREETING":
            return {
                "intent": "GREETING",
                "draft_answer": result.greeting_response or "Hello! How can I help you with your documents today?",
                "retrieved_chunks": []
            }
        elif result.intent == "SUMMARY":
            return {"intent": "SUMMARY"}
        else:
            return {
                "intent": "RAG",
                "search_query": result.search_query or query
            }

    except Exception as e:
        print(f"⚠️ Router parsing error. Safely defaulting to RAG pipeline. Error: {e}")
        return {"intent": "RAG", "search_query": query}