import os
import chromadb
from typing import List, Dict
from ingestion.embedder import LocalEmbedder

class VectorRetriever:
    def __init__(self, collection_name: str = "master_docs"):
        chroma_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        self.client = chromadb.PersistentClient(path=chroma_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedder = LocalEmbedder()

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        if self.collection.count() == 0:
            return []
        
        query_embedding = self.embedder.embed_query(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
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