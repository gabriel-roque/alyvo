ALTER TABLE knowledge_chunks
  ADD COLUMN IF NOT EXISTS content_hash varchar(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS section varchar(255) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS page integer,
  ADD COLUMN IF NOT EXISTS parent_id varchar(64),
  ADD COLUMN IF NOT EXISTS parser_version varchar(40) NOT NULL DEFAULT 'structural-v1',
  ADD COLUMN IF NOT EXISTS embedding_model varchar(120) NOT NULL DEFAULT 'BAAI/bge-m3',
  ADD COLUMN IF NOT EXISTS index_version varchar(40) NOT NULL DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_hash ON knowledge_chunks(content_hash);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_parent_id ON knowledge_chunks(parent_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_index_version ON knowledge_chunks(index_version);

CREATE TABLE IF NOT EXISTS knowledge_index_versions (
  id varchar(36) PRIMARY KEY,
  tenant_id varchar(64) NOT NULL REFERENCES tenants(id),
  version varchar(40) NOT NULL,
  parser_version varchar(40) NOT NULL,
  embedding_model varchar(120) NOT NULL,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, version)
);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_versions_tenant_id ON knowledge_index_versions(tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_versions_active ON knowledge_index_versions(active);

CREATE TABLE IF NOT EXISTS tool_executions (
  id varchar(36) PRIMARY KEY,
  tenant_id varchar(64) NOT NULL REFERENCES tenants(id),
  session_id varchar(36) NOT NULL REFERENCES chat_sessions(id),
  actor_id varchar(36) NOT NULL,
  confirmation_id varchar(64) NOT NULL,
  tool_name varchar(80) NOT NULL,
  arguments_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  status varchar(20) NOT NULL DEFAULT 'pending',
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code varchar(120) NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, confirmation_id)
);
CREATE INDEX IF NOT EXISTS ix_tool_executions_tenant_id ON tool_executions(tenant_id);
CREATE INDEX IF NOT EXISTS ix_tool_executions_session_id ON tool_executions(session_id);
CREATE INDEX IF NOT EXISTS ix_tool_executions_actor_id ON tool_executions(actor_id);
CREATE INDEX IF NOT EXISTS ix_tool_executions_confirmation_id ON tool_executions(confirmation_id);

ALTER TABLE knowledge_index_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_index_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS knowledge_index_versions_tenant_policy ON knowledge_index_versions;
CREATE POLICY knowledge_index_versions_tenant_policy ON knowledge_index_versions
  USING (current_setting('app.tenant_id', true) = '*' OR tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (current_setting('app.tenant_id', true) = '*' OR tenant_id = current_setting('app.tenant_id', true));

ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_executions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tool_executions_tenant_policy ON tool_executions;
CREATE POLICY tool_executions_tenant_policy ON tool_executions
  USING (current_setting('app.tenant_id', true) = '*' OR tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (current_setting('app.tenant_id', true) = '*' OR tenant_id = current_setting('app.tenant_id', true));

