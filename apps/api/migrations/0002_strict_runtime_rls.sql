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
    EXECUTE format('DROP POLICY IF EXISTS %%I ON %%I', table_name || '_tenant_policy', table_name);
    EXECUTE format(
      'CREATE POLICY %%I ON %%I USING (tenant_id = current_setting(''app.tenant_id'', true)) WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      table_name || '_tenant_policy', table_name
    );
  END LOOP;
END $$;
