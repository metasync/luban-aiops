"""SPEC-039 R-4: clearly-labeled narrative layer (default since SPEC-040 R-2).

Covers the digest-only prompt contract (no transcript text, evidence
payload, or argument body ever reaches the prompt), the SPEC-040 R-2
anchoring rules (every statement traces to a digest section; nothing
absent from the digest may appear), and the fail-soft degradation: a
model error, timeout, or empty reply yields ``prose_status=failed``
and the document ships digest-only.
"""

from __future__ import annotations

import asyncio
import json
import inspect

from agent_service.services import document_prose
from agent_service.services.document_prose import (
    build_prose_prompt,
    generate_prose,
    parse_blurb,
)


def _digest() -> dict:
    return {
        "session_count": 1,
        "sessions": [
            {
                "session_id": "ses-1",
                "coverage": "owner",
                "title": "restart investigation",
                "open_items": {"pending_confirmations": 1},
            }
        ],
    }


class _FakeResponse:
    def __init__(self, content) -> None:
        self.content = content


class _FakeKernel:
    """Stand-in kernel exposing the same _build_model(None) path."""

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


class TestPromptContract:
    def test_prompt_carries_digest_json_only(self) -> None:
        digest = _digest()
        prompt = build_prose_prompt("shift_summary", digest)
        assert (
            json.dumps(
                {"document_type": "shift_summary", "digest": digest},
                sort_keys=True,
                default=str,
            )
            in prompt
        )
        # The SPEC-040 R-2 anchoring rules bound the model to the digest:
        # facts only, tied to their sections, no invented detail.
        assert "state only facts present in the digest" in prompt
        assert "never introduce record ids, causes, recommendations" in prompt
        # A quiet shift must be reported honestly, not filled in.
        assert "quiet=true" in prompt
        # v0.23.3 tuning: a human handover voice, a bounded recap, and
        # the SUMMARY marker that parse_blurb extracts as the one-liner.
        assert "plain, direct, and human" in prompt
        assert "at most three short paragraphs" in prompt
        assert '"SUMMARY:"' in prompt

    def test_prompt_never_receives_caller_supplied_text(self) -> None:
        # The signature only accepts the digest: there is no channel
        # for transcript text or evidence payloads to enter the prompt.
        params = inspect.signature(build_prose_prompt).parameters
        assert list(params) == ["document_type", "digest"]

    def test_incident_prompt_carries_digest_json_only(self) -> None:
        # SPEC-043 R-4: incident reports reuse the digest-only contract
        # with incident-review framing; the raw alert payload, raw
        # triage text, and transcripts never enter through this path.
        digest = {
            "incident": {"incident_id": "inc-abc123", "has_triage_raw": True},
            "triage": {"status": "not_triaged"},
            "dispatches": [],
            "session": {"status": "missing"},
        }
        prompt = build_prose_prompt("incident_report", digest)
        assert (
            json.dumps(
                {"document_type": "incident_report", "digest": digest},
                sort_keys=True,
                default=str,
            )
            in prompt
        )
        assert "incident-review notes" in prompt
        assert "state only facts present in the digest" in prompt
        # The marker guidance keeps the honest-degradation posture.
        assert "not_triaged marker" in prompt
        # Shift framing never leaks into the incident template.
        assert "shift-handover notes" not in prompt


class TestGeneration:
    def test_success_returns_included(self) -> None:
        prose, blurb, status = asyncio.run(
            generate_prose(
                _FakeKernel(
                    _model_returning(
                        [{"type": "text", "text": "Recap: one session."}]
                    )
                ),
                "shift_summary",
                _digest(),
            )
        )
        assert status == "included"
        assert prose == "Recap: one session."
        # No SUMMARY marker: the whole reply stays prose, no blurb.
        assert blurb is None

    def test_success_extracts_the_summary_blurb(self) -> None:
        reply = (
            "SUMMARY: One restart was approved and ran clean.\n"
            "The shift investigated the restart and the approver signed\n"
            "off before it executed."
        )
        prose, blurb, status = asyncio.run(
            generate_prose(
                _FakeKernel(_model_returning([{"type": "text", "text": reply}])),
                "shift_summary",
                _digest(),
            )
        )
        assert status == "included"
        assert blurb == "One restart was approved and ran clean."
        assert prose == (
            "The shift investigated the restart and the approver signed\n"
            "off before it executed."
        )

    def test_model_build_failure_degrades_to_failed(self) -> None:
        prose, blurb, status = asyncio.run(
            generate_prose(
                _FakeKernel(RuntimeError("provider unconfigured")),
                "shift_summary",
                _digest(),
            )
        )
        assert status == "failed"
        assert prose is None
        assert blurb is None

    def test_model_call_failure_degrades_to_failed(self) -> None:
        async def _call(messages, **kwargs):
            raise RuntimeError("upstream 500")

        prose, blurb, status = asyncio.run(
            generate_prose(_FakeKernel(_call), "shift_summary", _digest())
        )
        assert (prose, blurb, status) == (None, None, "failed")

    def test_empty_reply_degrades_to_failed(self) -> None:
        prose, blurb, status = asyncio.run(
            generate_prose(
                _FakeKernel(_model_returning([{"type": "text", "text": "   "}])),
                "shift_summary",
                _digest(),
            )
        )
        assert (prose, blurb, status) == (None, None, "failed")

    def test_timeout_degrades_to_failed(self, monkeypatch) -> None:
        monkeypatch.setattr(document_prose, "PROSE_TIMEOUT_SECONDS", 0.05)

        async def _hang(messages, **kwargs):
            await asyncio.sleep(5)
            return _FakeResponse([{"type": "text", "text": "late"}])

        prose, blurb, status = asyncio.run(
            generate_prose(_FakeKernel(_hang), "shift_summary", _digest())
        )
        assert (prose, blurb, status) == (None, None, "failed")

    def test_streaming_response_drained(self) -> None:
        class _Stream:
            def __aiter__(self):
                async def _gen():
                    yield _FakeResponse([{"type": "text", "text": "part one."}])
                    yield _FakeResponse(
                        [{"type": "text", "text": "part one. part two."}]
                    )

                return _gen()

        async def _call(messages, **kwargs):
            return _Stream()

        prose, blurb, status = asyncio.run(
            generate_prose(_FakeKernel(_call), "shift_summary", _digest())
        )
        assert status == "included"
        assert prose == "part one. part two."
        assert blurb is None


class TestParseBlurb:
    def test_marker_on_first_line_splits(self) -> None:
        blurb, prose = parse_blurb("SUMMARY: All quiet.\nNothing else.")
        assert blurb == "All quiet."
        assert prose == "Nothing else."

    def test_marker_is_case_insensitive(self) -> None:
        blurb, prose = parse_blurb("summary: All quiet.\nBody.")
        assert blurb == "All quiet."
        assert prose == "Body."

    def test_no_marker_leaves_text_as_prose(self) -> None:
        blurb, prose = parse_blurb("A plain recap without a marker.")
        assert blurb is None
        assert prose == "A plain recap without a marker."

    def test_marker_later_than_first_line_is_ignored(self) -> None:
        text = "Intro first.\nSUMMARY: late marker."
        blurb, prose = parse_blurb(text)
        assert blurb is None
        assert prose == text

    def test_blurb_is_bounded(self) -> None:
        long_line = "SUMMARY: " + "x" * 500
        blurb, prose = parse_blurb(long_line + "\nBody.")
        assert blurb is not None
        assert len(blurb) <= document_prose.BLURB_MAX_CHARS
        assert prose == "Body."

    def test_marker_only_reply_keeps_text_as_prose(self) -> None:
        blurb, prose = parse_blurb("SUMMARY: Just the one-liner.")
        assert blurb == "Just the one-liner."
        # Nothing after the marker: the one-liner stands as the prose
        # (marker stripped) so the narrative panel never renders empty.
        assert prose == "Just the one-liner."

    def test_empty_text(self) -> None:
        assert parse_blurb("") == (None, "")
