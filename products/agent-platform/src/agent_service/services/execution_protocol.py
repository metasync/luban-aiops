"""Agent-side local v3 contracts; canonical vectors are checked against the worker."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from importlib.resources import files
import json
import os
import re
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from agent_service.services.execution_signing import canonical_digest, canonical_json, sign_envelope, verify_envelope

SCHEMAS = ("execution-request", "execution-receipt", "execution-observation",
           "execution-recovery", "execution-handoff-response", "tool-result")
METADATA_LIMIT = 8192
MAX_LIFETIME_SECONDS = 900
OBSERVE_SECONDS = 120
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")


class ProtocolError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@lru_cache(maxsize=1)
def validators():
    resources = {}
    for name in SCHEMAS:
        schema = json.loads(files("agent_service").joinpath("contracts", name + ".schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        resources[name] = schema
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema))
                                         for schema in resources.values())
    return {name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            for name, schema in resources.items()}


def validate(name, value):
    try:
        if next(validators()[name].iter_errors(value), None) is not None:
            raise ProtocolError("bad_request")
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ProtocolError("bad_request") from None


def validate_metadata(name, value):
    validate(name, value)
    if len(canonical_json(value).encode()) > METADATA_LIMIT:
        raise ProtocolError("bad_request")


def request_id(value):
    return value if isinstance(value, str) and SAFE_REQUEST_ID.fullmatch(value) else f"req-{uuid4()}"


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (AttributeError, ValueError, OverflowError):
        raise ProtocolError("bad_request") from None


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_request(envelope, key):
    if not isinstance(envelope, dict) or envelope.get("protocol_version") != 3:
        raise ProtocolError("protocol_unsupported")
    validate_metadata("execution-request", envelope)
    if not key:
        raise ProtocolError("signing_unavailable")
    if not verify_envelope(envelope, envelope["signature"], key):
        raise ProtocolError("signature_invalid")
    lifetime = (timestamp(envelope["expires_at"]) - timestamp(envelope["requested_at"])).total_seconds()
    if not 0 < lifetime <= MAX_LIFETIME_SECONDS:
        raise ProtocolError("lifetime_invalid")


def observation(envelope, *, source, kind, attempt_request_id, current_request_id,
                key, reason="none", observed_at=None, **facts):
    value = {"observation_version": 1, "observation_id": str(uuid4()),
             "execution_id": envelope["execution_id"], "run_id": envelope["run_id"],
             "request_digest": canonical_digest(envelope), "source": source, "kind": kind,
             "observed_at": iso(observed_at or datetime.now(timezone.utc)),
             "attempt_request_id": attempt_request_id, "request_id": current_request_id,
             "reason_code": reason, **facts}
    value["signature"] = sign_envelope(value, key)
    validate_observation(value, envelope, key)
    return value


def validate_observation(value, envelope, key):
    validate_metadata("execution-observation", value)
    if not key or not verify_envelope(value, value["signature"], key):
        raise ProtocolError("signature_invalid")
    if (value["execution_id"] != envelope["execution_id"] or value["run_id"] != envelope["run_id"]
            or value["request_digest"] != canonical_digest(envelope)):
        raise ProtocolError("identity_conflict")
    if value["kind"] == "worker_result":
        receipt = value["receipt"]
        if not verify_envelope(receipt, receipt["signature"], key):
            raise ProtocolError("signature_invalid")
        if (receipt["execution_id"] != envelope["execution_id"]
                or receipt["request_id"] != value["attempt_request_id"]
                or value["receipt_digest"] != canonical_digest(receipt)
                or (value["tool_status"] == "success") != (receipt["status"] == "succeeded")):
            raise ProtocolError("identity_conflict")


_ORIGINAL_AUTHORITY = object()


class VerifiedOriginal:
    """An in-process validated response, not a secret-release/continuation permit."""
    __slots__ = ("_payload", "_attempt_id", "_current_id", "_pid")

    def __init__(self, authority, payload, attempt_id, current_id):
        if authority is not _ORIGINAL_AUTHORITY:
            raise TypeError("original responses require complete wire validation")
        self._payload = canonical_json(payload)
        self._attempt_id, self._current_id, self._pid = attempt_id, current_id, os.getpid()

    @property
    def observation(self):
        return json.loads(self._payload)["observation"]

    @property
    def result(self):
        return json.loads(self._payload)["result"]

    @property
    def recovery(self):
        return json.loads(self._payload)["recovery"]

    def revalidate(self, envelope, key):
        if self._pid != os.getpid():
            raise ProtocolError("response_invalid")
        _validate_original(json.loads(self._payload), envelope, key, self._attempt_id, self._current_id)

    def __reduce__(self):
        raise TypeError("original response authority cannot be serialized")

    def __copy__(self):
        raise TypeError("original response authority cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("original response authority cannot be copied")


def _validate_original(payload, envelope, key, attempt_id, current_id):
    validate_request(envelope, key)
    validate("execution-handoff-response", payload)
    if payload["kind"] != "original_result":
        raise ProtocolError("metadata_replay")
    fact, recovery, result = payload["observation"], payload["recovery"], payload["result"]
    validate_observation(fact, envelope, key)
    receipt = fact["receipt"]
    expected_status = ("succeeded" if result["status"] == "success" else
                       "timeout" if (result.get("error") or {}).get("code") == "TIMEOUT" else "failed")
    if (payload["request_id"] != current_id or fact["request_id"] != current_id
            or fact["attempt_request_id"] != attempt_id or fact["source"] != "worker"
            or result["tool_name"] != envelope["tool_name"] or fact["tool_status"] != result["status"]
            or receipt["status"] != expected_status or receipt["outcome_digest"] != canonical_digest(result)
            or (result["status"] == "success" and ("data" not in result or result.get("error")))
            or (result["status"] != "success" and not result.get("error"))
            or recovery["availability"] != "available" or recovery["run_stopped"]
            or recovery["integrity_conflict"] or recovery["receipt"] != receipt
            or recovery["request_digest"] != canonical_digest(envelope)
            or recovery["attempt_request_id"] != attempt_id or not recovery["claimed_at"]
            or not recovery["target_verification_required"]):
        raise ProtocolError("response_invalid")
    for name in ("execution_id", "run_id", "admission_epoch", "session_id", "confirm_id", "call_id",
                 "tool_name", "requested_at", "expires_at"):
        if recovery[name] != envelope[name]:
            raise ProtocolError("response_invalid")
    for item in recovery["observations"]:
        validate_observation(item, envelope, key)
        if item["attempt_request_id"] != attempt_id:
            raise ProtocolError("response_invalid")


def validate_original(payload, envelope, key, attempt_id, current_id):
    """Validate before changing a display copy or allowing agent acceptance."""
    try:
        _validate_original(payload, envelope, key, attempt_id, current_id)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ProtocolError("response_invalid") from None
    return VerifiedOriginal(_ORIGINAL_AUTHORITY, payload, attempt_id, current_id)
