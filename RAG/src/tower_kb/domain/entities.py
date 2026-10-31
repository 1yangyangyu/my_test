from dataclasses import dataclass

@dataclass(frozen=True)
class Actor:
    user_id: str
    org_id: str
    roles: tuple[str, ...]
    regions: tuple[str, ...]

@dataclass(frozen=True)
class Hit:
    chunk_id: str
    text: str
    score: float
