"""Ingest/query caller authentication tests (SPEC-013 R-3).

Covers the static HTTP Basic registry path, the header parsing, and the
workload bearer path's not-enabled guard. The full projected-token OIDC flow
is exercised through the identity-broker's own workload tests; here we only
assert the audit service reuses that vocabulary correctly.
"""

from __future__ import annotations

import asyncio
import base64
import unittest

from audit_service.core.config import AuditSettings, IngestClient
from audit_service.services.ingest_auth import (
    IngestAuthError,
    _parse_basic,
    authenticate_caller,
    authenticate_static,
    authenticate_workload,
)


def _settings(**overrides) -> AuditSettings:
    defaults = {
        "ingest_clients": (
            IngestClient(client_id="tool-gateway", secret="tg-secret"),
            IngestClient(client_id="platform-gateway", secret="pg-secret"),
        ),
    }
    defaults.update(overrides)
    return AuditSettings(**defaults)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class AuthenticateStaticTests(unittest.TestCase):
    def test_valid_credential_returns_client_id(self) -> None:
        settings = _settings()
        self.assertEqual(
            authenticate_static(settings, "tool-gateway", "tg-secret"),
            "tool-gateway",
        )

    def test_wrong_secret_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, "tool-gateway", "bad")

    def test_unknown_client_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, "intruder", "tg-secret")

    def test_missing_credential_rejected(self) -> None:
        settings = _settings()
        with self.assertRaises(IngestAuthError):
            authenticate_static(settings, None, None)


class ParseBasicTests(unittest.TestCase):
    def test_parses_valid_header(self) -> None:
        header = base64.b64encode(b"tool-gateway:tg-secret").decode()
        self.assertEqual(_parse_basic(header), ("tool-gateway", "tg-secret"))

    def test_invalid_base64_returns_nones(self) -> None:
        self.assertEqual(_parse_basic("!!!not-base64!!!"), (None, None))


class AuthenticateCallerTests(unittest.TestCase):
    def test_basic_header_resolves_client(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": _basic("platform-gateway", "pg-secret")})
        client_id = asyncio.run(authenticate_caller(settings, request))
        self.assertEqual(client_id, "platform-gateway")

    def test_missing_authorization_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))

    def test_bad_basic_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": _basic("tool-gateway", "wrong")})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))

    def test_unsupported_scheme_rejected(self) -> None:
        settings = _settings()
        request = _FakeRequest({"authorization": "Digest abc"})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))


class AuthenticateWorkloadTests(unittest.TestCase):
    def test_workload_not_enabled_rejected(self) -> None:
        settings = _settings(workload_issuer_url="")
        with self.assertRaises(IngestAuthError):
            authenticate_workload(settings, "some-bearer-token")

    def test_bearer_routes_to_workload_path_and_fails_when_disabled(self) -> None:
        settings = _settings(workload_issuer_url="")
        request = _FakeRequest({"authorization": "Bearer abc.def.ghi"})
        with self.assertRaises(IngestAuthError):
            asyncio.run(authenticate_caller(settings, request))


if __name__ == "__main__":
    unittest.main()
