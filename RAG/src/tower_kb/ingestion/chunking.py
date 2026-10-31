import hashlib
import re

def chunk_document(doc_id, version, text):
    # Paragraph-aware parents, bounded children with 50-character overlap.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parents = []
    for number, paragraph in enumerate(paragraphs, 1):
        for offset in range(0, len(paragraph), 1600):
            parents.append((paragraph[offset:offset+1600], f"段落 {number}，字符 {offset+1}"))
    result = []
    def ident(kind, n):
        return hashlib.sha256(f"{doc_id}:{version}:chunk-v1:{kind}:{n}".encode()).hexdigest()[:32]
    child_n = 0
    for i, (parent, position) in enumerate(parents):
        pid = ident("parent", i)
        result.append((pid, doc_id, version, None, "parent", i, parent, position))
        for start in range(0, len(parent), 350):
            result.append((ident("child", child_n), doc_id, version, pid, "child", child_n,
                           parent[start:start+400], position + f"，片段偏移 {start+1}"))
            child_n += 1
    return result
