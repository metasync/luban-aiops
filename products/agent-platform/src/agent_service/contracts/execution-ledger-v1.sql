-- SPEC-063 additive migration. Executed in one explicit migrator transaction.
-- No reference to legacy execution_records and no session deletion cascade.
CREATE FUNCTION execution_json_strings(value jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT bool_and(jsonb_typeof(v) = 'string') FROM jsonb_each(value) AS fields(k,v);
$$;

CREATE TABLE execution_protocol_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    schema_version integer NOT NULL CHECK (schema_version = 1),
    admission_epoch uuid NOT NULL,
    admission_enabled boolean NOT NULL DEFAULT false,
    schema_fingerprint text NOT NULL CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$')
);

CREATE TABLE execution_runs (
    run_id uuid PRIMARY KEY,
    session_id varchar(256) NOT NULL CHECK (length(session_id) > 0),
    owner_user_id varchar(256) NOT NULL CHECK (length(owner_user_id) > 0),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    stopped_at timestamptz,
    stop_reason varchar(64),
    CHECK ((stopped_at IS NULL) = (stop_reason IS NULL)),
    CHECK (stop_reason IS NULL OR stop_reason IN (
        'wait_expired', 'transport_error', 'response_invalid', 'receipt_unconfirmed',
        'run_stopped', 'predecessor_unresolved', 'send_lock_unavailable', 'shutdown',
        'integrity_conflict', 'metadata_replay', 'store_unavailable', 'claim_commit_unconfirmed',
        'request_expired', 'request_not_yet_valid', 'admission_disabled', 'epoch_mismatch',
        'gateway_not_configured', 'credential_missing', 'request_missing', 'schema_invalid'))
);

CREATE TABLE execution_intents (
    execution_id uuid PRIMARY KEY,
    confirm_id uuid NOT NULL,
    call_id varchar(256) NOT NULL CHECK (length(call_id) > 0),
    run_id uuid NOT NULL REFERENCES execution_runs(run_id),
    request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    request_envelope jsonb NOT NULL,
    attempt_request_id varchar(256) NOT NULL CHECK (attempt_request_id ~ '^[A-Za-z0-9_.:-]+$'),
    requested_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    registration_seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    UNIQUE (confirm_id, call_id),
    UNIQUE (execution_id, confirm_id, call_id, request_digest),
    CHECK (expires_at > requested_at AND expires_at <= requested_at + interval '900 seconds'),
    CHECK (jsonb_typeof(request_envelope) = 'object' AND octet_length(request_envelope::text) <= 8192),
    CHECK (request_envelope ?& ARRAY['protocol_version','execution_id','confirm_id','call_id',
        'session_id','owner_user_id','decider_user_id','tool_name','args_digest','requested_at',
        'expires_at','run_id','admission_epoch','approval_kind','signature']),
    CHECK (request_envelope - ARRAY['protocol_version','execution_id','confirm_id','call_id',
        'session_id','owner_user_id','decider_user_id','tool_name','args_digest','requested_at',
        'expires_at','run_id','admission_epoch','approval_kind','signature'] = '{}'::jsonb),
    CHECK (request_envelope->'protocol_version' = '3'::jsonb),
    CHECK (execution_json_strings(request_envelope - 'protocol_version')),
    CHECK ((request_envelope->>'admission_epoch')::uuid IS NOT NULL),
    CHECK (execution_id::text = request_envelope->>'execution_id'),
    CHECK (confirm_id::text = request_envelope->>'confirm_id'),
    CHECK (call_id = request_envelope->>'call_id'),
    CHECK (run_id::text = request_envelope->>'run_id'),
    CHECK (requested_at = (request_envelope->>'requested_at')::timestamptz),
    CHECK (expires_at = (request_envelope->>'expires_at')::timestamptz),
    CHECK (request_envelope->>'approval_kind' IN ('action','flow')),
    CHECK (request_envelope->>'args_digest' ~ '^[0-9a-f]{64}$'),
    CHECK (request_envelope->>'signature' ~ '^[0-9a-f]{64}$'),
    CHECK (length(request_envelope->>'tool_name') BETWEEN 1 AND 128),
    CHECK (length(request_envelope->>'session_id') BETWEEN 1 AND 256),
    CHECK (length(request_envelope->>'owner_user_id') BETWEEN 1 AND 256),
    CHECK (length(request_envelope->>'decider_user_id') BETWEEN 1 AND 256)
);
CREATE INDEX execution_intents_run_order ON execution_intents(run_id, registration_seq);
CREATE INDEX execution_intents_expiry ON execution_intents(expires_at);

CREATE TABLE execution_dispatch_claims (
    execution_id uuid PRIMARY KEY,
    confirm_id uuid NOT NULL,
    call_id varchar(256) NOT NULL,
    request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    claim_owner_id uuid NOT NULL,
    claimed_at timestamptz NOT NULL,
    observe_by timestamptz NOT NULL,
    retain_until timestamptz NOT NULL,
    UNIQUE (confirm_id, call_id),
    FOREIGN KEY (execution_id,confirm_id,call_id,request_digest)
        REFERENCES execution_intents(execution_id,confirm_id,call_id,request_digest),
    CHECK (observe_by = claimed_at + interval '120 seconds'),
    CHECK (retain_until >= claimed_at + interval '30 days')
);

CREATE TABLE execution_observation_state (
    execution_id uuid PRIMARY KEY REFERENCES execution_intents(execution_id),
    ordinary_count integer NOT NULL DEFAULT 0 CHECK (ordinary_count BETWEEN 0 AND 64),
    duplicate_count integer NOT NULL DEFAULT 0 CHECK (duplicate_count BETWEEN 0 AND 2147483647),
    overflow_count integer NOT NULL DEFAULT 0 CHECK (overflow_count BETWEEN 0 AND 2147483647),
    integrity_conflict boolean NOT NULL DEFAULT false,
    overflow boolean NOT NULL DEFAULT false,
    first_conflicting_digest text CHECK (first_conflicting_digest ~ '^[0-9a-f]{64}$')
);

CREATE TABLE execution_observations (
    observation_id uuid PRIMARY KEY,
    execution_id uuid NOT NULL REFERENCES execution_intents(execution_id),
    insertion_seq bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    inserted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source text NOT NULL CHECK (source IN ('agent','worker')),
    kind text NOT NULL,
    reserved_slot text CHECK (reserved_slot IN ('claim','result','timeout','stop','acceptance','conflict')),
    payload jsonb NOT NULL,
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    UNIQUE (execution_id, reserved_slot),
    CHECK (jsonb_typeof(payload) = 'object' AND octet_length(payload::text) <= 8192),
    CHECK (payload ?& ARRAY['observation_version','observation_id','execution_id','run_id',
        'request_digest','source','kind','observed_at','attempt_request_id','request_id','reason_code','signature']),
    CHECK (payload - ARRAY['observation_version','observation_id','execution_id','run_id',
        'request_digest','source','kind','observed_at','attempt_request_id','request_id','reason_code','signature',
        'claim_owner_id','receipt_digest','tool_status','receipt'] = '{}'::jsonb),
    CHECK (payload->'observation_version' = '1'::jsonb),
    CHECK (execution_json_strings(payload - ARRAY['observation_version','receipt'])),
    CHECK ((payload->>'run_id')::uuid IS NOT NULL),
    CHECK (payload->>'observation_id' = observation_id::text),
    CHECK (payload->>'execution_id' = execution_id::text),
    CHECK (payload->>'source' = source AND payload->>'kind' = kind),
    CHECK (payload->>'request_digest' ~ '^[0-9a-f]{64}$' AND payload->>'signature' ~ '^[0-9a-f]{64}$'),
    CHECK (length(payload->>'attempt_request_id') BETWEEN 1 AND 256),
    CHECK (length(payload->>'request_id') BETWEEN 1 AND 256),
    CHECK (payload->>'reason_code' IN (
        'none','unauthorized','bad_request','signing_unavailable','signature_invalid',
        'args_digest_mismatch','request_missing','identity_conflict','protocol_unsupported',
        'request_expired','request_not_yet_valid','lifetime_invalid','admission_disabled',
        'epoch_mismatch','store_unavailable','schema_invalid','claim_commit_unconfirmed',
        'gateway_not_configured','credential_missing','wait_expired','transport_error',
        'response_invalid','receipt_unconfirmed','run_stopped','predecessor_unresolved',
        'send_lock_unavailable','shutdown','integrity_conflict','metadata_replay')),
    CHECK ((source = 'agent' AND kind IN ('wait_expired','transport_uncertain',
        'pre_dispatch_refused','response_accepted','run_stopped')) OR
        (source = 'worker' AND kind IN ('claim_committed','transport_uncertain','pre_dispatch_refused',
        'worker_result','result_persistence_unconfirmed','run_stopped','duplicate_seen'))),
    CHECK ((kind = 'worker_result') = (payload ? 'receipt')),
    CHECK ((kind = 'worker_result') = (payload ? 'tool_status')),
    CHECK ((kind IN ('worker_result','claim_committed')) = (payload ? 'claim_owner_id')),
    CHECK ((kind IN ('worker_result','response_accepted')) = (payload ? 'receipt_digest')),
    CHECK (NOT (payload ? 'receipt') OR (
        jsonb_typeof(payload->'receipt') = 'object' AND execution_json_strings(payload->'receipt') AND
        payload->'receipt' ?& ARRAY['execution_id','status','outcome_digest','request_id','completed_at','signature'] AND
        (payload->'receipt') - ARRAY['execution_id','status','outcome_digest','request_id','completed_at','signature'] = '{}'::jsonb AND
        payload->'receipt'->>'execution_id' = execution_id::text AND
        payload->'receipt'->>'status' IN ('succeeded','failed','timeout') AND
        payload->'receipt'->>'outcome_digest' ~ '^[0-9a-f]{64}$' AND
        payload->'receipt'->>'signature' ~ '^[0-9a-f]{64}$'))
);
CREATE INDEX execution_observations_order ON execution_observations(execution_id,insertion_seq);

CREATE FUNCTION execution_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('luban.execution_retention', true) = 'on' THEN
        IF EXISTS (SELECT 1 FROM execution_intents i WHERE i.execution_id = OLD.execution_id
                   AND i.expires_at + interval '30 days' > clock_timestamp()) THEN
            RAISE EXCEPTION 'execution retention horizon not reached';
        END IF;
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'immutable execution evidence';
END;
$$;
CREATE TRIGGER execution_intents_immutable BEFORE UPDATE OR DELETE ON execution_intents
    FOR EACH ROW EXECUTE FUNCTION execution_immutable();
CREATE TRIGGER execution_claims_immutable BEFORE UPDATE OR DELETE ON execution_dispatch_claims
    FOR EACH ROW EXECUTE FUNCTION execution_immutable();
CREATE TRIGGER execution_observations_immutable BEFORE UPDATE OR DELETE ON execution_observations
    FOR EACH ROW EXECUTE FUNCTION execution_immutable();

CREATE FUNCTION execution_run_monotonic() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.session_id IS DISTINCT FROM OLD.session_id
       OR NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id OR NEW.started_at IS DISTINCT FROM OLD.started_at
       OR (OLD.stopped_at IS NOT NULL AND
           (NEW.stopped_at IS DISTINCT FROM OLD.stopped_at OR NEW.stop_reason IS DISTINCT FROM OLD.stop_reason)) THEN
        RAISE EXCEPTION 'execution run is monotonic';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER execution_run_monotonic BEFORE UPDATE ON execution_runs
    FOR EACH ROW EXECUTE FUNCTION execution_run_monotonic();

CREATE FUNCTION execution_observation_monotonic() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.execution_id IS DISTINCT FROM OLD.execution_id OR NEW.ordinary_count < OLD.ordinary_count
       OR NEW.duplicate_count < OLD.duplicate_count OR NEW.overflow_count < OLD.overflow_count
       OR (OLD.integrity_conflict AND NOT NEW.integrity_conflict) OR (OLD.overflow AND NOT NEW.overflow)
       OR (OLD.first_conflicting_digest IS NOT NULL AND
           NEW.first_conflicting_digest IS DISTINCT FROM OLD.first_conflicting_digest) THEN
        RAISE EXCEPTION 'execution observation state is monotonic';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER execution_observation_monotonic BEFORE UPDATE ON execution_observation_state
    FOR EACH ROW EXECUTE FUNCTION execution_observation_monotonic();
