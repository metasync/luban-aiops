"""Closed, local-only v3 execution contracts and signed metadata validation."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from importlib.resources import files
import json
import re
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from execution_runtime.services.execution_signing import (
    canonical_digest, canonical_json, sign_envelope, verify_envelope,
)

SCHEMAS = ("execution-request", "execution-receipt", "execution-observation",
           "execution-recovery", "execution-handoff-response", "tool-result")
METADATA_LIMIT = 8192
MAX_LIFETIME_SECONDS = 900
OBSERVE_SECONDS = 120
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")


class ProtocolError(ValueError):
    """Only closed reason codes cross the service/logging boundary."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@lru_cache(maxsize=1)
def validators():
    resources = {}
    for name in SCHEMAS:
        schema = json.loads(files("execution_runtime").joinpath(
            "contracts", name + ".schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        resources[name] = schema
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema))
                                         for schema in resources.values())
    return {name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            for name, schema in resources.items()}


def validate(name, value):
    # Do not include ValidationError messages or input values in failures/logs.
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
