"""Local baselines: token overlap + hashed character vectors; NOT BM25/BGE."""
import hashlib
import math
import re
from collections import Counter
from tower_kb.domain.entities import Hit

def tokens(text):
    text = text.lower()
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text)
    return words + [a+b for a,b in zip(words, words[1:])]

def vector(text):
    values = [0.0] * 128
    for token in tokens(text):
        h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
        values[h % 128] += 1 if h & 128 else -1
    norm = math.sqrt(sum(v*v for v in values)) or 1
    return [v/norm for v in values]

class LexicalIndex:
    def search(self, query, chunks, limit=30):
        q = Counter(tokens(query))
        hits = []
        for c in chunks:
            t = Counter(tokens(c["text"]))
            score = sum(min(n, t[w]) for w,n in q.items()) / max(1,sum(q.values()))
            if score > 0:
                hits.append(Hit(c["id"],c["text"],score))
        return sorted(hits,key=lambda h:(-h.score,h.chunk_id))[:limit]

class VectorIndex:
    def search(self, query, chunks, limit=30):
        q = vector(query)
        hits = [Hit(c["id"],c["text"],sum(a*b for a,b in zip(q,c["vector"]))) for c in chunks]
        return sorted((h for h in hits if h.score > .05), key=lambda h:(-h.score,h.chunk_id))[:limit]
