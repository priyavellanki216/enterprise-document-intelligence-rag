from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

URL = "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf"
EXPECTED_TITLE = "Guide to Operational Technology (OT) Security"
MAX_BYTES = 25_000_000
DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "NIST.SP.800-82r3.pdf"


def download() -> tuple[Path, str]:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        URL, headers={"User-Agent": "EngineeringDocumentRAG/0.1 (reproducible corpus setup)"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200 or "pdf" not in response.headers.get("Content-Type", "").lower():
            raise RuntimeError(
                f"Unexpected source response: {response.status} "
                f"{response.headers.get('Content-Type')}"
            )
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("Source exceeds the configured 25 MB safety limit")
    if not data.startswith(b"%PDF-"):
        raise RuntimeError("Official source did not return a PDF")
    DEST.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"Downloaded {DEST} ({len(data)} bytes), SHA-256 {digest}")
    return DEST, digest


if __name__ == "__main__":
    download()
