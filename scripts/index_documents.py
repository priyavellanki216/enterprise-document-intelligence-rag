from __future__ import annotations

import os
from pathlib import Path

from download_data import DEST
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def main() -> None:
    source = Path(os.getenv("RAG_SOURCE_FILE", str(DEST)))
    if not source.is_file():
        raise SystemExit(
            f"Source file not found: {source}. Run python scripts/download_data.py first."
        )
    settings = Settings.from_env()
    admin_key = next(
        (key for key, principal in settings.api_keys.items() if principal.role == "admin"), None
    )
    if not admin_key:
        raise SystemExit("RAG_API_KEYS must include an admin key for indexing")
    app = create_app(settings)
    with TestClient(app) as client, source.open("rb") as stream:
        response = client.post(
            "/api/v1/documents/upload",
            headers={"X-API-Key": admin_key},
            files={"file": (source.name, stream, "application/pdf")},
        )
        if response.status_code not in (201, 200):
            raise SystemExit(f"Indexing failed ({response.status_code}): {response.text}")
        print(response.json())


if __name__ == "__main__":
    main()
