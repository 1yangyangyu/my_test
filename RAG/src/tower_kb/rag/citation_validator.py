from tower_kb.domain.errors import DomainError

def validate(draft, evidence):
    known = {e["citation_id"]: e for e in evidence}
    ids = draft.get("citation_ids", [])
    if not ids or len(ids) != len(set(ids)) or any(i not in known for i in ids):
        raise DomainError("invalid_citation", "生成结果引用校验失败", 503)
    # Local generator must quote every cited evidence verbatim. Semantic support
    # validation for a future model generator needs a separately evaluated policy.
    if any(known[i]["text"] not in draft.get("answer", "") for i in ids):
        raise DomainError("unsupported_answer", "回答不满足本地原文引用规则", 503)
    return [known[i] for i in ids]
