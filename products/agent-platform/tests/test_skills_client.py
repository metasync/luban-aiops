"""SPEC-044 R-2: skills-hub validation client.

Covers the structured error hierarchy (not-configured 503, transport/5xx
502, 4xx passthrough), the registered Basic query credential and
request-id forwarding, and the ``(valid, reason)`` result mapping — an
unvalidated draft is never returned by the client on any failure.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services import skills_client
from agent_service.services.skills_client import (
    SkillsClientRejected,
    SkillsDependencyNotConfigured,
    SkillsServiceUnavailable,
    is_configured,
    validate_skill_draft,
)

VALID_DOC = """---
title: KubePodNotReady
description: Pod not ready triage steps.
---

Check the pod events first.
"""


def _settings(**overrides) -> RuntimeSettings:
    base = {
        "skills_service_url": "http://skills-hub:8000",
        "skills_client_secret": "query-secret",
    }
    base.update(overrides)
    return RuntimeSettings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class _FakeAsyncClient:
    def __init__(
        self,
        response: _FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url, json=None, auth=None, headers=None):
        self.requests.append(
            {"url": url, "json": json, "auth": auth, "headers": headers}
        )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _patch_http(monkeypatch, fake: _FakeAsyncClient) -> None:
    def _factory(timeout=None):
        fake.timeout = timeout
        return fake

    monkeypatch.setattr(skills_client.httpx, "AsyncClient", _factory)


class TestSkillsClientConfiguration:
    def test_requires_both_url_and_secret(self) -> None:
        assert is_configured(_settings()) is True
        assert is_configured(_settings(skills_service_url=None)) is False
        assert is_configured(_settings(skills_client_secret=None)) is False

    def test_not_configured_raises_structured(self) -> None:
        with pytest.raises(SkillsDependencyNotConfigured):
            asyncio.run(
                validate_skill_draft(
                    _settings(skills_service_url=None), "req-1", VALID_DOC
                )
            )


class TestSkillsClientValidation:
    def test_success_returns_valid(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(200, {"valid": True}))
        _patch_http(monkeypatch, fake)
        valid, reason = asyncio.run(
            validate_skill_draft(_settings(), "req-42", VALID_DOC)
        )
        assert valid is True
        assert reason is None
        [request] = fake.requests
        assert request["url"] == "http://skills-hub:8000/api/v1/skills/validate"
        # The candidate document is the sole request payload.
        assert request["json"] == {"document": VALID_DOC}
        # The registered Basic query credential, forwarded request id.
        assert request["auth"] == ("agent-service", "query-secret")
        assert request["headers"] == {"x-request-id": "req-42"}
        assert fake.timeout == _settings().skills_client_timeout_seconds

    def test_rejection_returns_ingestion_reason(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                200,
                {
                    "valid": False,
                    "reason": "missing or unterminated frontmatter",
                },
            )
        )
        _patch_http(monkeypatch, fake)
        valid, reason = asyncio.run(
            validate_skill_draft(_settings(), None, "no frontmatter")
        )
        assert valid is False
        assert reason == "missing or unterminated frontmatter"

    def test_401_maps_to_rejected_with_upstream_message(
        self, monkeypatch
    ) -> None:
        fake = _FakeAsyncClient(
            response=_FakeResponse(
                401, {"error": {"code": "UNAUTHORIZED", "message": "bad credential"}}
            )
        )
        _patch_http(monkeypatch, fake)
        with pytest.raises(SkillsClientRejected) as excinfo:
            asyncio.run(validate_skill_draft(_settings(), None, VALID_DOC))
        assert excinfo.value.status_code == 401
        assert excinfo.value.message == "bad credential"

    def test_5xx_maps_to_unavailable(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(response=_FakeResponse(500))
        _patch_http(monkeypatch, fake)
        with pytest.raises(SkillsServiceUnavailable):
            asyncio.run(validate_skill_draft(_settings(), None, VALID_DOC))

    def test_transport_failure_maps_to_unavailable(self, monkeypatch) -> None:
        fake = _FakeAsyncClient(error=httpx.ConnectError("boom"))
        _patch_http(monkeypatch, fake)
        with pytest.raises(SkillsServiceUnavailable):
            asyncio.run(validate_skill_draft(_settings(), None, VALID_DOC))
