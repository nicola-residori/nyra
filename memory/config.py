from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_DATA_ROOT = Path("/var/lib/nyra-memory")
DEFAULT_EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


@dataclass(frozen=True)
class MemorySettings:
    data_root: Path = DEFAULT_DATA_ROOT
    host: str = "0.0.0.0"
    port: int = 8090
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    search_limit: int = 10
    similarity_floor: float = 0.35
    request_timeout_seconds: float = 3.0
    router_url: str = "http://127.0.0.1:8090"

    @property
    def database_path(self) -> Path:
        return self.data_root / "memory.sqlite3"

    @classmethod
    def load(cls) -> "MemorySettings":
        return cls(
            data_root=Path(os.getenv("NYRA_MEMORY_DATA_ROOT", DEFAULT_DATA_ROOT)),
            host=os.getenv("NYRA_MEMORY_HOST", "0.0.0.0"),
            port=int(os.getenv("NYRA_MEMORY_PORT", "8090")),
            embedding_model=os.getenv("NYRA_MEMORY_MODEL", DEFAULT_EMBEDDING_MODEL),
            search_limit=int(os.getenv("NYRA_MEMORY_SEARCH_LIMIT", "10")),
            similarity_floor=float(os.getenv("NYRA_MEMORY_SIMILARITY_FLOOR", "0.35")),
            request_timeout_seconds=float(
                os.getenv("NYRA_MEMORY_REQUEST_TIMEOUT_SECONDS", "3.0")
            ),
            router_url=os.getenv("NYRA_ROUTER_URL", "http://127.0.0.1:8090"),
        )

