"""Signed execution requests and receipts (SPEC-037 R-1/R-2).

Canonicalization, digests, and HMAC-SHA256 signing for the execution
envelopes defined by ``execution-request.schema.json`` and
``execution-receipt.schema.json``. Both envelopes sign the canonical
JSON of every field except ``signature`` itself; canonicalization is
defined once here (sorted keys, no insignificant whitespace) so the
resume path that signs and the invocation boundary that verifies can
never drift apart.

The signing key is provisioned by the deploy chain
(``sync-execution-signing-secret.sh``) and surfaced as
``AGENT_EXECUTION_SIGNING_KEY``. A missing key never silently degrades
to unsigned execution — the resume path fails closed (SPEC-037 R-2).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from agent_service.services.hitl_confirmations import PendingConfirmation

# Rejection reasons carried by ``execution_rejected`` audit events and
# structured tool errors (SPEC-037 R-2/R-3).
REASON_SIGNING_UNAVAILABLE = "signing_unavailable"
REASON_ARGS_DIGEST_MISMATCH = "args_digest_mismatch"
REASON_REQUEST_MISSING = "request_missing"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace.

    The single canonicalization shared by signing and verification;
    same value ⇒ same serialization regardless of key order.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def canonical_digest(obj: Any) -> str:
    """SHA-256 hex of the canonical JSON of ``obj``."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sign_envelope(envelope: dict[str, Any], key: str) -> str:
    """HMAC-SHA256 hex over the canonical envelope excluding ``signature``."""
    payload = {k: v for k, v in envelope.items() if k != "signature"}
    return hmac.new(
        key.encode("utf-8"),
        canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_envelope(envelope: dict[str, Any], signature: str, key: str) -> bool:
    """Constant-time verification of an envelope signature."""
    expected = sign_envelope(envelope, key)
    return hmac.compare_digest(expected, signature)


def build_requests(
    pending: PendingConfirmation,
    decider_user_id: str,
    key: str,
) -> list[dict[str, Any]]:
    """One signed execution request per parked tool call (SPEC-037 R-2).

    ``args_digest`` binds the envelope to the *parked* arguments — the
    ones the approver saw on the confirmation card. The invocation
    boundary recomputes it from the executed arguments before the
    gateway call goes out (SPEC-037 R-3). Denials never reach this
    builder; the resume path constructs nothing for them.
    """
    requests: list[dict[str, Any]] = []
    for call in pending.pending_calls_payload():
        envelope: dict[str, Any] = {
            "execution_id": str(uuid.uuid4()),
            "confirm_id": pending.confirm_id,
            "call_id": call["call_id"],
            "session_id": pending.session_id,
            "owner_user_id": pending.user_id,
            "decider_user_id": decider_user_id,
            "tool_name": call["tool_name"],
            "args_digest": canonical_digest(call["parameters"]),
            "requested_at": _utc_now_iso(),
        }
        envelope["signature"] = sign_envelope(envelope, key)
        requests.append(envelope)
    return requests


def build_receipt(
    request: dict[str, Any],
    status: str,
    outcome: Any,
    request_id: str,
    key: str,
) -> dict[str, Any]:
    """Sign the receipt closing one execution request (SPEC-037 R-4).

    ``status`` is the mapped receipt outcome (``succeeded`` /
    ``failed`` / ``timeout``); ``outcome`` is the tool result the
    receipt is built from — digested, never stored in full. The
    correlating ``request_id`` is the resumed stream's x-request-id.
    """
    envelope: dict[str, Any] = {
        "execution_id": request["execution_id"],
        "status": status,
        "outcome_digest": canonical_digest(outcome),
        "request_id": request_id,
        "completed_at": _utc_now_iso(),
    }
    envelope["signature"] = sign_envelope(envelope, key)
    return envelope
