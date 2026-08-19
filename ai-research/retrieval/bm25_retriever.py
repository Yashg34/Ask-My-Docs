import os
import pickle

_bm25_cache = {}
_bm25_chunks = {}

class BM25Retriever:
    def __init__(self):
        pass

    def _get_user_index(self, user_id: str):
        index_path = os.path.join("data", f"bm25_{user_id}.pkl")
        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                data = pickle.load(f)
                return data["bm25"], data["chunks"]
        return None, []

    def retrieve(self, query: str, user_id: str, top_k: int = 5):
        bm25, chunks = self._get_user_index(user_id)
        if not bm25 or not chunks:
            return []
        
        # Tokenize the query exactly how we indexed it
        tokenized_query = query.lower().split()
        
        # Get raw BM25 scores for all chunks
        scores = bm25.get_scores(tokenized_query)
        
        # Pair up chunk indices with their scores, filtering out zero scores
        scored_indices = [(idx, score) for idx, score in enumerate(scores) if score > 0]
        
        # Sort descending by score
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        
        # Return the top_k chunk objects
        return [chunks[idx] for idx, _ in scored_indices[:top_k]]