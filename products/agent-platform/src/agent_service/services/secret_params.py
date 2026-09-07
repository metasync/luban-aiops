"""Secret-parameter vocabulary for the change-request projection (SPEC-054 R-3).

The R-3 change-request card promotes a parked call's decision-relevant
parameters out of the collapsed "Technical details" expander into the
approval intention, with secret-bearing values masked. Masking runs
**kernel-side**, where the tool-gateway's known-secret value set
(``entry.secret_values``, used to mask screenshots) is not available.

SPEC-055 R-7 flips that masking **fail-closed**: a value masks unless its
``<tool>.<param>`` is positively on the ``KNOWN_SAFE_FIELDS`` allow-list
(``should_mask``), so a secret under an off-vocabulary, generically-named
key can never project as plaintext. ``redact_parameters`` applies the same
posture to the raw ``parameters`` that ride alongside the projection on the
confirmation frame and the durable record. The name-substring vocabulary
below is retained as the twinned record of what counts as secret (it anchors
``is_secret_param`` and the gateway parity check) even though fail-closed
masking no longer depends on a name match.

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

# Per-tool fields whose values are non-secret and may render verbatim in the
# change-request projection and survive raw-parameter redaction. Keyed
# ``"<canonical.tool.name>.<param>"``. SPEC-055 R-7 flips masking fail-closed:
# a field masks unless it is positively listed here, so an off-vocabulary,
# generically-named secret can never project as plaintext. These mirror the
# fields the curated ``_cr_*`` formatters already surface in their effect
# sentences (the pod being deleted, the option selected, the credential set
# *referenced* — never a credential value), so redacting the raw parameters
# stays consistent with the projection instead of masking a value the summary
# already shows.
KNOWN_SAFE_FIELDS: frozenset[str] = frozenset({
    "k8s.delete_pod.name",
    "k8s.delete_pod.namespace",
    "web.select.value",
    "web.fill_credential.credential_set",
    "web.fill_credential.field",
    "web.press_key.key",
    "web.upload_file.filename",
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


def is_known_safe(tool_name: str, param_name: str) -> bool:
    """True when this tool's field is positively allow-listed as non-secret.

    The fail-closed complement of ``should_mask``: only fields named in
    ``KNOWN_SAFE_FIELDS`` may render verbatim (SPEC-055 R-7).
    """
    return f"{tool_name}.{param_name}" in KNOWN_SAFE_FIELDS


def should_mask(tool_name: str, param_name: str) -> bool:
    """True when a parameter value must be masked in the change request.

    **Fail-closed** (SPEC-055 R-7 finding #2): a value masks unless its
    ``<tool>.<param>`` is positively on the ``KNOWN_SAFE_FIELDS`` allow-list.
    The earlier mask-if-known-secret posture (``is_secret_param`` or
    ``is_opaque_value``) failed *open* — a secret under an off-vocabulary,
    generically-named key projected as plaintext. Name-based masking is now
    subsumed: a secret-named field is never allow-listed, so it masks.
    """
    return not is_known_safe(tool_name, param_name)


def redact_parameters(tool_name: str, parameters: dict) -> dict:
    """A display/persistence copy of ``parameters`` with secrets masked.

    SPEC-055 R-7 finding #1: the raw ``parameters`` ride alongside the
    ``change_request`` projection on the confirmation stream frame and the
    durable record, so a secret-bearing value would appear in plaintext on
    both even while the projection masks it. This applies the same fail-closed
    posture at the top level — every value whose key is not positively
    known-safe becomes ``MASK``, keys preserved.

    **Never** applied to a signing input: ``build_requests`` re-reads a fresh
    raw ``pending_calls_payload()`` at resume time and digests that, so the
    ``args_digest`` a gateway verifies is byte-identical to the pre-redaction
    value. Redaction is a pure display + at-rest projection.
    """
    if not isinstance(parameters, dict):
        return {}
    return {
        str(key): MASK if should_mask(tool_name, str(key)) else value
        for key, value in parameters.items()
    }
