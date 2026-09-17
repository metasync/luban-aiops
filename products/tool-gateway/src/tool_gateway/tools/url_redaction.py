"""Shared URL secret-masking for gateway connectors (SPEC-058 R-6).

The secret-query masking vocabulary and its redaction routine began life
inside ``browser_connector.py`` (SPEC-049 R-5), where the password-reset demo
passes a new password as a query parameter (``?newpw=...``) that must reach
the page but never be serialized into results, evidence, or the audit trail.
SPEC-058 adds an HTTP connector whose ``http.get``/``http.post`` URLs are
model-supplied and are reported through the same evidence envelope, so the
masking has to apply there too. Rather than a second copy of the vocabulary —
which is exactly the drift the ``validate-secret-vocabulary`` leg of
``make verify`` exists to prevent — the routine moves here and both connectors
import it.

This module holds the **gateway** copy. The kernel keeps a deliberate second
copy in ``products/agent-platform/src/agent_service/services/secret_params.py``
(``SECRET_PARAM_SUBSTRINGS``), because the SPEC-054 R-3 change-request
projection is assembled kernel-side where the gateway's known-secret value set
is unavailable. The two tuples are pinned as sets by
``shared/shared-contracts/scripts/validate_secret_vocabulary.py``; never change
one alone.
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit, urlunsplit

# Query-string parameter names whose values are secret-bearing and must
# never enter results, evidence, or the audit trail in plaintext
# (SPEC-049 R-5). Matched case-insensitively as a substring of the
# parameter name, so ``newpw``/``newPassword``/``user_password`` all match.
#
# TWIN: products/agent-platform/src/agent_service/services/secret_params.py
# ``SECRET_PARAM_SUBSTRINGS`` — the SPEC-054 R-3 change-request projection
# masks by the same vocabulary kernel-side. Keep the two in lockstep; the
# validate-secret-vocabulary ``make verify`` leg pins them.
SECRET_QUERY_PARAMS: tuple[str, ...] = (
    "password", "passwd", "pwd", "newpw", "oldpw", "secret", "token",
    "apikey", "api_key", "accesskey", "access_key", "privatekey",
    "private_key", "credential", "otp", "cvv", "ssn", "sessionid",
    "session_id", "signature",
)


def is_secret_param(name: str) -> bool:
    lowered = name.lower()
    return any(secret in lowered for secret in SECRET_QUERY_PARAMS)


def redact_secret_query(url: str) -> str:
    """Mask secret-bearing query-param values in a URL for evidence.

    The password-reset demo passes the new password as a query parameter
    (``?newpw=...``) so the legacy target can auto-fill it; the real value
    must reach the page but must never be serialized into results,
    evidence, or the audit trail (SPEC-049 R-5). Only the value is masked
    (to ``***``); the key stays so the URL shape is still visible. The raw
    query is rewritten segment-by-segment so every non-secret byte is
    preserved exactly (no re-encoding). A URL with no secret-bearing params
    is returned unchanged.
    """
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    changed = False
    # A credential can ride in the userinfo (``scheme://user:password@host``)
    # with no query string at all, so the password is masked independently of
    # the query loop below and an empty query is no longer an early return.
    # Kernel twin of ``secret_params.redact_secret_query`` — keep the two in
    # lockstep. The raw netloc is rewritten by a single first-occurrence
    # replace so every non-secret byte is preserved exactly (no re-encoding).
    netloc = parsed.netloc
    if parsed.password:
        netloc = netloc.replace(f":{parsed.password}@", ":***@", 1)
        changed = True
    segments: list[str] = []
    for segment in parsed.query.split("&"):
        key, sep, _value = segment.partition("=")
        # A bare key with no '=' carries no value to leak; leave it as-is.
        if sep and is_secret_param(unquote(key)):
            segments.append(f"{key}{sep}***")
            changed = True
        else:
            segments.append(segment)
    if not changed:
        return url
    return urlunsplit((
        parsed.scheme, netloc, parsed.path,
        "&".join(segments), parsed.fragment,
    ))
