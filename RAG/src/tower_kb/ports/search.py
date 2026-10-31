from typing import Protocol
from tower_kb.domain.entities import Hit

class SearchIndex(Protocol):
    # Input must already be constrained to the trusted retrieval scope.
    def search(self, query: str, chunks: list[dict], limit: int = 30) -> list[Hit]: ...
