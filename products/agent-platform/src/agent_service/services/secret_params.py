"""Secret-parameter vocabulary for the change-request projection (SPEC-054 R-3).

The R-3 change-request card promotes a parked call's decision-relevant
parameters out of the collapsed "Technical details" expander into the
approval intention, with secret-bearing values masked. Masking runs
**kernel-side**, where the tool-gateway's known-secret value set
(``entry.secret_values``, used to mask screenshots) is not available, so
this module carries the vocabulary the projection needs to mask by name
plus a per-tool opaque-value list for secrets that sit in
generically-named fields.

This is a deliberate **second copy** of the gateway's masking vocabulary
(Resolved At Plan Time 2). It is a Python constant rather than a shared
data file on purpose: a masking vocabulary that lived in a mounted file
would fail **open** (nothing gets masked) if the file were missing or
unmounted, whereas a constant has no such failure mode. The twin lives in
``products/tool-gateway/src/tool_gateway/tools/browser_connector.py`` as
``_SECRET_QUERY_PARAMS``; ``shared/shared-contracts/scripts/
validate_secret_vocabulary.py`` (a ``make verify`` leg) fails the build if
the two tuples diverge as sets, so the copies cannot drift silently.
"""

from __future__ import annotations

# Parameter-name substrings whose values are secret-bearing and must never
# enter a change-request projection in plaintext. Matched case-insensitively
# as a substring of the parameter name, so ``newpw``/``newPassword``/
# ``user_password`` all match — the same semantics as the gateway twin.
#
# TWIN: products/tool-gateway/src/tool_gateway/tools/browser_connector.py
# `_SECRET_QUERY_PARAMS`. Keep the two in lockstep; the
# validate-secret-vocabulary `make verify` leg pins them.
SECRET_PARAM_SUBSTRINGS: tuple[str, ...] = (
    "password", "passwd", "pwd", "newpw", "oldpw", "secret", "token",
    "apikey", "api_key", "accesskey", "access_key", "privatekey",
    "private_key", "credential", "otp", "cvv", "ssn", "sessionid",
    "session_id", "signature",
)

# The mask token a secret value is replaced with. The parameter *key* is
# always preserved so the approver sees that a secret is involved without
# seeing it (SPEC-049 R-5 posture, reused by SPEC-054 R-3).
MASK = "***"

# Per-tool opaque-value fields, keyed ``"<canonical.tool.name>.<param>"``:
# masked wholesale regardless of parameter name. Name-based masking is
# necessary but not sufficient — a secret in a generically-named field is
# invisible to ``is_secret_param`` (``web.type``'s ``text`` matches no
# vocabulary entry), and the projection is assembled kernel-side where the
# gateway's known-secret value set is unavailable (SPEC-054 R-3). The
# structural fix is R-2's reference-only credential entry
# (``web.fill_credential``), so a credential never needs to appear as a
# literal argument; this list covers the residual case of a secret typed
# directly into a field.
OPAQUE_VALUE_FIELDS: frozenset[str] = frozenset({
    "web.type.text",
})


def is_secret_param(name: str) -> bool:
    """True when a parameter name bears a secret.

    Case-insensitive substring match — the same semantics as the gateway
    twin ``_is_secret_param`` so the two products mask identically.
    """
    lowered = name.lower()
    return any(secret in lowered for secret in SECRET_PARAM_SUBSTRINGS)


def is_opaque_value(tool_name: str, param_name: str) -> bool:
    """True when this tool's parameter is masked wholesale regardless of name.

    Covers secrets in generically-named fields (``web.type.text``) that
    ``is_secret_param`` cannot catch by name alone.
    """
    return f"{tool_name}.{param_name}" in OPAQUE_VALUE_FIELDS


def should_mask(tool_name: str, param_name: str) -> bool:
    """True when a parameter value must be masked in the change request.

    Masking is **by default** for the projection: a value masks when its
    name is secret-bearing or it sits on the per-tool opaque-value list.
    """
    return is_secret_param(param_name) or is_opaque_value(tool_name, param_name)
