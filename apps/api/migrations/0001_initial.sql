CREATE EXTENSION IF NOT EXISTS btree_gist;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'appointments_doctor_no_overlap') THEN
    ALTER TABLE appointments
      ADD CONSTRAINT appointments_doctor_no_overlap
      EXCLUDE USING gist (
        tenant_id WITH =,
        doctor_id WITH =,
        tstzrange(starts_at, ends_at, '[)') WITH &&
      ) WHERE (status = 'confirmed');
  END IF;
END $$;

DO $$
DECLARE
  table_name text;
  tables text[] := ARRAY[
    'users', 'specialties', 'units', 'insurers', 'doctors', 'exams', 'services',
    'availability', 'availability_blocks', 'appointments', 'appointment_history',
    'patient_documents', 'knowledge_documents', 'knowledge_chunks', 'tickets',
    'outbox_events', 'audit_events', 'otp_codes', 'refresh_tokens', 'chat_sessions', 'chat_messages'
  ];
BEGIN
  FOREACH table_name IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE %%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %%I FORCE ROW LEVEL SECURITY', table_name);
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = table_name
        AND policyname = table_name || '_tenant_policy'
    ) THEN
      EXECUTE format(
        'CREATE POLICY %%I ON %%I USING (current_setting(''app.tenant_id'', true) = ''*'' OR tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (current_setting(''app.tenant_id'', true) = ''*'' OR tenant_id = current_setting(''app.tenant_id'', true))',
        table_name || '_tenant_policy', table_name
      );
    END IF;
  END LOOP;
END $$;

