import math
from sentence_transformers import CrossEncoder

class CrossEncoderReranker:
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"):
        print("⏳ Loading Cross-Encoder model (this might take a few seconds)...")
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list, top_n: int = 3, threshold: float = 0.05):
        if not candidates:
            return []

        # Format the input as pairs: [[query, doc1], [query, doc2], ...]
        pairs = [[query, chunk["text"]] for chunk in candidates]
        
        raw_scores = self.model.predict(pairs)
        
        scored_candidates = []
        for i, chunk in enumerate(candidates):
            logit = raw_scores[i]
            sigmoid_score = 1 / (1 + math.exp(-logit))
            
            scored_candidates.append({
                "chunk": chunk,
                "score": sigmoid_score
            })
        
        # Sort candidates strictly by their deep-attention score
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Apply the threshold gate and slice the top_n
        final_results = []
        for item in scored_candidates:
            if item["score"] >= threshold:
                final_results.append(item["chunk"])
            
            if len(final_results) >= top_n:
                break
                
        return final_results