from typing import Protocol

class Generator(Protocol):
    def generate(self, query: str, evidence: list[dict]) -> dict: ...
