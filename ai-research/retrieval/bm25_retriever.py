import os
import pickle

class BM25Retriever:
    def __init__(self, index_path="data/bm25_index.pkl"):
        self.bm25 = None
        self.chunks = []
        
        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                data = pickle.load(f)
                self.bm25 = data["bm25"]
                self.chunks = data["chunks"]
        else:
            print("⚠️ BM25 index not found. Please ingest a document first.")

    def retrieve(self, query: str, top_k: int = 5):
        if not self.bm25 or not self.chunks:
            return []
        
        # Tokenize the query exactly how we indexed it
        tokenized_query = query.lower().split()
        
        # Get raw BM25 scores for all chunks
        scores = self.bm25.get_scores(tokenized_query)
        
        # Pair up chunk indices with their scores, filtering out zero scores
        scored_indices = [(idx, score) for idx, score in enumerate(scores) if score > 0]
        
        # Sort descending by score
        scored_indices.sort(key=lambda x: x[1], reverse=True)
        
        # Return the top_k chunk objects
        return [self.chunks[idx] for idx, _ in scored_indices[:top_k]]