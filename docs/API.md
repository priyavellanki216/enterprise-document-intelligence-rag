# API reference

Interactive OpenAPI docs: `/docs` and `/redoc`. All application routes except health and `/` require `X-API-Key`. The local `.env.example` contains two replaceable demonstration keys. Keys resolve to one tenant and either `viewer` or `admin`; all SQL and vector-store reads filter by tenant on the server.

- `GET /health/live` — process liveness.
- `GET /health/ready` — relational database and Qdrant readiness.
- `GET /auth/whoami` — authenticated tenant and role.
- `GET /api/v1/documents` — tenant-scoped document inventory.
- `POST /api/v1/documents/upload` — multipart PDF/DOCX upload; admin only; bounded by `MAX_UPLOAD_BYTES`; SHA-256 duplicate detection; updates create a new version.
- `POST /api/v1/search` — `{ "query": "...", "top_k": 5 }`; tenant-filtered dense/BM25 hybrid results with source metadata.
- `POST /api/v1/ask` — same query shape plus optional `conversation_id`; uses the top BM25 passage plus balanced-RRF evidence, returns quotations tied to up to three citations, abstention flag, latency, and evidence excerpts.
- `GET /api/v1/conversations?limit=20` — tenant-scoped conversation history.
- `POST /api/v1/feedback` — rating and citation correctness, restricted to the conversation tenant.
- `GET /api/v1/admin/evaluations/summary` — actual saved evaluation report, admin only.
- `POST /api/v1/admin/reindex` — administrator re-embeds each current tenant-scoped chunk from Qdrant payloads and upserts stable point IDs; returns actual document/chunk counts.

Example:

```bash
export VIEWER_API_KEY="<viewer-key-from-your-local-.env>"
curl -H "X-API-Key: ${VIEWER_API_KEY}" -H 'Content-Type: application/json' \
  -d '{"query":"What risks remain when using network isolation devices?","top_k":5}' \
  http://localhost:8000/api/v1/ask
```

The default answer engine quotes retrieved passages. A hosted OpenAI-compatible adapter can be selected with `LLM_PROVIDER=openai-compatible`, `OPENAI_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`; use it only after reviewing the data-sharing and provider terms. The adapter uses a 20-second request timeout, one retry, a bounded three-chunk context, a 400-token output ceiling, and rejects citations not among retrieved chunk IDs. Usage token counts are logged only when returned by the provider. External provider behavior is not verified in this run. Citations otherwise come directly from retrieved Qdrant payload metadata; no free-form page numbers are generated. The application does not currently provide SSO, per-document ACLs, managed key rotation, distributed rate limiting, or OCR; tenant-level API-key scope is the implemented authorization boundary.
