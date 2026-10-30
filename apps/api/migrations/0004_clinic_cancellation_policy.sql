ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS cancellation_notice_hours integer NOT NULL DEFAULT 0;
