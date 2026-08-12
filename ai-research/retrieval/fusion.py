def reciprocal_rank_fusion(vector_results, bm25_results, k=60):
    """
    Fuses two lists of retrieved chunks using Reciprocal Rank Fusion.
    k = 60 is the standard smoothing constant used in RRF.
    """
    fused_scores = {}
    chunk_map = {} 
    
    def add_ranks(results):
        for rank, chunk in enumerate(results):
            chunk_id = chunk["chunk_id"]
            if chunk_id not in fused_scores:
                fused_scores[chunk_id] = 0
                chunk_map[chunk_id] = chunk
            # RRF Formula: 1 / (k + rank)
            fused_scores[chunk_id] += 1 / (k + rank)

    # Process both lists
    add_ranks(vector_results)
    add_ranks(bm25_results)
    
    # Sort the dictionary by the fused scores in descending order
    sorted_fused = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    
    return [chunk_map[chunk_id] for chunk_id, score in sorted_fused]