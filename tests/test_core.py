from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.config import Principal, Settings
from app.ingestion import chunk_pages, content_hash, parse_document
from app.main import create_app
from app.retrieval import bm25_scores


def test_pdf_extracts_page_provenance_and_rejects_blank_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    data = BytesIO()
    writer.write(data)
    try:
        parse_document("blank.pdf", data.getvalue(), 100_000)
    except ValueError as exc:
        assert "no extractable text" in str(exc)
    else:
        raise AssertionError("image-only/blank PDF should fail transparently")


def test_docx_extracts_paragraphs_and_tables():
    doc = DocxDocument()
    doc.add_heading("Inspection", level=1)
    doc.add_paragraph("Verify the isolation boundary.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Asset"
    table.cell(0, 1).text = "Status"
    buf = BytesIO()
    doc.save(buf)
    pages = parse_document("check.docx", buf.getvalue(), 100_000)
    assert pages[0].page is None
    assert "Verify the isolation boundary" in pages[0].text
    assert "Asset | Status" in pages[0].text


def test_chunk_overlap_and_hash():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_pages([type("P", (), {"page": 3, "text": text})()], 50, 10)
    assert len(chunks) == 3
    assert chunks[0]["page"] == 3
    assert set(chunks[0]["text"].split()[-10:]) & set(chunks[1]["text"].split()[:10])
    assert (
        content_hash(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_bm25_prefers_relevant_document():
    corpus = [
        {"text": "OT network isolation and firewall controls"},
        {"text": "industrial safety training guidance"},
    ]
    scores = bm25_scores("network isolation firewall", corpus)
    assert scores[0] > scores[1]


def test_settings_load_dotenv_with_environment_precedence(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"APP_DATA_DIR={tmp_path / 'app-data'}\n"
        "RAG_API_KEYS=test-key:tenant-test:viewer\n"
        "CHUNK_WORDS=50\nCHUNK_OVERLAP_WORDS=10\n"
    )
    for name in ("APP_DATA_DIR", "RAG_API_KEYS", "CHUNK_WORDS", "CHUNK_OVERLAP_WORDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CHUNK_WORDS", "60")
    settings = Settings.from_env()
    assert settings.chunk_words == 60
    assert settings.api_keys["test-key"] == Principal("tenant-test", "viewer")


def test_api_authentication_role_and_tenant_boundary(tmp_path: Path):
    settings = Settings(
        app_env="test",
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        qdrant_url=None,
        qdrant_path=tmp_path / "qdrant",
        embedding_model="BAAI/bge-small-en-v1.5",
        max_upload_bytes=1_000_000,
        chunk_words=50,
        chunk_overlap_words=10,
        api_keys={
            "admin-a": Principal("tenant-a", "admin"),
            "viewer-b": Principal("tenant-b", "viewer"),
        },
    )
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/v1/documents").status_code == 401
        assert (
            client.get("/auth/whoami", headers={"X-API-Key": "viewer-b"}).json()["tenant_id"]
            == "tenant-b"
        )
        assert (
            client.post("/api/v1/admin/reindex", headers={"X-API-Key": "viewer-b"}).status_code
            == 403
        )
        response = client.post("/api/v1/ask", headers={"X-API-Key": "viewer-b"}, json={"query": ""})
        assert response.status_code == 422
