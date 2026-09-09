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

SPEC-055 R-2 reuses this vocabulary for a third purpose: parameterizing
the arguments an authoring trace stores, so a literal credential never
reaches a store that outlives the receipts which would otherwise be its
only copy. That projection uses a *different* predicate
(``is_secret_value``) than the fail-closed display masking above — see its
docstring for why the two postures diverge.
"""

from __future__ import annotations

from typing import Any

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

# The placeholder the authoring trace substitutes for a credential value
# (SPEC-055 R-2). Deliberately **not** ``MASK``: ``MASK`` tells an approver
# "a secret is here and withheld", while a trace placeholder tells a
# graduation "this argument has to be supplied from a credential-set
# reference at replay time". It is a hole the operator must fill. R-4's
# blast-radius re-validation (``skill_graduation.revalidate_blast_radius``)
# requires every credential resolved to a credential-set reference, which
# makes a trace still carrying one a deterministic refusal naming the step
# and the argument path. The placeholder is loud either way, where a ``***``
# in stored replay arguments would be indistinguishable from a value the flow
# is supposed to type literally.
#
# Two costs are accepted here and are recorded as R-4/R-5 inputs in tasks.md:
# the per-tool opaque fields (``web.type.text``, ``web.evaluate.expression``)
# placeholder *unconditionally, by name*, so a non-secret value typed through
# them is lost too; and the placeholder is a bare string carrying no record
# of *which* credential set should fill it, because no ``credential_set``
# reference ever reaches a trace under the default configuration (see
# ``is_secret_value``). The reference is supplied by the human completing the
# draft at merge time.
#
# R-4 makes that second cost consequential rather than cosmetic: it refuses a
# trace still holding a hole, and nothing resolves one already stored, so a
# session that typed a credential literally through an opaque field cannot
# graduate at all. That is the intended failure — the refusal says so and
# names the steps — and its remedy is to re-author them filling the credential
# through ``web.fill_credential`` instead, which leaves no hole because that
# tool is read-tier and is never captured, and then to add the reference step
# by hand when merging the draft, because the trace does not carry it either.
#
# The literal is a cross-product twin: skills-hub re-declares it as
# ``ingestion.CREDENTIAL_HOLE`` to refuse an executable-flow document still
# carrying one (SPEC-055 R-3). Renaming it here would silently disable that
# check rather than fail anything, so the ``validate-secret-vocabulary`` leg of
# ``make verify`` extracts both and fails the build on divergence — never
# change one alone.
TRACE_CREDENTIAL_PLACEHOLDER = "<credential-reference>"

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
    # Arbitrary JS can read a masked secret off the page and can *be* the
    # mutation (``document.querySelector('#pw').value = '<literal>'`` is how
    # an agent fills a credential when it does not use
    # ``web.fill_credential``), so the expression is opaque by tool exactly
    # like ``web.type.text``. ``_cr_web_evaluate`` already refuses to project
    # it on a change-request card for the same reason; without this entry the
    # trace projection would be the one place a literal JS-embedded
    # credential survives, into a store that outlives every receipt
    # (SPEC-055 R-2).
    "web.evaluate.expression",
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


# ---------------------------------------------------------------------------
# Authoring-trace parameterization (SPEC-055 R-2)
# ---------------------------------------------------------------------------


def is_secret_value(tool_name: str, param_name: str) -> bool:
    """True when this field's *value* is credential-bearing (SPEC-055 R-2).

    Deliberately **not** ``should_mask``, and the divergence is the point.
    ``should_mask`` is fail-closed because a display/at-rest projection's
    only cost for a false positive is a less informative card. The
    authoring trace has a different cost curve: an argument the trace
    cannot keep is an argument a graduated flow cannot replay, so applying
    the allow-list-only posture here would placeholder every off-list field
    (``web.click.selector``, ``web.navigate.url``,
    ``k8s.restart_service.namespace``) and make every trace un-graduable —
    R-2 would ship non-functional. This predicate therefore targets
    *credential values specifically*: the SPEC-049 R-5 name vocabulary plus
    the per-tool opaque fields, minus the positively-known-safe allow-list.

    The gap that leaves is **bounded, not closed**, and it matters to be
    precise about which half R-4 covers. ``revalidate_blast_radius``
    (``skill_graduation``, R-4) refuses a trace still carrying
    ``TRACE_CREDENTIAL_PLACEHOLDER``, so a credential this vocabulary
    *recognizes* can never graduate unresolved — the refusal names the step
    and the argument path. A literal under a name the vocabulary does not know
    produces no placeholder and is therefore **not** detectable by that check
    either, which leaves the vocabulary below as the only control on what a
    trace stores. What carries the residual risk is that vocabulary's breadth
    — the name substrings plus the per-tool opaque fields, both of which grow
    as new secret shapes are found (see ``web.evaluate.expression``) — and the
    fact that graduation produces a draft a human reviews and merges, never an
    auto-published skill.
    """
    if is_known_safe(tool_name, param_name):
        # Must precede the vocabulary check: ``is_secret_param`` matches
        # "credential" as a substring, so the allow-listed
        # ``web.fill_credential.credential_set`` *reference* — the one field
        # that is the structural fix R-2 is supposed to preserve — would
        # otherwise be placeholdered into uselessness.
        return False
    return is_secret_param(param_name) or is_opaque_value(tool_name, param_name)


def _parameterize_nested(tool_name: str, value: Any) -> Any:
    """Parameterize credential values below the top level of an argument.

    Both the name vocabulary and the per-tool opaque fields apply at depth:
    a nested ``{"form": {"text": ...}}`` handed to ``web.type`` carries the
    same secret as a top-level one, and "the store persists exactly what it
    is given" does not get more forgiving one level down.

    The ``KNOWN_SAFE_FIELDS`` exemption does **not** descend. Its entries
    name curated *top-level* fields (``k8s.delete_pod.name``), so a nested
    field that happens to share the name inherits no exemption — the
    conservative direction, since at depth this can only placeholder more
    than a top-level-only reading would, never less.
    """
    if isinstance(value, dict):
        return {
            str(key): (
                TRACE_CREDENTIAL_PLACEHOLDER
                if is_secret_param(str(key))
                or is_opaque_value(tool_name, str(key))
                else _parameterize_nested(tool_name, item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_parameterize_nested(tool_name, item) for item in value]
    return value


def parameterize_for_trace(tool_name: str, parameters: Any) -> dict:
    """A secret-safe copy of ``parameters`` for the authoring trace (R-2).

    Recurses into nested dicts and lists, unlike ``redact_parameters`` which
    only needs the top level because a change-request card projects
    top-level arguments. A trace is what a graduated flow will *replay*, so
    a credential nested one level down would ride along verbatim into a
    store that outlives the receipts which are otherwise its only copy.

    Returns a fresh dict; the caller's ``parameters`` is never mutated, so
    this cannot perturb the ``args_digest`` a gateway verifies against.
    """
    if not isinstance(parameters, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, value in parameters.items():
        name = str(key)
        safe[name] = (
            TRACE_CREDENTIAL_PLACEHOLDER
            if is_secret_value(tool_name, name)
            else _parameterize_nested(tool_name, value)
        )
    return safe
