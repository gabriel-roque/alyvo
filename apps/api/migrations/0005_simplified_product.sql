ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date date;
ALTER TABLE specialties ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
ALTER TABLE units ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
ALTER TABLE insurers ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS expires_at timestamptz NOT NULL DEFAULT (now() + interval '2 hours');

UPDATE users
SET birth_date = DATE '1990-01-15'
WHERE tenant_id = 'clinic-alyvo'
  AND email = 'juliana.demo@alyvo.local'
  AND birth_date IS NULL;

CREATE TABLE IF NOT EXISTS availability_rules (
  id varchar(36) PRIMARY KEY,
  tenant_id varchar(64) NOT NULL REFERENCES tenants(id),
  doctor_id varchar(36) NOT NULL REFERENCES doctors(id),
  unit_id varchar(36) NOT NULL REFERENCES units(id),
  weekday integer NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  starts_at time NOT NULL,
  ends_at time NOT NULL,
  slot_minutes integer NOT NULL DEFAULT 30 CHECK (slot_minutes BETWEEN 10 AND 240),
  valid_from date,
  valid_until date,
  active boolean NOT NULL DEFAULT true,
  CHECK (starts_at < ends_at)
);
CREATE INDEX IF NOT EXISTS ix_availability_rules_tenant_id ON availability_rules(tenant_id);
CREATE INDEX IF NOT EXISTS ix_availability_rules_doctor_id ON availability_rules(doctor_id);

ALTER TABLE availability_rules ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_availability_rules ON availability_rules;
CREATE POLICY tenant_isolation_availability_rules ON availability_rules
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP TABLE IF EXISTS patient_documents CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS otp_codes CASCADE;
DROP TABLE IF EXISTS services CASCADE;
