from dotenv import load_dotenv
from typing import List, Dict
from ingestion.embedder import get_embedder, get_chroma_client

load_dotenv()

class VectorRetriever:
    def __init__(self, collection_name: str = "master_docs"):
        self.client = get_chroma_client()
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedder = get_embedder()

    def retrieve(self, query: str, top_k: int = 5, where_filter: dict = None) -> List[Dict]:
        if self.collection.count() == 0:
            return []
        
        query_embedding = self.embedder.embed_query(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter 
        )

        retrieved_chunks = []
        if results["documents"]:
            for i in range(len(results["documents"][0])):
                retrieved_chunks.append({
                    "chunk_id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i]
                })

        return retrieved_chunks