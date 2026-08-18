from sentence_transformers import SentenceTransformer
from typing import List
import chromadb
import os

class LocalEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        print("⏳ Loading Embedding model (this might take a few seconds)...")
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        embeddings = self.model.encode(
            texts, 
            batch_size=batch_size, 
            convert_to_numpy=True,
            show_progress_bar=True  
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

_embedder_instance = None

def get_embedder() -> "LocalEmbedder":
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = LocalEmbedder()
    return _embedder_instance

_chroma_client = None

def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        chroma_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        _chroma_client = chromadb.PersistentClient(path=chroma_dir)
    return _chroma_client