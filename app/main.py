import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.answering import configured_provider
from app.config import Principal, Settings
from app.db import AuditEvent, Conversation, Database, Document, Feedback, Message
from app.ingestion import chunk_pages, content_hash, parse_document
from app.retrieval import COLLECTION, HybridRetriever
from app.ui import UI

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("engineering_rag")
ABSTENTION_DENSE_THRESHOLD = 0.72


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class AskRequest(SearchRequest):
    conversation_id: str | None = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    rating: int = Field(ge=1, le=5)
    citation_correct: bool
    note: str = Field(default="", max_length=1000)


class Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.database_url)
        self.retriever: HybridRetriever | None = None
        self.answer_provider = configured_provider()

    def initialize(self) -> None:
        self.db.initialize()
        self.retriever = HybridRetriever(self.settings)

    def close(self) -> None:
        if self.retriever:
            self.retriever.close()

    def add_audit(self, tenant: str, role: str, action: str, resource_id: str = "") -> None:
        with self.db.session() as session:
            session.add(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant,
                    actor_role=role,
                    action=action,
                    resource_id=resource_id,
                )
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    service = Service(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        service.initialize()
        yield
        service.close()

    app = FastAPI(
        title="Engineering Document Intelligence & Grounded RAG", version="0.1.0", lifespan=lifespan
    )
    app.state.service = service

    def principal(x_api_key: Annotated[str | None, Header()] = None) -> Principal:
        if not x_api_key:
            raise HTTPException(401, "X-API-Key is required")
        for key, user in app_settings.api_keys.items():
            if hmac.compare_digest(key, x_api_key):
                return user
        raise HTTPException(401, "Invalid API key")

    def admin(user: Annotated[Principal, Depends(principal)]) -> Principal:
        if user.role != "admin":
            raise HTTPException(403, "Administrator role required")
        return user

    def get_service() -> Service:
        if service.retriever is None:
            service.initialize()
        return service

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(svc: Annotated[Service, Depends(get_service)]):
        try:
            with svc.db.session() as session:
                session.execute(select(1))
            if not svc.retriever.client.collection_exists(COLLECTION):
                raise RuntimeError("Qdrant collection is unavailable")
            return {
                "status": "ready",
                "database": "ok",
                "vector_store": "ok",
                "embedding_model": app_settings.embedding_model,
            }
        except Exception as exc:
            raise HTTPException(503, "Dependency readiness check failed") from exc

    @app.get("/auth/whoami")
    def whoami(user: Annotated[Principal, Depends(principal)]):
        return {"tenant_id": user.tenant_id, "role": user.role}

    @app.get("/api/v1/documents")
    def documents(
        user: Annotated[Principal, Depends(principal)],
        svc: Annotated[Service, Depends(get_service)],
    ):
        rows = svc.db.list_documents(user.tenant_id)
        return [
            {
                "id": d.id,
                "title": d.title,
                "version": d.version,
                "page_count": d.page_count,
                "chunk_count": d.chunk_count,
                "status": d.status,
                "created_at": d.created_at,
            }
            for d in rows
        ]

    @app.post("/api/v1/documents/upload", status_code=201)
    async def upload(
        file: Annotated[UploadFile, File()],
        user: Annotated[Principal, Depends(admin)],
        svc: Annotated[Service, Depends(get_service)],
    ):
        name = Path(file.filename or "upload").name
        payload = await file.read(app_settings.max_upload_bytes + 1)
        try:
            pages = parse_document(name, payload, app_settings.max_upload_bytes)
        except ValueError as exc:
            raise HTTPException(415 if "Unsupported" in str(exc) else 422, str(exc)) from exc
        digest = content_hash(payload)
        chunks = chunk_pages(pages, app_settings.chunk_words, app_settings.chunk_overlap_words)
        if not chunks:
            raise HTTPException(422, "Document extraction produced no usable chunks")
        with svc.db.session() as session:
            old = session.scalar(
                select(Document).where(
                    Document.tenant_id == user.tenant_id, Document.sha256 == digest
                )
            )
            if old:
                return {
                    "id": old.id,
                    "title": old.title,
                    "status": "duplicate",
                    "version": old.version,
                    "chunk_count": old.chunk_count,
                }
            versions = list(
                session.scalars(
                    select(Document).where(
                        Document.tenant_id == user.tenant_id, Document.title == name
                    )
                )
            )
            version = max((d.version for d in versions), default=0) + 1
            doc_id = str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                tenant_id=user.tenant_id,
                title=name,
                sha256=digest,
                version=version,
                page_count=len(pages),
                chunk_count=len(chunks),
                status="indexing",
            )
            session.add(doc)
        try:
            svc.retriever.add_document(user.tenant_id, doc_id, name, version, digest, chunks)
            for prior in versions:
                svc.retriever.mark_document_obsolete(user.tenant_id, prior.id)
            with svc.db.session() as session:
                session.get(Document, doc_id).status = "indexed"
        except Exception as exc:
            with svc.db.session() as session:
                row = session.get(Document, doc_id)
                if row:
                    row.status = "failed"
            logger.exception("indexing_failed tenant=%s document_id=%s", user.tenant_id, doc_id)
            raise HTTPException(
                503, "Document was parsed but indexing failed; inspect server logs"
            ) from exc
        svc.add_audit(user.tenant_id, user.role, "document.index", doc_id)
        return {
            "id": doc_id,
            "title": name,
            "status": "indexed",
            "version": version,
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "sha256": digest,
        }

    @app.post("/api/v1/search")
    def search(
        body: SearchRequest,
        user: Annotated[Principal, Depends(principal)],
        svc: Annotated[Service, Depends(get_service)],
    ):
        started = time.perf_counter()
        results, scores = svc.retriever.search(user.tenant_id, body.query, body.top_k)
        svc.add_audit(user.tenant_id, user.role, "search", "")
        logger.info(
            json.dumps(
                {
                    "event": "search",
                    "tenant_id": user.tenant_id,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "result_count": len(results),
                }
            )
        )
        return {"results": results, "diagnostics": scores}

    @app.post("/api/v1/ask")
    def ask(
        body: AskRequest,
        user: Annotated[Principal, Depends(principal)],
        svc: Annotated[Service, Depends(get_service)],
    ):
        started = time.perf_counter()
        ranked, dense_score = svc.retriever.ranked_lists(
            user.tenant_id, body.query, max(20, body.top_k)
        )
        results = [
            {**item, "citation_id": item["point_id"]} for item in ranked["hybrid"][: body.top_k]
        ]
        diagnostic = {
            "dense_top_score": dense_score,
            "bm25_candidates": float(len(ranked["bm25"])),
        }
        answerable = bool(results) and diagnostic["dense_top_score"] >= ABSTENTION_DENSE_THRESHOLD
        provider_name = "abstention"
        usage: dict[str, int] = {}
        if answerable:
            top = []
            seen_ids: set[str] = set()
            for item in [*ranked["bm25"][:1], *results]:
                point_id = item["point_id"]
                if point_id not in seen_ids:
                    top.append({**item, "citation_id": point_id})
                    seen_ids.add(point_id)
                if len(top) == 3:
                    break
            try:
                result = svc.answer_provider.answer(body.query, top)
                provider_name, usage = result.provider, result.usage
            except RuntimeError:
                # Provider failures do not prevent evidence-backed operation.
                from app.answering import ExtractiveAnswerProvider

                result = ExtractiveAnswerProvider().answer(body.query, top)
                provider_name = "extractive-fallback"
            valid = {r["citation_id"] for r in top}
            cited_ids = list(dict.fromkeys(cid for cid in result.citation_ids if cid in valid))
            if not cited_ids:
                answerable = False
                citations = []
                answer = (
                    "I cannot answer from the indexed evidence. "
                    "No valid source citation was returned."
                )
            else:
                citations = [
                    {
                        "citation_id": r["citation_id"],
                        "title": r["title"],
                        "page": r["page"],
                        "section": r["section"],
                        "excerpt": r["text"][:900],
                    }
                    for r in top
                    if r["citation_id"] in cited_ids
                ]
                answer = result.text
        else:
            citations = []
            answer = (
                "I cannot answer from the indexed evidence. "
                "The available sources did not provide sufficiently relevant support."
            )
        conversation_id = body.conversation_id or str(uuid.uuid4())
        with svc.db.session() as session:
            conv = session.get(Conversation, conversation_id)
            if conv and conv.tenant_id != user.tenant_id:
                raise HTTPException(404, "Conversation not found")
            if not conv:
                session.add(Conversation(id=conversation_id, tenant_id=user.tenant_id))
            session.add_all(
                [
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        tenant_id=user.tenant_id,
                        role="user",
                        content=body.query,
                    ),
                    Message(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        tenant_id=user.tenant_id,
                        role="assistant",
                        content=answer,
                    ),
                ]
            )
        svc.add_audit(user.tenant_id, user.role, "answer", conversation_id)
        latency = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "answer",
                    "tenant_id": user.tenant_id,
                    "conversation_id": conversation_id,
                    "latency_ms": latency,
                    "citation_count": len(citations),
                    "abstained": not answerable,
                    "provider": provider_name,
                    "usage": usage,
                }
            )
        )
        return {
            "conversation_id": conversation_id,
            "answer": answer,
            "abstained": not answerable,
            "citations": citations,
            "latency_ms": latency,
            "diagnostics": diagnostic,
            "mode": provider_name,
            "usage": usage,
        }

    @app.get("/api/v1/conversations")
    def conversations(
        user: Annotated[Principal, Depends(principal)],
        svc: Annotated[Service, Depends(get_service)],
        limit: int = Query(20, ge=1, le=100),
    ):
        with svc.db.session() as session:
            items = session.scalars(
                select(Conversation)
                .where(Conversation.tenant_id == user.tenant_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            ).all()
            return [
                {
                    "id": c.id,
                    "created_at": c.created_at,
                    "messages": [
                        {"role": m.role, "content": m.content, "created_at": m.created_at}
                        for m in session.scalars(
                            select(Message)
                            .where(
                                Message.conversation_id == c.id, Message.tenant_id == user.tenant_id
                            )
                            .order_by(Message.created_at)
                        )
                    ],
                }
                for c in items
            ]

    @app.post("/api/v1/feedback", status_code=201)
    def feedback(
        body: FeedbackRequest,
        user: Annotated[Principal, Depends(principal)],
        svc: Annotated[Service, Depends(get_service)],
    ):
        with svc.db.session() as session:
            conv = session.get(Conversation, body.conversation_id)
            if not conv or conv.tenant_id != user.tenant_id:
                raise HTTPException(404, "Conversation not found")
            session.add(
                Feedback(
                    id=str(uuid.uuid4()),
                    tenant_id=user.tenant_id,
                    conversation_id=conv.id,
                    rating=body.rating,
                    citation_correct=body.citation_correct,
                    note=body.note,
                )
            )
        svc.add_audit(user.tenant_id, user.role, "feedback.submit", body.conversation_id)
        return {"status": "recorded"}

    @app.get("/api/v1/admin/evaluations/summary")
    def evaluation_summary(user: Annotated[Principal, Depends(admin)]):
        path = Path("reports/evaluation.json")
        if not path.exists():
            return {
                "status": "not_run",
                "message": "Run python scripts/evaluate.py after indexing the sample source.",
            }
        return json.loads(path.read_text())

    @app.post("/api/v1/admin/reindex")
    def reindex(
        user: Annotated[Principal, Depends(admin)], svc: Annotated[Service, Depends(get_service)]
    ):
        chunks = svc.retriever.all_chunks(user.tenant_id)
        grouped: dict[str, list[dict]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk["document_id"], []).append(chunk)
        for document_id, payloads in grouped.items():
            payloads.sort(key=lambda item: item["chunk_index"])
            first = payloads[0]
            svc.retriever.add_document(
                user.tenant_id,
                document_id,
                first["title"],
                first["version"],
                first["sha256"],
                [
                    {
                        "page": item.get("page"),
                        "section": item.get("section", ""),
                        "text": item["text"],
                    }
                    for item in payloads
                ],
            )
        svc.add_audit(user.tenant_id, user.role, "document.reindex", str(len(grouped)))
        return {
            "status": "completed",
            "documents_reindexed": len(grouped),
            "chunks_reembedded": len(chunks),
        }

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def ui():
        return HTMLResponse(UI)

    return app


app = create_app()
