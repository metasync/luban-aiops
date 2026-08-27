"""Signed execution envelopes — worker copy (SPEC-037 contract, SPEC-038 R-2).

Canonicalization, digests, and HMAC-SHA256 signing for the execution
envelopes defined by ``execution-request.schema.json`` and
``execution-receipt.schema.json``. Both envelopes sign the canonical
JSON of every field except ``signature`` itself; canonicalization is
defined once per product copy (sorted keys, no insignificant
whitespace), and the two copies are pinned together by cross-verification
tests: an envelope signed by agent-platform verifies here and vice
versa, so the resume path that signs and the worker that verifies can
never drift apart.

The signing key is provisioned by the deploy chain
(``sync-execution-signing-secret.sh``) and surfaced as
``EXECUTION_SIGNING_KEY`` on the worker. A missing key never silently
degrades to unsigned execution — every handoff fails closed
(SPEC-038 R-2). The worker only verifies request envelopes and signs
receipts; it never constructs execution requests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

# Rejection reasons carried by ``execution_rejected`` audit events and
# structured handoff rejections (SPEC-037 R-2/R-3, SPEC-038 R-2).
REASON_UNAUTHORIZED = "unauthorized"
REASON_SIGNATURE_INVALID = "signature_invalid"
REASON_ARGS_DIGEST_MISMATCH = "args_digest_mismatch"


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
