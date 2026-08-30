"""SPEC-044 R-1/R-2/R-6 + SPEC-045 R-1: skill-draft generation.

Covers the digest-only prompt contract (the digest bundle is the sole
generation input), the fenced ``skill-frontmatter`` parse contract, the
deterministic post-processing (redaction vocabulary + Skill Format v1
caps), the facts-only skeleton degradation (always format-valid), the
provenance block shape, and the route-level posture: ownership-by-404,
fail-closed validation (503/502), and generation that never raises a 500.
SPEC-045 adds the incident anchor: bundle purity (envelope minus
``triage_raw`` + validated report only, dispatches excluded), the
deterministic 409 triage gate, incident-client error mapping, and the
incident skeleton/provenance shapes.
"""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest
from fastapi.testclient import TestClient

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.metadata import SERVICE_VERSION
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import skill_draft
from agent_service.services.incident_client import (
    IncidentClientRejected,
    IncidentDependencyNotConfigured,
    IncidentNotFound,
    IncidentServiceUnavailable,
)
from agent_service.services.session_store import SESSION_STORE
from agent_service.services.skill_draft import (
    ANCHOR_INCIDENT,
    MAX_BODY_BYTES,
    MAX_DESCRIPTION_CHARS,
    MAX_TAG_CHARS,
    MAX_TAGS,
    MAX_TITLE_CHARS,
    MODE_GENERATED,
    MODE_SKELETON,
    NoValidatedTriageReport,
    REDACTION_MARKER,
    assemble_markdown,
    build_incident_skeleton,
    build_skeleton,
    build_skill_draft_prompt,
    generate_skill_draft,
    incident_id_from_session,
    parse_model_output,
    postprocess,
    provenance_block,
    slug_from_title,
)


# --- Shared fixtures ---------------------------------------------------------


def _bundle() -> dict:
    return {
        "session_count": 1,
        "sessions": [
            {
                "session_id": "incident-inc-abc123",
                "coverage": "owner",
                "title": "checkout latency",
                "open_items": {"pending_confirmations": 0},
            }
        ],
        "handover": {
            "quiet": False,
            "decisions": [
                {"confirm_id": "cfm-1", "action": "restart", "decision": "approved"}
            ],
            "executions": [
                {
                    "execution_id": "exe-1",
                    "tool_name": "restart_service",
                    "receipt_status": "succeeded",
                }
            ],
        },
    }


def _incident_bundle() -> dict:
    return {
        "incident": {
            "incident_id": "inc-abc123",
            "title": "Checkout latency",
            "severity": "sev2",
            "status": "triaged",
            "summary": "Elevated p99 on checkout.",
            "triage_raw": {"raw": "secret alert payload"},
        },
        "report": {
            "summary": "Triage points at the cache tier.",
            "hypotheses": ["cache eviction storm", "db connection saturation"],
            "next_steps": [{"title": "inspect cache hit ratio"}],
        },
    }


def _incident_service_bundle() -> dict:
    """The incident-service detail shape: envelope + report + dispatches."""
    return {
        "incident": {
            "incident_id": "inc-abc123",
            "title": "Checkout latency",
            "severity": "sev2",
            "status": "triaged",
            "summary": "Elevated p99 on checkout.",
            "session_id": "incident-inc-abc123--alice",
            "triage_raw": {"raw": "secret alert payload"},
        },
        "report": {
            "incident_id": "inc-abc123",
            "session_id": "incident-inc-abc123--alice",
            "summary": "Triage points at the cache tier.",
            "severity_assessment": "warning",
            "evidence": [{"source": "metrics", "description": "p99 up"}],
            "hypotheses": ["cache eviction storm"],
            "next_steps": [{"title": "inspect cache hit ratio"}],
            "generated_at": "2026-08-30T01:00:00+00:00",
            "generated_by": "alice",
        },
        "dispatches": [
            {"dispatch_id": "dsp-1", "connector": "restart", "status": "done"}
        ],
    }


def _incident_draft_bundle() -> dict:
    """The assembler output the incident route generates from."""
    return {
        "incident": {
            "envelope": {
                "incident_id": "inc-abc123",
                "title": "Checkout latency",
                "severity": "sev2",
                "status": "triaged",
                "summary": "Elevated p99 on checkout.",
            },
            "triage_report": {
                "incident_id": "inc-abc123",
                "summary": "Triage points at the cache tier.",
                "hypotheses": ["cache eviction storm"],
                "next_steps": [{"title": "inspect cache hit ratio"}],
                "evidence": [{"source": "metrics", "description": "p99 up"}],
                "generated_at": "2026-08-30T01:00:00+00:00",
                "generated_by": "alice",
            },
        }
    }


class _FakeResponse:
    def __init__(self, content) -> None:
        self.content = content


class _FakeKernel:
    def __init__(self, model) -> None:
        self.model = model

    def _build_model(self, model_id=None):
        if isinstance(self.model, Exception):
            raise self.model
        return self.model


def _model_returning(content):
    async def _call(messages, **kwargs):
        return _FakeResponse(content)

    return _call


def _fenced(frontmatter: dict, body: str) -> str:
    return (
        "```skill-frontmatter\n"
        + json.dumps(frontmatter)
        + "\n```\n\n"
        + body
    )


# --- Prompt contract (R-1: digest-only input) -------------------------------


class TestPromptContract:
    def test_prompt_carries_bundle_json_only(self) -> None:
        bundle = _bundle()
        prompt = build_skill_draft_prompt(bundle)
        assert json.dumps(bundle, sort_keys=True, default=str) in prompt
        # Anchoring rules bound the model to the digest bundle.
        assert "state only facts present in the digest bundle" in prompt
        assert "Never include secrets, credentials, tokens, hostnames" in prompt
        assert "skill-frontmatter" in prompt

    def test_prompt_signature_accepts_only_the_bundle(self) -> None:
        # There is no channel for transcripts, alert payloads, or evidence
        # payloads to enter the prompt: the bundle is the sole input; the
        # anchor is a shape selector (SPEC-045), never a data channel.
        params = inspect.signature(build_skill_draft_prompt).parameters
        assert list(params) == ["bundle", "rejection_reason", "anchor"]

    def test_incident_anchor_frames_the_triage_record(self) -> None:
        prompt = build_skill_draft_prompt(_bundle(), anchor=ANCHOR_INCIDENT)
        assert "validated triage report of one incident" in prompt
        assert "incident envelope or the triage report section" in prompt
        # The fenced contract and prohibitions are anchor-invariant.
        assert "skill-frontmatter" in prompt
        assert "state only facts present in the digest bundle" in prompt
        assert "Never include secrets, credentials, tokens, hostnames" in prompt

    def test_rejection_reason_rides_the_retry_prompt(self) -> None:
        prompt = build_skill_draft_prompt(_bundle(), "missing frontmatter")
        assert "rejected by the format validator" in prompt
        assert "missing frontmatter" in prompt


class TestBundleAssembly:
    def test_incident_leg_strips_raw_alert_payload(self, monkeypatch) -> None:
        monkeypatch.setattr(
            skill_draft,
            "build_session_digest",
            lambda user_id, session_ids, can_view_foreign: (_bundle(), None),
        )

        async def _fetch(settings, request_id, incident_id):
            return _incident_bundle()

        monkeypatch.setattr(skill_draft, "fetch_incident_bundle", _fetch)
        bundle, incident_id = asyncio.run(
            skill_draft.build_skill_draft_bundle(
                RuntimeSettings(), "alice", "incident-inc-abc123", "req-1"
            )
        )
        assert incident_id == "inc-abc123"
        envelope = bundle["incident"]["envelope"]
        # Raw alert payloads never reach the builder.
        assert "triage_raw" not in envelope
        assert envelope["incident_id"] == "inc-abc123"
        assert bundle["incident"]["triage_report"]["summary"]

    def test_incident_leg_degrades_to_digest(self, monkeypatch) -> None:
        from agent_service.services.incident_client import IncidentServiceUnavailable

        monkeypatch.setattr(
            skill_draft,
            "build_session_digest",
            lambda user_id, session_ids, can_view_foreign: (_bundle(), None),
        )

        async def _fetch(settings, request_id, incident_id):
            raise IncidentServiceUnavailable("down")

        monkeypatch.setattr(skill_draft, "fetch_incident_bundle", _fetch)
        bundle, incident_id = asyncio.run(
            skill_draft.build_skill_draft_bundle(
                RuntimeSettings(), "alice", "incident-inc-abc123", "req-1"
            )
        )
        assert incident_id == "inc-abc123"
        # The triage section is enrichment, not a generation dependency.
        assert "incident" not in bundle


# --- Incident-anchored bundle assembly (SPEC-045 R-1) -----------------------


class TestIncidentBundleAssembly:
    def test_bundle_purity(self, monkeypatch) -> None:
        async def _fetch(settings, request_id, incident_id):
            assert incident_id == "inc-abc123"
            return _incident_service_bundle()

        monkeypatch.setattr(skill_draft, "fetch_incident_bundle", _fetch)
        bundle = asyncio.run(
            skill_draft.build_incident_skill_draft_bundle(
                RuntimeSettings(), "req-1", "inc-abc123"
            )
        )
        envelope = bundle["incident"]["envelope"]
        report = bundle["incident"]["triage_report"]
        # Raw, unvalidated agent output never reaches the builder.
        assert "triage_raw" not in envelope
        # The draft never names anyone's session — neither on the
        # envelope (the triage session can name the triage operator)
        # nor on the report.
        assert "session_id" not in envelope
        assert "session_id" not in report
        # Dispatches are action history, not diagnostic technique (Q-3).
        assert "dispatches" not in bundle
        # Nothing outside the envelope + validated report rides the bundle.
        assert set(bundle) == {"incident"}
        assert set(bundle["incident"]) == {"envelope", "triage_report"}
        assert report["summary"] == "Triage points at the cache tier."
        assert envelope["incident_id"] == "inc-abc123"

    @pytest.mark.parametrize("status", ["new", "triaging", "triage_failed"])
    def test_missing_report_raises_per_status(
        self, monkeypatch, status
    ) -> None:
        upstream = _incident_service_bundle()
        upstream["report"] = None
        upstream["incident"]["status"] = status

        async def _fetch(settings, request_id, incident_id):
            return upstream

        monkeypatch.setattr(skill_draft, "fetch_incident_bundle", _fetch)
        with pytest.raises(NoValidatedTriageReport):
            asyncio.run(
                skill_draft.build_incident_skill_draft_bundle(
                    RuntimeSettings(), "req-1", "inc-abc123"
                )
            )

    def test_client_errors_propagate_to_the_route(self, monkeypatch) -> None:
        async def _fetch(settings, request_id, incident_id):
            raise IncidentNotFound(incident_id)

        monkeypatch.setattr(skill_draft, "fetch_incident_bundle", _fetch)
        with pytest.raises(IncidentNotFound):
            asyncio.run(
                skill_draft.build_incident_skill_draft_bundle(
                    RuntimeSettings(), "req-1", "inc-missing"
                )
            )


class TestIncidentIdFromSession:
    def test_incident_session(self) -> None:
        assert incident_id_from_session("incident-inc-abc123") == "inc-abc123"

    def test_operator_suffix_stripped(self) -> None:
        assert (
            incident_id_from_session("incident-inc-abc123--alice") == "inc-abc123"
        )

    def test_plain_session(self) -> None:
        assert incident_id_from_session("ses-1") is None

    def test_non_incident_shape(self) -> None:
        assert incident_id_from_session("incident-notanid") is None


# --- Fenced-contract parsing (R-6) ------------------------------------------


class TestParseModelOutput:
    def test_valid_contract(self) -> None:
        text = _fenced(
            {"title": "Restart the checkout", "description": "When p99 spikes."},
            "# Body\nCheck the cache.",
        )
        parsed = parse_model_output(text)
        assert parsed is not None
        frontmatter, body = parsed
        assert frontmatter["title"] == "Restart the checkout"
        assert body.startswith("# Body")

    def test_missing_fence(self) -> None:
        assert parse_model_output("just a body, no fence") is None

    def test_invalid_json(self) -> None:
        assert parse_model_output("```skill-frontmatter\n{not json}\n```\nBody") is None

    def test_unknown_key_rejected(self) -> None:
        text = _fenced(
            {"title": "t", "description": "d", "evil": "x"}, "Body"
        )
        assert parse_model_output(text) is None

    def test_blank_title_rejected(self) -> None:
        assert parse_model_output(_fenced({"title": "  ", "description": "d"}, "Body")) is None

    def test_empty_body_rejected(self) -> None:
        assert (
            parse_model_output(
                _fenced({"title": "t", "description": "d"}, "")
            )
            is None
        )


# --- Deterministic post-processing (R-6) -----------------------------------


class TestPostprocess:
    def test_redaction_scrubs_secrets(self) -> None:
        body = (
            "Use this token eyJabcdefgh.ijklmnop.qrstuvwx and "
            "Bearer AAAA.BBBB-CCCC_dddd and key AKIA1234567890ABCDEF."
        )
        _, safe_body = postprocess({"title": "t", "description": "d"}, body)
        assert "eyJabcdefgh" not in safe_body
        assert "AKIA1234567890ABCDEF" not in safe_body
        assert REDACTION_MARKER in safe_body

    def test_caps_clamped_regardless_of_model(self) -> None:
        frontmatter = {
            "title": "t" * (MAX_TITLE_CHARS + 50),
            "description": "d" * (MAX_DESCRIPTION_CHARS + 50),
            "tags": ["x" * (MAX_TAG_CHARS + 10)] * (MAX_TAGS + 5),
        }
        safe, _ = postprocess(frontmatter, "body")
        assert len(safe["title"]) == MAX_TITLE_CHARS
        assert len(safe["description"]) == MAX_DESCRIPTION_CHARS
        assert len(safe["tags"]) == MAX_TAGS
        assert all(len(tag) <= MAX_TAG_CHARS for tag in safe["tags"])

    def test_body_truncated_to_cap(self) -> None:
        _, safe_body = postprocess(
            {"title": "t", "description": "d"}, "a" * (MAX_BODY_BYTES + 100)
        )
        assert len(safe_body.encode("utf-8")) <= MAX_BODY_BYTES


# --- Facts-only skeleton (always format-valid) -----------------------------


class TestSkeleton:
    def test_skeleton_is_format_valid(self) -> None:
        frontmatter, body = build_skeleton(_bundle())
        assert frontmatter["title"].strip()
        assert frontmatter["description"].strip()
        assert len(frontmatter["title"]) <= MAX_TITLE_CHARS
        assert len(frontmatter["description"]) <= MAX_DESCRIPTION_CHARS
        assert frontmatter["tags"]
        assert body.strip()

    def test_skeleton_copies_decisions_and_executions(self) -> None:
        _, body = build_skeleton(_bundle())
        assert "cfm-1" in body
        assert "restart_service" in body
        assert "succeeded" in body

    def test_skeleton_quiet_session(self) -> None:
        bundle = _bundle()
        bundle["handover"] = {"quiet": True}
        _, body = build_skeleton(bundle)
        assert "No recorded decisions or executions" in body

    def test_skeleton_uses_incident_facts(self) -> None:
        bundle = _bundle()
        bundle["incident"] = {
            "envelope": _incident_bundle()["incident"],
            "triage_report": _incident_bundle()["report"],
        }
        frontmatter, body = build_skeleton(bundle)
        assert frontmatter["title"].startswith("Triage runbook:")
        assert "cache eviction storm" in body
        assert "inspect cache hit ratio" in body


class TestIncidentSkeleton:
    def test_skeleton_is_format_valid(self) -> None:
        frontmatter, body = build_incident_skeleton(_incident_draft_bundle())
        assert frontmatter["title"].startswith("Triage runbook:")
        assert len(frontmatter["title"]) <= MAX_TITLE_CHARS
        assert frontmatter["description"].strip()
        assert len(frontmatter["description"]) <= MAX_DESCRIPTION_CHARS
        assert frontmatter["tags"]
        assert body.strip()

    def test_skeleton_copies_report_facts_verbatim(self) -> None:
        _, body = build_incident_skeleton(_incident_draft_bundle())
        assert "cache eviction storm" in body
        assert "inspect cache hit ratio" in body
        assert "p99 up" in body
        assert "Triage run by: alice" in body

    def test_skeleton_never_names_a_session(self) -> None:
        _, body = build_incident_skeleton(_incident_draft_bundle())
        assert "incident-inc-abc123" not in body
        assert "session" not in body.lower()

    def test_skeleton_without_report_narrative(self) -> None:
        bundle = _incident_draft_bundle()
        bundle["incident"]["triage_report"] = {}
        frontmatter, body = build_incident_skeleton(bundle)
        assert frontmatter["description"].strip()
        assert "## Context" in body


# --- Provenance + assembly (Q-5) -------------------------------------------


class TestAssembly:
    def test_provenance_block_shape(self) -> None:
        block = provenance_block("ses-1", "inc-abc123", MODE_GENERATED)
        assert block.startswith("<!--")
        assert block.endswith("-->")
        assert "session: ses-1" in block
        assert "incident: inc-abc123" in block
        assert f"platform_version: {SERVICE_VERSION}" in block
        assert f"mode: {MODE_GENERATED}" in block

    def test_provenance_omits_incident_when_absent(self) -> None:
        block = provenance_block("ses-1", None, MODE_SKELETON)
        assert "incident:" not in block

    def test_provenance_incident_anchor_names_no_session(self) -> None:
        # SPEC-045 R-1: the incident-anchored draft carries the incident
        # id only — never anyone's session.
        block = provenance_block(None, "inc-abc123", MODE_GENERATED)
        assert "incident: inc-abc123" in block
        assert "session:" not in block

    def test_assemble_produces_frontmatter_and_provenance(self) -> None:
        markdown, slug = assemble_markdown(
            {"title": "Restart the checkout", "description": "d"},
            "Check the cache.",
            "ses-1",
            None,
            MODE_GENERATED,
        )
        assert markdown.startswith("---\n")
        assert 'title: "Restart the checkout"' in markdown
        assert "session: ses-1" in markdown
        assert "Check the cache." in markdown
        assert slug == "restart-the-checkout"

    def test_slug_fallback(self) -> None:
        assert slug_from_title("") == "skill-draft"
        assert slug_from_title("!!!") == "skill-draft"
        assert slug_from_title("Restart the Checkout!") == "restart-the-checkout"


# --- Bounded generation (fail-soft) ----------------------------------------


class TestGeneration:
    def test_success_parses_contract(self) -> None:
        text = _fenced(
            {"title": "Restart the checkout", "description": "When p99 spikes."},
            "# Body\nCheck the cache.",
        )
        parsed = asyncio.run(
            generate_skill_draft(
                _FakeKernel(_model_returning([{"type": "text", "text": text}])),
                _bundle(),
            )
        )
        assert parsed is not None
        assert parsed[0]["title"] == "Restart the checkout"

    def test_model_build_failure_degrades_to_none(self) -> None:
        parsed = asyncio.run(
            generate_skill_draft(
                _FakeKernel(RuntimeError("provider unconfigured")), _bundle()
            )
        )
        assert parsed is None

    def test_model_call_failure_degrades_to_none(self) -> None:
        async def _call(messages, **kwargs):
            raise RuntimeError("upstream 500")

        assert asyncio.run(
            generate_skill_draft(_FakeKernel(_call), _bundle())
        ) is None

    def test_empty_reply_degrades_to_none(self) -> None:
        assert (
            asyncio.run(
                generate_skill_draft(
                    _FakeKernel(_model_returning([{"type": "text", "text": "  "}])),
                    _bundle(),
                )
            )
            is None
        )

    def test_unparseable_reply_degrades_to_none(self) -> None:
        assert (
            asyncio.run(
                generate_skill_draft(
                    _FakeKernel(
                        _model_returning([{"type": "text", "text": "no fence"}])
                    ),
                    _bundle(),
                )
            )
            is None
        )

    def test_timeout_degrades_to_none(self, monkeypatch) -> None:
        monkeypatch.setattr(skill_draft, "SKILL_DRAFT_TIMEOUT_SECONDS", 0.05)

        async def _hang(messages, **kwargs):
            await asyncio.sleep(5)
            return _FakeResponse([{"type": "text", "text": "late"}])

        assert asyncio.run(
            generate_skill_draft(_FakeKernel(_hang), _bundle())
        ) is None


# --- Route posture (ownership, fail-closed, never-500) --------------------


@pytest.fixture(autouse=True)
def _clean_stores(monkeypatch):
    sessions = getattr(SESSION_STORE, "_sessions", None)
    last_accessed = getattr(SESSION_STORE, "_last_accessed", None)
    if sessions is not None:
        sessions.clear()
    if last_accessed is not None:
        last_accessed.clear()

    emitted: list[dict] = []

    def _capture(settings, event: dict) -> None:
        emitted.append(event)

    monkeypatch.setattr(v2_routes, "emit_audit_event", _capture)
    yield emitted
    if sessions is not None:
        sessions.clear()
    if last_accessed is not None:
        last_accessed.clear()


def _configured_settings() -> RuntimeSettings:
    return RuntimeSettings(
        skills_service_url="http://skills-hub:8000",
        skills_client_secret="s3cret",
    )


def _make_session(client: TestClient, user: str) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": user})
    assert response.status_code == 201
    return response.json()["session_id"]


def _wire_route(
    monkeypatch,
    *,
    configured: bool = True,
    validation=(True, None),
    generation=None,
    bundle=None,
):
    monkeypatch.setattr(v2_routes, "get_settings", lambda: _configured_settings())
    monkeypatch.setattr(
        v2_routes, "skills_validation_configured", lambda settings: configured
    )

    calls = {"validate": 0, "generate": 0}
    validations = list(validation) if isinstance(validation, list) else [validation]

    async def _validate(settings, request_id, markdown):
        index = min(calls["validate"], len(validations) - 1)
        calls["validate"] += 1
        return validations[index]

    monkeypatch.setattr(v2_routes, "validate_skill_draft", _validate)

    generations = generation if isinstance(generation, list) else [generation]

    async def _generate(kernel, bundle_arg, rejection_reason=None):
        index = min(calls["generate"], len(generations) - 1)
        calls["generate"] += 1
        value = generations[index]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(v2_routes, "generate_skill_draft", _generate)

    async def _bundle_fn(settings, user_id, session_id, request_id):
        return (bundle if bundle is not None else _bundle()), None

    monkeypatch.setattr(v2_routes, "build_skill_draft_bundle", _bundle_fn)
    return calls


class TestRoutePosture:
    def _post(self, client, session_id, user="alice"):
        return client.post(
            f"/api/v2/sessions/{session_id}/skill-draft",
            headers={"X-User-ID": user},
        )

    def test_foreign_session_answers_structural_404(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        _wire_route(monkeypatch)
        response = self._post(app_client, session_id, user="bob")
        assert response.status_code == 404

    def test_unknown_session_answers_404(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_route(monkeypatch)
        response = self._post(app_client, "ses-missing")
        assert response.status_code == 404

    def test_validation_not_configured_503(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        _wire_route(monkeypatch, configured=False)
        response = self._post(app_client, session_id)
        assert response.status_code == 503

    def test_generated_mode_returns_validated_draft(
        self, monkeypatch, _clean_stores
    ) -> None:
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        _wire_route(
            monkeypatch,
            generation=({"title": "Restart checkout", "description": "d"}, "Body"),
        )
        response = self._post(app_client, session_id)
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == MODE_GENERATED
        assert body["validation"] == "passed"
        assert body["suggested_filename"] == "restart-checkout.md"
        assert body["markdown"].startswith("---\n")
        event = _clean_stores[-1]
        assert event["event_type"] == "skill_draft_generated"
        assert event["details"]["mode"] == MODE_GENERATED
        assert event["details"]["validation"] == "passed"

    def test_generation_failure_degrades_to_skeleton(self, monkeypatch) -> None:
        # Generation never raises a 500: a model failure yields the
        # facts-only skeleton, which is always format-valid.
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        _wire_route(monkeypatch, generation=None)
        response = self._post(app_client, session_id)
        assert response.status_code == 200
        assert response.json()["mode"] == MODE_SKELETON

    def test_rejection_triggers_one_bounded_regeneration(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        calls = _wire_route(
            monkeypatch,
            validation=[(False, "missing frontmatter"), (True, None)],
            generation=[
                ({"title": "Bad", "description": "d"}, "Body"),
                ({"title": "Good", "description": "d"}, "Body"),
            ],
        )
        response = self._post(app_client, session_id)
        assert response.status_code == 200
        assert response.json()["mode"] == MODE_GENERATED
        assert calls["generate"] == 2
        assert calls["validate"] == 2

    def test_second_validation_failure_degrades_to_skeleton(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        _wire_route(
            monkeypatch,
            # Both generated drafts fail validation; the skeleton passes.
            validation=[(False, "oversize body"), (False, "oversize body"), (True, None)],
            generation=({"title": "Bad", "description": "d"}, "Body"),
        )
        response = self._post(app_client, session_id)
        # The skeleton re-validates on the same path; the operator always
        # holds a format-valid file rather than a 5xx.
        assert response.status_code == 200
        assert response.json()["mode"] == MODE_SKELETON

    def test_validation_unreachable_502(self, monkeypatch) -> None:
        from agent_service.services.skills_client import SkillsServiceUnavailable

        app_client = TestClient(create_app())
        session_id = _make_session(app_client, "alice")
        monkeypatch.setattr(v2_routes, "get_settings", lambda: _configured_settings())
        monkeypatch.setattr(
            v2_routes, "skills_validation_configured", lambda settings: True
        )

        async def _validate(settings, request_id, markdown):
            raise SkillsServiceUnavailable("unreachable")

        monkeypatch.setattr(v2_routes, "validate_skill_draft", _validate)

        async def _generate(kernel, bundle_arg, rejection_reason=None):
            return None

        monkeypatch.setattr(v2_routes, "generate_skill_draft", _generate)

        async def _bundle_fn(settings, user_id, session_id, request_id):
            return _bundle(), None

        monkeypatch.setattr(v2_routes, "build_skill_draft_bundle", _bundle_fn)
        response = self._post(app_client, session_id)
        # An unvalidated draft is never returned.
        assert response.status_code == 502


# --- Incident route posture (SPEC-045 R-1) ----------------------------------


def _wire_incident_route(
    monkeypatch,
    *,
    configured: bool = True,
    validation=(True, None),
    generation=None,
    bundle=None,
    assembler_error=None,
):
    monkeypatch.setattr(v2_routes, "get_settings", lambda: _configured_settings())
    monkeypatch.setattr(
        v2_routes, "skills_validation_configured", lambda settings: configured
    )

    calls = {"validate": 0, "generate": 0}
    validations = list(validation) if isinstance(validation, list) else [validation]

    async def _validate(settings, request_id, markdown):
        index = min(calls["validate"], len(validations) - 1)
        calls["validate"] += 1
        return validations[index]

    monkeypatch.setattr(v2_routes, "validate_skill_draft", _validate)

    generations = generation if isinstance(generation, list) else [generation]

    async def _generate(kernel, bundle_arg, rejection_reason=None, anchor=None):
        index = min(calls["generate"], len(generations) - 1)
        calls["generate"] += 1
        return generations[index]

    monkeypatch.setattr(v2_routes, "generate_skill_draft", _generate)

    async def _bundle_fn(settings, request_id, incident_id):
        if assembler_error is not None:
            raise assembler_error
        return bundle if bundle is not None else _incident_draft_bundle()

    monkeypatch.setattr(
        v2_routes, "build_incident_skill_draft_bundle", _bundle_fn
    )
    return calls


class TestIncidentRoutePosture:
    def _post(self, client, incident_id="inc-abc123", user="bob"):
        return client.post(
            f"/api/v2/incidents/{incident_id}/skill-draft",
            headers={"X-User-ID": user},
        )

    def test_missing_triage_report_answers_409(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            assembler_error=NoValidatedTriageReport("inc-abc123"),
        )
        response = self._post(app_client)
        assert response.status_code == 409
        assert "run triage first" in response.json()["detail"]

    def test_unknown_incident_answers_404(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch, assembler_error=IncidentNotFound("inc-missing")
        )
        response = self._post(app_client, incident_id="inc-missing")
        assert response.status_code == 404

    def test_incident_dependency_not_configured_503(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            assembler_error=IncidentDependencyNotConfigured("not configured"),
        )
        response = self._post(app_client)
        assert response.status_code == 503

    def test_incident_transport_failure_502(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            assembler_error=IncidentServiceUnavailable("down"),
        )
        response = self._post(app_client)
        assert response.status_code == 502

    def test_incident_client_rejected_passes_through(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            assembler_error=IncidentClientRejected(401, "bad credential"),
        )
        response = self._post(app_client)
        assert response.status_code == 401

    def test_validation_not_configured_503(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(monkeypatch, configured=False)
        response = self._post(app_client)
        assert response.status_code == 503

    def test_generated_mode_returns_validated_draft(
        self, monkeypatch, _clean_stores
    ) -> None:
        # The motivating case: a user who does not own the triage session
        # converts the incident's validated triage into a skill.
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            generation=(
                {"title": "Cache tier triage", "description": "d"},
                "Body",
            ),
        )
        response = self._post(app_client, user="bob")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == MODE_GENERATED
        assert body["validation"] == "passed"
        assert body["suggested_filename"] == "cache-tier-triage.md"
        assert body["markdown"].startswith("---\n")
        # Provenance names the incident only — never anyone's session.
        assert "incident: inc-abc123" in body["markdown"]
        assert "session:" not in body["markdown"]
        event = _clean_stores[-1]
        assert event["event_type"] == "incident_skill_draft_generated"
        assert event["details"]["incident_id"] == "inc-abc123"
        assert event["details"]["mode"] == MODE_GENERATED
        assert event["details"]["validation"] == "passed"
        assert "session_id" not in event["details"]

    def test_generation_failure_degrades_to_skeleton(self, monkeypatch) -> None:
        # Generation never raises a 500 on the incident anchor either.
        app_client = TestClient(create_app())
        _wire_incident_route(monkeypatch, generation=None)
        response = self._post(app_client)
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == MODE_SKELETON
        # The incident skeleton's facts ride the degraded draft.
        assert "cache eviction storm" in body["markdown"]

    def test_second_validation_failure_degrades_to_skeleton(self, monkeypatch) -> None:
        app_client = TestClient(create_app())
        _wire_incident_route(
            monkeypatch,
            validation=[(False, "oversize body"), (False, "oversize body"), (True, None)],
            generation=({"title": "Bad", "description": "d"}, "Body"),
        )
        response = self._post(app_client)
        assert response.status_code == 200
        assert response.json()["mode"] == MODE_SKELETON

    def test_validation_unreachable_502(self, monkeypatch) -> None:
        from agent_service.services.skills_client import SkillsServiceUnavailable

        app_client = TestClient(create_app())
        monkeypatch.setattr(v2_routes, "get_settings", lambda: _configured_settings())
        monkeypatch.setattr(
            v2_routes, "skills_validation_configured", lambda settings: True
        )

        async def _validate(settings, request_id, markdown):
            raise SkillsServiceUnavailable("unreachable")

        monkeypatch.setattr(v2_routes, "validate_skill_draft", _validate)

        async def _generate(kernel, bundle_arg, rejection_reason=None, anchor=None):
            return None

        monkeypatch.setattr(v2_routes, "generate_skill_draft", _generate)

        async def _bundle_fn(settings, request_id, incident_id):
            return _incident_draft_bundle()

        monkeypatch.setattr(
            v2_routes, "build_incident_skill_draft_bundle", _bundle_fn
        )
        response = self._post(app_client)
        # An unvalidated draft is never returned.
        assert response.status_code == 502
