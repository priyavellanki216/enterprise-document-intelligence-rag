from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    role: str


@dataclass(frozen=True)
class Settings:
    app_env: str
    data_dir: Path
    database_url: str
    qdrant_url: str | None
    qdrant_path: Path
    embedding_model: str
    max_upload_bytes: int
    chunk_words: int
    chunk_overlap_words: int
    api_keys: dict[str, Principal]

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(Path(".env"), override=False)
        root = Path(os.getenv("APP_DATA_DIR", "./data")).resolve()
        keymap: dict[str, Principal] = {}
        raw_keys = os.getenv(
            "RAG_API_KEYS", "local-admin-change-me:demo:admin,local-viewer-change-me:demo:viewer"
        )
        for entry in raw_keys.split(","):
            parts = entry.strip().split(":")
            if len(parts) != 3 or not all(parts):
                raise ValueError("RAG_API_KEYS entries must be key:tenant:role")
            key, tenant, role = parts
            if role not in {"admin", "viewer"}:
                raise ValueError("RAG_API_KEYS role must be admin or viewer")
            keymap[key] = Principal(tenant_id=tenant, role=role)
        words = int(os.getenv("CHUNK_WORDS", "220"))
        overlap = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))
        if words < 40 or overlap < 0 or overlap >= words:
            raise ValueError("Require CHUNK_WORDS >= 40 and 0 <= overlap < chunk words")
        maximum = int(os.getenv("MAX_UPLOAD_BYTES", "25000000"))
        if not 1024 <= maximum <= 100_000_000:
            raise ValueError("MAX_UPLOAD_BYTES must be between 1 KiB and 100 MB")
        url = os.getenv("QDRANT_URL", "").strip() or None
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            data_dir=root,
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{root / 'app.db'}"),
            qdrant_url=url,
            qdrant_path=Path(os.getenv("QDRANT_PATH", str(root / "qdrant"))).resolve(),
            embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            max_upload_bytes=maximum,
            chunk_words=words,
            chunk_overlap_words=overlap,
            api_keys=keymap,
        )
