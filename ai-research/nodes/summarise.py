import asyncio
from llm_gateway.router import llm_router
from graph.state import GraphState
from retrieval.vector_retriever import VectorRetriever

vec_retriever = VectorRetriever()

CHUNK_BATCH_SIZE = 40

async def summarize_batch(batch_text: str, batch_index: int) -> str:
    """Map Phase: Summarize a specific chunk batch in parallel"""
    print(f"      [Map] Summarizing batch {batch_index}...")
    
    prompt = f"""You are a technical analyst extracting information. 
        Summarize the following part of a larger document. 
        Focus on extracting key facts, topics, and important details. Do not miss technical specifications.
        
        Document Part:
        {batch_text}
    """
    
    try:
        response = await llm_router.acompletion(
            model="cheap-model", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Error in mapping batch {batch_index}: {e}")
        return ""

async def summarize_document(state: GraphState):
    print("📝 [Node: Summarizer] Generating Map-Reduce Document Summary...")

    user_id = state["user_id"]
    document_id = state.get("document_id")

    if not document_id:
        return {
            "draft_answer": "Please pick a specific document to summarize — I can't summarize your whole library in one pass.",
            "retrieved_chunks": [],
            "formatted_context": "",
            "is_valid": True
        }

    print(f"   -> Fetching all chunks for document: {document_id}")

    where_filter = {"$and": [{"user_id": user_id}, {"document_id": document_id}]}
    results = vec_retriever.collection.get(
        where=where_filter,
        include=["documents", "metadatas"]
    )

    if not results["documents"]:
        return {
            "draft_answer": "I couldn't find that document — it may not have finished indexing yet, or the document_id is wrong.",
            "retrieved_chunks": [],
            "formatted_context": "",
            "is_valid": True
        }

    # Sort into reading order (by page)
    chunks = sorted(
        zip(results["documents"], results["metadatas"]),
        key=lambda c: c[1].get("page", 0)
    )

    
    batches = []
    for i in range(0, len(chunks), CHUNK_BATCH_SIZE):
        batch = chunks[i : i + CHUNK_BATCH_SIZE]
        batch_text = "\n\n".join([text for text, meta in batch])
        batches.append(batch_text)

    print(f"   -> 🗺️ Map Phase: Split {len(chunks)} chunks into {len(batches)} batches.")

    batch_summaries = []
    
    tasks = [summarize_batch(batch_text, i + 1) for i, batch_text in enumerate(batches)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, str) and result:
            batch_summaries.append(result)

    print("   -> 📉 Reduce Phase: Combining mini-summaries into Final Master Summary...")
    
    # Combine all intermediate summaries
    combined_summaries_text = "\n\n--- NEXT SECTION ---\n\n".join(batch_summaries)

    reduce_prompt = f"""You are an expert technical analyst. 
        Below are summaries of different sequential sections of a large document. 
        Please synthesize these section summaries into a single, cohesive, and comprehensive master summary.
        Use clear headings, bullet points, and maintain a logical flow of information. Do not mention "Section Summaries" in your output.

        Section Summaries:
        {combined_summaries_text}
    """

    try:
        response = await llm_router.acompletion(
            model="strong-model",
            messages=[{"role": "user", "content": reduce_prompt}],
            temperature=0.3
        )

        final_summary = (response.choices[0].message.content or "").strip()

        return {
            "draft_answer": final_summary,
            "retrieved_chunks": [],
            "formatted_context": "",
            "is_valid": True
        }

    except Exception as e:
        print(f"⚠️ Summarizer Reduce Error: {e}")
        return {
            "draft_answer": "Sorry, I encountered an error while trying to generate the final master summary.",
            "retrieved_chunks": [],
            "formatted_context": "",
            "is_valid": True
        }