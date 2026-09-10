"""SPEC-055 R-2: the authoring-trace parameterization surface of
``services/secret_params.py``.

The SPEC-055 R-7 predicates this module adds to (``should_mask``,
``redact_parameters``, ``KNOWN_SAFE_FIELDS``) are asserted where they are
load-bearing — through the confirmation frame and the durable
``pending_calls`` in ``test_hitl_confirmations.py``. This file covers the
R-2 projection, which is a pure function with no frame to ride: the
predicate that decides what counts as a *credential value*, and the
projection that replaces one before an authoring-trace write.

The two surfaces deliberately disagree, and most of what is pinned below is
that disagreement — it is the whole design decision, so it has to fail
loudly if someone "simplifies" one posture into the other.
"""

from __future__ import annotations

import copy

from agent_service.services.secret_params import (
    MASK,
    TRACE_CREDENTIAL_PLACEHOLDER,
    is_secret_param,
    is_secret_value,
    parameterize_for_trace,
    redact_evidence_parameters,
    redact_parameters,
    redact_secret_query,
    should_mask,
)

# --- The predicate: credential values, not "everything unlisted" ------------


def test_the_trace_predicate_diverges_from_fail_closed_masking() -> None:
    """``should_mask`` is fail-closed; ``is_secret_value`` is not, on
    purpose. An off-allow-list but off-vocabulary argument (a CSS selector,
    a URL, a namespace) *must* mask on a change-request card and *must not*
    be placeholdered in a trace — a trace that cannot keep it is a trace a
    graduated flow cannot replay."""
    for tool, param in (
        ("web.click", "selector"),
        ("web.navigate", "url"),
        ("k8s.restart_service", "namespace"),
        ("k8s.scale_deployment", "replicas"),
    ):
        assert should_mask(tool, param) is True
        assert is_secret_value(tool, param) is False


def test_the_allow_list_still_exempts_a_credential_named_reference() -> None:
    """``is_secret_param`` matches "credential" as a substring, so the
    allow-list check has to run first: ``web.fill_credential``'s
    credential-set *reference* is the structural fix R-2 exists to preserve,
    not a value to destroy. Note the two projections still disagree on
    ``field`` — masking is fail-closed, so only the positively allow-listed
    pair survives there too."""
    assert is_secret_param("credential_set") is True
    assert is_secret_value("web.fill_credential", "credential_set") is False
    assert is_secret_value("web.fill_credential", "field") is False


def test_vocabulary_names_and_opaque_fields_are_credential_values() -> None:
    """Both halves of the SPEC-049 R-5 vocabulary carry over: the
    case-insensitive name substrings and the per-tool opaque fields whose
    secrets no name match can catch."""
    assert is_secret_value("k8s.rotate_secret", "password") is True
    assert is_secret_value("admin.login", "newPassword") is True
    assert is_secret_value("admin.login", "api_key") is True
    assert is_secret_value("admin.login", "otp") is True
    # Opaque by tool, not by name — the residual typed-credential case.
    assert is_secret_value("web.type", "text") is True
    # The same parameter name on a different tool is not opaque.
    assert is_secret_value("web.set_attribute", "text") is False


def test_an_allow_listed_field_is_never_a_credential_value() -> None:
    """A positively allow-listed field is never a credential value, so a
    trace keeps the argument a graduation has to replay against — the option
    selected, the pod deleted, the namespace targeted. (The one allow-list
    entry the name vocabulary *would* have matched,
    ``web.fill_credential.credential_set``, is asserted above; ``name`` and
    ``namespace`` match no substring, so the allow-list is not what spares
    them here.)"""
    assert should_mask("k8s.delete_pod", "name") is False
    assert is_secret_value("k8s.delete_pod", "name") is False
    assert is_secret_value("k8s.delete_pod", "namespace") is False
    assert is_secret_value("web.select", "value") is False
    assert parameterize_for_trace(
        "web.select", {"selector": "#role", "value": "admin"}
    ) == {"selector": "#role", "value": "admin"}


# --- The projection -------------------------------------------------------


def test_a_replayable_call_is_kept_verbatim() -> None:
    """The common case: a browser or infra write with no credential in it
    survives intact, types and all, because a graduation replays exactly
    these arguments."""
    parameters = {
        "selector": "#submit",
        "url": "http://admin.local/users",
        "replicas": 3,
        "force": True,
        "labels": None,
    }

    assert parameterize_for_trace("web.click", parameters) == parameters


def test_credential_values_become_references_not_masks() -> None:
    """A credential value becomes the trace placeholder — deliberately not
    ``MASK``, so an operator reading a draft can tell "supply this from a
    credential set" apart from a value the flow types literally."""
    safe = parameterize_for_trace(
        "k8s.rotate_secret", {"name": "db", "password": "s3cret-PASSWORD-xyz"}
    )

    assert safe == {"name": "db", "password": TRACE_CREDENTIAL_PLACEHOLDER}
    assert TRACE_CREDENTIAL_PLACEHOLDER != MASK


def test_an_opaque_field_is_parameterized_by_tool() -> None:
    safe = parameterize_for_trace(
        "web.type", {"selector": "#pw", "text": "hunter2-SECRET"}
    )

    assert safe == {"selector": "#pw", "text": TRACE_CREDENTIAL_PLACEHOLDER}


def test_an_evaluated_expression_is_opaque_whatever_its_name() -> None:
    """``web.evaluate.expression`` is opaque by tool, not by name: no
    substring of "expression" is on the vocabulary, yet the value can *be*
    the mutation (``document.querySelector('#pw').value = '<literal>'``) and
    can read a masked secret back off the page. It is write-tier, in
    ``BROWSER_WRITE_TOOLS`` and already masked by the change-request
    projector, so it reaches a trace — and must not reach it verbatim."""
    assert should_mask("web.evaluate", "expression") is True
    assert is_secret_param("expression") is False

    safe = parameterize_for_trace(
        "web.evaluate",
        {"expression": "document.querySelector('#pw').value = 'hunter2'"},
    )

    assert safe == {"expression": TRACE_CREDENTIAL_PLACEHOLDER}


def test_a_credential_set_reference_survives_the_projection() -> None:
    """The allow-list's precedence over the name vocabulary, asserted at the
    projection. Reachability caveat: ``web.fill_credential`` is read-tier and
    on the default auto-allow list, so under the default configuration this
    call never parks and therefore never enters a trace at all — which is
    precisely why the guarantee is pinned here rather than at the seam (see
    ``test_a_read_tier_parked_call_is_never_captured``)."""
    assert parameterize_for_trace(
        "web.fill_credential",
        {"credential_set": "admin-portal", "field": "password"},
    ) == {"credential_set": "admin-portal", "field": "password"}


def test_the_projection_recurses_into_nested_arguments() -> None:
    """Unlike ``redact_parameters``, which only needs the top level because
    a card projects top-level arguments. A trace is replayed, so a
    credential nested one level down would ride along verbatim."""
    parameters = {
        "target": {"host": "db-1", "password": "n3sted-SECRET"},
        "batch": [
            {"user": "ops", "token": "t0ken-SECRET"},
            {"user": "dev", "role": "viewer"},
        ],
        "options": ("a", "b"),
    }

    safe = parameterize_for_trace("db.grant", parameters)

    assert safe == {
        "target": {"host": "db-1", "password": TRACE_CREDENTIAL_PLACEHOLDER},
        "batch": [
            {"user": "ops", "token": TRACE_CREDENTIAL_PLACEHOLDER},
            {"user": "dev", "role": "viewer"},
        ],
        # A tuple becomes a list: the trace is persisted as JSONB, which has
        # no tuple type, and a graduated step list is JSON too.
        "options": ["a", "b"],
    }


def test_a_deeply_nested_credential_is_still_parameterized() -> None:
    safe = parameterize_for_trace(
        "cfg.apply",
        {"spec": {"template": {"env": [{"name": "OK", "apiKey": "k3y"}]}}},
    )

    assert safe == {
        "spec": {
            "template": {"env": [{"name": "OK", "apiKey": TRACE_CREDENTIAL_PLACEHOLDER}]}
        }
    }


def test_an_opaque_field_is_still_opaque_below_the_top_level() -> None:
    """``is_opaque_value`` needs the tool name, so it only holds at depth if
    the walker is handed one — which it is. A credential typed into a field
    nested inside a composite argument is the same residual case as a
    top-level ``web.type.text``, and losing it at depth would leave the one
    hole the entry exists to close."""
    safe = parameterize_for_trace(
        "web.type", {"form": {"text": "hunter2-SECRET", "selector": "#pw"}}
    )

    assert safe == {
        "form": {
            "text": TRACE_CREDENTIAL_PLACEHOLDER,
            "selector": "#pw",
        }
    }
    assert "hunter2-SECRET" not in str(safe)


def test_the_allow_list_deliberately_does_not_descend() -> None:
    """The nesting walker consults the vocabulary and the opaque fields but
    **not** ``KNOWN_SAFE_FIELDS``. Those are curated ``<tool>.<param>`` pairs
    for the top level of a known tool schema; a key that is safe there is not
    thereby safe inside an arbitrary nested object of an arbitrary tool. The
    trade inverts on purpose: at the top level failing open costs a
    credential, at depth failing closed only costs replayability — and R-4's
    blast-radius re-validation turns an unresolved placeholder into a
    deterministic refusal rather than a silent leak."""
    assert is_secret_value("web.fill_credential", "credential_set") is False

    safe = parameterize_for_trace(
        "some.tool", {"nested": {"credential_set": "admin-portal"}}
    )

    assert safe == {
        "nested": {"credential_set": TRACE_CREDENTIAL_PLACEHOLDER}
    }


def test_the_projection_never_mutates_its_input() -> None:
    """The caller's ``parameters`` is the very object just digested into
    ``args_digest``; mutating it would perturb the signature a gateway
    verifies against. Asserted structurally, not just by comment."""
    parameters = {
        "name": "db",
        "password": "s3cret-PASSWORD-xyz",
        "target": {"token": "t0ken-SECRET"},
    }
    before = copy.deepcopy(parameters)

    parameterize_for_trace("k8s.rotate_secret", parameters)

    assert parameters == before


def test_a_non_dict_argument_projects_to_an_empty_dict() -> None:
    """Same tolerance ``redact_parameters`` has: a malformed parked payload
    yields an empty step rather than raising inside the capture seam."""
    for value in (None, "", [], 7):
        assert parameterize_for_trace("web.click", value) == {}


def test_the_two_projections_stay_independent() -> None:
    """One vocabulary, two postures, neither one silently rewritten in terms
    of the other: the same input masks everything for display and keeps the
    replayable arguments for the trace."""
    parameters = {"selector": "#submit", "password": "s3cret"}

    assert redact_parameters("web.click", parameters) == {
        "selector": MASK,
        "password": MASK,
    }
    assert parameterize_for_trace("web.click", parameters) == {
        "selector": "#submit",
        "password": TRACE_CREDENTIAL_PLACEHOLDER,
    }


# --- The evidence-frame projection: shape kept, secret removed --------------

RESET_URL = "https://browser-check-target/reset?user=alice&newpw=TempPass123%21"


def test_the_query_redactor_masks_the_value_and_preserves_bytes() -> None:
    """The gateway twin's contract, asserted on the kernel copy: the key stays
    so the URL shape is still visible, non-secret params survive untouched, and
    the percent-encoding is not re-encoded on the way through."""
    assert redact_secret_query(RESET_URL) == (
        "https://browser-check-target/reset?user=alice&newpw=" + MASK
    )


def test_the_query_redactor_is_a_no_op_without_a_secret_param() -> None:
    """It is applied to *every* string argument, so a string that carries no
    secret-bearing query must come back byte-identical — including strings
    that are not URLs at all."""
    for value in (
        "https://browser-check-target/reset?user=alice",
        "https://portal/reset",
        "samples/password-reset-resetuserpassword",
        "#reset-status",
        "",
        "?user=alice",
        "a bare key with no equals? newpw",
    ):
        assert redact_secret_query(value) == value


def test_the_evidence_projection_diverges_from_fail_closed_masking() -> None:
    """The whole reason a third posture exists. R-7's ``redact_parameters``
    masks a URL wholesale because a change-request card conveys an intention;
    an evidence frame is the record of what was invoked, so masking it to
    ``***`` would destroy the evidence the panel exists to show. If someone
    "simplifies" one into the other, this fails."""
    parameters = {"url": RESET_URL}

    assert redact_parameters("web.navigate", parameters) == {"url": MASK}
    assert redact_evidence_parameters("web.navigate", parameters) == {
        "url": "https://browser-check-target/reset?user=alice&newpw=" + MASK,
    }


def test_the_evidence_projection_masks_opaque_and_secret_named_fields() -> None:
    """A field whose value *is* the secret keeps no shape worth preserving, so
    it masks wholesale — the per-tool opaque fields (a literal typed into
    ``web.type``, a credential assigned from JS in ``web.evaluate``) and the
    name vocabulary, including a secret-named key holding a container."""
    assert redact_evidence_parameters(
        "web.type", {"selector": "#username", "text": "TempPass123!"},
    ) == {"selector": "#username", "text": MASK}
    assert redact_evidence_parameters(
        "web.evaluate",
        {"expression": "document.querySelector('#pw').value='TempPass123!'"},
    ) == {"expression": MASK}
    assert redact_evidence_parameters(
        "k8s.rotate_secret", {"name": "db", "passwords": ["a1b2c3d4"]},
    ) == {"name": "db", "passwords": MASK}


def test_the_evidence_projection_keeps_a_credential_reference_readable() -> None:
    """``KNOWN_SAFE_FIELDS`` wins over the name vocabulary, exactly as in
    ``is_secret_value``: ``credential_set`` contains "credential", but the
    *reference* is the structural fix that keeps a credential out of the
    arguments at all, so masking it would hide the one thing worth showing."""
    assert redact_evidence_parameters(
        "web.fill_credential",
        {"credential_set": "admin-portal", "field": "#username"},
    ) == {"credential_set": "admin-portal", "field": "#username"}


def test_the_evidence_projection_descends_into_containers() -> None:
    """A secret nested one level down rides into the same persisted frame."""
    assert redact_evidence_parameters(
        "web.navigate",
        {"options": {"referer": RESET_URL}, "urls": [RESET_URL, "plain"]},
    ) == {
        "options": {
            "referer": (
                "https://browser-check-target/reset?user=alice&newpw=" + MASK
            ),
        },
        "urls": [
            "https://browser-check-target/reset?user=alice&newpw=" + MASK,
            "plain",
        ],
    }


def test_the_evidence_projection_never_mutates_its_input() -> None:
    """The caller's ``tool_call`` input is the object the resume path digests
    into ``args_digest``; mutating it would perturb the signature a gateway
    verifies against. Asserted structurally, not just by comment."""
    parameters = {"url": RESET_URL, "nested": {"token": "t0ken-SECRET"}}
    before = copy.deepcopy(parameters)

    redact_evidence_parameters("web.navigate", parameters)

    assert parameters == before


def test_the_evidence_projection_tolerates_a_non_dict_argument() -> None:
    """Same tolerance the other two projections have: a malformed frame yields
    something inert rather than raising inside the evidence seam."""
    assert redact_evidence_parameters("web.navigate", None) is None
    assert redact_evidence_parameters("web.navigate", "") == ""
    assert redact_evidence_parameters("web.navigate", 7) == 7
    assert redact_evidence_parameters("web.navigate", []) == []
    assert redact_evidence_parameters("web.navigate", RESET_URL) == (
        "https://browser-check-target/reset?user=alice&newpw=" + MASK
    )
