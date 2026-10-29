-- PostgreSQL production invariants. SQLAlchemy creates an equivalent portable
-- schema for tests; this migration adds the database-level overlap guarantee.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE appointments
  ADD CONSTRAINT appointments_doctor_no_overlap
  EXCLUDE USING gist (
    tenant_id WITH =,
    doctor_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  ) WHERE (status = 'confirmed');

ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY appointments_tenant_policy ON appointments
  USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY patient_documents_tenant_policy ON patient_documents
  USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY knowledge_documents_tenant_policy ON knowledge_documents
  USING (tenant_id = current_setting('app.tenant_id', true));

