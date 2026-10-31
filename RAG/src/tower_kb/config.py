import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    data_dir: Path
    token: str
    mode: str = "local"

    @classmethod
    def from_env(cls):
        return cls(Path(os.getenv("TOWER_DATA_DIR", ".runtime")), os.getenv("TOWER_DEV_TOKEN", ""), os.getenv("TOWER_MODE", "local"))

    def validate(self):
        if self.mode != "local":
            raise ValueError("Only local adapters are implemented; production mode is intentionally disabled")
        if len(self.token) < 24:
            raise ValueError("Set TOWER_DEV_TOKEN to a random secret of at least 24 characters")
