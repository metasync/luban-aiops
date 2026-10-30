-- SPEC-070 explicit v1 -> v2 upgrade, in the migrator's fenced transaction.
-- Historical envelopes, receipts, dispatch claims, and monotonic stops are untouched.
DO $$
DECLARE
    closed_constraint text;
    matches integer;
BEGIN
    SELECT count(*), min(conname) INTO matches, closed_constraint
    FROM pg_constraint
    WHERE conrelid='public.execution_intents'::regclass AND contype='c'
      AND position('request_envelope - ARRAY[' in pg_get_constraintdef(oid)) > 0;
    IF matches <> 1 THEN
        RAISE EXCEPTION 'execution closed envelope constraint unavailable';
    END IF;
    EXECUTE format('ALTER TABLE execution_intents DROP CONSTRAINT %I', closed_constraint);
END;
$$;

ALTER TABLE execution_intents ADD CONSTRAINT execution_envelope_closed CHECK (
    request_envelope - ARRAY['protocol_version','execution_id','confirm_id','call_id',
        'session_id','owner_user_id','decider_user_id','tool_name','args_digest','requested_at',
        'expires_at','run_id','admission_epoch','approval_kind','signature',
        'requester_namespace','requester_sub','decider_namespace','decider_sub'] = '{}'::jsonb
);
ALTER TABLE execution_intents ADD CONSTRAINT execution_delegated_identity_group CHECK (
    NOT (request_envelope ?| ARRAY['requester_namespace','requester_sub','decider_namespace','decider_sub'])
    OR (
        request_envelope ?& ARRAY['requester_namespace','requester_sub','decider_namespace','decider_sub']
        AND length(request_envelope->>'requester_namespace') BETWEEN 1 AND 256
        AND length(request_envelope->>'requester_sub') BETWEEN 1 AND 256
        AND length(request_envelope->>'decider_namespace') BETWEEN 1 AND 256
        AND length(request_envelope->>'decider_sub') BETWEEN 1 AND 256
    )
);
-- The existing execution_json_strings constraint rejects JSON null and non-strings.
ALTER TABLE execution_protocol_state DROP CONSTRAINT execution_protocol_state_schema_version_check;
ALTER TABLE execution_protocol_state ADD CONSTRAINT execution_protocol_state_schema_version_check CHECK (schema_version = 2) NOT VALID;
UPDATE execution_protocol_state SET schema_version=2;
ALTER TABLE execution_protocol_state VALIDATE CONSTRAINT execution_protocol_state_schema_version_check;
