-- Initial relational metadata schema. Runtime create_all() uses the same SQLAlchemy models.
CREATE TABLE IF NOT EXISTS documents (
  id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, title VARCHAR(512) NOT NULL,
  sha256 VARCHAR(64) NOT NULL, version INTEGER NOT NULL DEFAULT 1, page_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0, status VARCHAR(24) NOT NULL DEFAULT 'indexed', created_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT uq_document_tenant_hash UNIQUE (tenant_id, sha256)
);
CREATE INDEX IF NOT EXISTS ix_documents_tenant_id ON documents(tenant_id);
CREATE TABLE IF NOT EXISTS conversations (
  id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conversations_tenant_id ON conversations(tenant_id);
CREATE TABLE IF NOT EXISTS messages (
  id VARCHAR(36) PRIMARY KEY, conversation_id VARCHAR(36) NOT NULL, tenant_id VARCHAR(128) NOT NULL,
  role VARCHAR(16) NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
  id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, conversation_id VARCHAR(36) NOT NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5), citation_correct BOOLEAN NOT NULL,
  note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(128) NOT NULL, actor_role VARCHAR(16) NOT NULL,
  action VARCHAR(128) NOT NULL, resource_id VARCHAR(128) NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL
);
