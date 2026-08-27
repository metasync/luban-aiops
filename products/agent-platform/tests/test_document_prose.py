"""SPEC-039 R-4: optional clearly-labeled prose layer.

Covers the digest-only prompt contract (no transcript text, evidence
payload, or argument body ever reaches the prompt) and the fail-soft
degradation: a model error, timeout, or empty reply yields
``prose_status=failed`` and the document ships digest-only.
"""

from __future__ import annotations

import asyncio
import json
import inspect

from agent_service.services import document_prose
from agent_service.services.document_prose import (
    build_prose_prompt,
    generate_prose,
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
        # The guardrail phrasing bounds the model to the facts.
        assert "State only what the facts contain" in prompt

    def test_prompt_never_receives_caller_supplied_text(self) -> None:
        # The signature only accepts the digest: there is no channel
        # for transcript text or evidence payloads to enter the prompt.
        params = inspect.signature(build_prose_prompt).parameters
        assert list(params) == ["document_type", "digest"]


class TestGeneration:
    def test_success_returns_included(self) -> None:
        prose, status = asyncio.run(
            generate_prose(
                _FakeKernel(_model_returning([{"type": "text", "text": "Recap: one session."}])),
                "shift_summary",
                _digest(),
            )
        )
        assert status == "included"
        assert prose == "Recap: one session."

    def test_model_build_failure_degrades_to_failed(self) -> None:
        prose, status = asyncio.run(
            generate_prose(
                _FakeKernel(RuntimeError("provider unconfigured")),
                "shift_summary",
                _digest(),
            )
        )
        assert status == "failed"
        assert prose is None

    def test_model_call_failure_degrades_to_failed(self) -> None:
        async def _call(messages, **kwargs):
            raise RuntimeError("upstream 500")

        prose, status = asyncio.run(
            generate_prose(_FakeKernel(_call), "shift_summary", _digest())
        )
        assert (prose, status) == (None, "failed")

    def test_empty_reply_degrades_to_failed(self) -> None:
        prose, status = asyncio.run(
            generate_prose(
                _FakeKernel(_model_returning([{"type": "text", "text": "   "}])),
                "shift_summary",
                _digest(),
            )
        )
        assert (prose, status) == (None, "failed")

    def test_timeout_degrades_to_failed(self, monkeypatch) -> None:
        monkeypatch.setattr(document_prose, "PROSE_TIMEOUT_SECONDS", 0.05)

        async def _hang(messages, **kwargs):
            await asyncio.sleep(5)
            return _FakeResponse([{"type": "text", "text": "late"}])

        prose, status = asyncio.run(
            generate_prose(_FakeKernel(_hang), "shift_summary", _digest())
        )
        assert (prose, status) == (None, "failed")

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

        prose, status = asyncio.run(
            generate_prose(_FakeKernel(_call), "shift_summary", _digest())
        )
        assert status == "included"
        assert prose == "part one. part two."
