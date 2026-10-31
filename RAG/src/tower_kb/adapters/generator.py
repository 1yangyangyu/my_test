class ExtractiveGenerator:
    """No model calls: quote trusted evidence verbatim; document text is never instructions."""
    def generate(self, query, evidence):
        return {"answer": "\n\n".join(
            ("【案例经验，不能替代有效规范】" if e["source_kind"] == "case" else "【规范原文】")
            + e["text"] + f" [{e['citation_id']}]" for e in evidence),
            "citation_ids": [e["citation_id"] for e in evidence]}
