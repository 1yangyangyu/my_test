def rrf(rankings, limit=40, k=60):
    scores = {}
    for hits in rankings:
        for rank, hit in enumerate(hits, 1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0) + 1/(k+rank)
    return sorted(scores, key=lambda key:(-scores[key],key))[:limit]
