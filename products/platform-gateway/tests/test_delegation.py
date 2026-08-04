"""Gateway delegation client tests (SPEC-008 R-4)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jwt as pyjwt

from platform_gateway.core.config import PlatformGatewaySettings
from platform_gateway.services import delegation_client as dc


def _settings(**overrides) -> PlatformGatewaySettings:
    defaults = {
        "identity_service_url": "http://identity-service:8000",
        "service_client_id": "platform-gateway",
        "service_client_secret": "gw-secret",
        "delegation_audience": "tool-gateway",
        "dev_user": "dev.operator",
    }
    defaults.update(overrides)
    return PlatformGatewaySettings(**defaults)


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        dc.reset_delegation_state()

    def tearDown(self) -> None:
        dc.reset_delegation_state()

    def test_miss_then_hit(self) -> None:
        client = dc.get_delegation_client()
        self.assertIsNone(client.get_cached("user-1"))
        client.put("user-1", "delegated-token", 300)
        self.assertEqual(client.get_cached("user-1"), "delegated-token")

    def test_per_user_isolation(self) -> None:
        client = dc.get_delegation_client()
        client.put("user-1", "token-a", 300)
        self.assertIsNone(client.get_cached("user-2"))

    def test_expired_entry_is_evicted(self) -> None:
        client = dc.get_delegation_client()
        client.put("user-1", "token-a", 300)
        # Force the entry past its refresh window.
        entry = client._cache["user-1"]
        object.__setattr__(entry, "refresh_at", 0)
        self.assertIsNone(client.get_cached("user-1"))
        self.assertNotIn("user-1", client._cache)


class ObtainDelegatedTokenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        dc.reset_delegation_state()

    def tearDown(self) -> None:
        dc.reset_delegation_state()

    async def test_returns_none_when_credential_not_configured(self) -> None:
        settings = _settings(service_client_id="", service_client_secret="")
        result = await dc.obtain_delegated_token(settings, "user-1", "subject.jwt")
        self.assertIsNone(result)

    async def test_exchanges_and_caches(self) -> None:
        settings = _settings()
        exchange = AsyncMock(return_value=("delegated-token", 300))
        with patch.object(dc.DelegationClient, "exchange", exchange):
            first = await dc.obtain_delegated_token(settings, "user-1", "subject.jwt")
            second = await dc.obtain_delegated_token(settings, "user-1", "subject.jwt")

        self.assertEqual(first, "delegated-token")
        self.assertEqual(second, "delegated-token")
        # Second call served from cache: only one exchange.
        self.assertEqual(exchange.await_count, 1)

    async def test_exchange_failure_is_non_fatal(self) -> None:
        settings = _settings()
        exchange = AsyncMock(side_effect=RuntimeError("broker down"))
        with patch.object(dc.DelegationClient, "exchange", exchange):
            result = await dc.obtain_delegated_token(settings, "user-1", "subject.jwt")
        self.assertIsNone(result)

    async def test_synthetic_identity_mints_dev_subject_token(self) -> None:
        settings = _settings()
        captured: dict[str, str] = {}

        async def fake_exchange(self, settings, subject_token):
            captured["subject_token"] = subject_token
            return "delegated-token", 300

        with patch.object(dc.DelegationClient, "exchange", fake_exchange):
            result = await dc.obtain_delegated_token(settings, "dev", None)

        self.assertEqual(result, "delegated-token")
        # A local subject token was minted for the synthetic identity.
        claims = pyjwt.decode(
            captured["subject_token"], options={"verify_signature": False}
        )
        self.assertEqual(claims["sub"], "dev")
        self.assertEqual(claims["username"], "dev.operator")
        self.assertEqual(claims["roles"], ["developer"])
        self.assertEqual(claims["aud"], ["platform-gateway"])


class ExchangeRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        dc.reset_delegation_state()

    def tearDown(self) -> None:
        dc.reset_delegation_state()

    async def test_exchange_posts_credential_and_audience(self) -> None:
        settings = _settings()
        client = dc.get_delegation_client()

        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"access_token": "delegated-token", "expires_in": 300}

        class FakeHttp:
            def __init__(self, *args, **kwargs) -> None:
                self.calls: list[dict] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc) -> bool:
                return False

            async def post(self, url, json=None, auth=None, headers=None):
                self.posts = {
                    "url": url,
                    "json": json,
                    "auth": auth,
                    "headers": headers,
                }
                FakeHttp.last = self.posts  # type: ignore[attr-defined]
                return FakeResponse()

        with patch.object(dc.httpx, "AsyncClient", FakeHttp):
            token, expires_in = await client.exchange(settings, "subject.jwt")

        self.assertEqual(token, "delegated-token")
        self.assertEqual(expires_in, 300)
        sent = FakeHttp.last  # type: ignore[attr-defined]
        self.assertTrue(sent["url"].endswith("/api/v1/auth/exchange"))
        self.assertEqual(sent["auth"], ("platform-gateway", "gw-secret"))
        self.assertEqual(
            sent["json"],
            {"subject_token": "subject.jwt", "audience": "tool-gateway"},
        )
        self.assertIsNone(sent["headers"])


class WorkloadTokenTests(unittest.IsolatedAsyncioTestCase):
    """Projected workload-token preference at exchange (SPEC-009 R-3)."""

    def setUp(self) -> None:
        dc.reset_delegation_state()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.token_path = Path(self._tmp.name) / "token"

    def tearDown(self) -> None:
        dc.reset_delegation_state()

    def _patch_http(self) -> "type":
        class FakeResponse:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"access_token": "delegated-token", "expires_in": 300}

        class FakeHttp:
            last = None

            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc) -> bool:
                return False

            async def post(self, url, json=None, auth=None, headers=None):
                FakeHttp.last = {
                    "url": url,
                    "json": json,
                    "auth": auth,
                    "headers": headers,
                }
                return FakeResponse()

        return FakeHttp

    async def test_projected_token_preferred_over_static_credential(self) -> None:
        self.token_path.write_text("projected.jwt\n")
        settings = _settings(workload_token_path=str(self.token_path))
        client = dc.get_delegation_client()
        fake_http = self._patch_http()

        with patch.object(dc.httpx, "AsyncClient", fake_http):
            token, _ = await client.exchange(settings, "subject.jwt")

        self.assertEqual(token, "delegated-token")
        sent = fake_http.last
        self.assertEqual(sent["headers"], {"Authorization": "Bearer projected.jwt"})
        self.assertIsNone(sent["auth"])

    async def test_token_file_is_reread_each_exchange(self) -> None:
        # The kubelet rotates the projected file in place; the client must
        # pick up the new token without a restart.
        self.token_path.write_text("first.jwt")
        settings = _settings(workload_token_path=str(self.token_path))
        client = dc.get_delegation_client()
        fake_http = self._patch_http()

        with patch.object(dc.httpx, "AsyncClient", fake_http):
            await client.exchange(settings, "subject.jwt")
            self.token_path.write_text("second.jwt")
            await client.exchange(settings, "subject.jwt")

        self.assertEqual(
            fake_http.last["headers"], {"Authorization": "Bearer second.jwt"}
        )

    async def test_missing_file_falls_back_to_static_credential(self) -> None:
        settings = _settings(workload_token_path=str(self.token_path))
        client = dc.get_delegation_client()
        fake_http = self._patch_http()

        with (
            patch.object(dc.httpx, "AsyncClient", fake_http),
            self.assertLogs(dc.LOGGER, level="WARNING") as captured,
        ):
            await client.exchange(settings, "subject.jwt")
            await client.exchange(settings, "subject.jwt")

        sent = fake_http.last
        self.assertIsNone(sent["headers"])
        self.assertEqual(sent["auth"], ("platform-gateway", "gw-secret"))
        # The fallback warning is emitted exactly once per process.
        warnings = [r for r in captured.output if "falling back" in r]
        self.assertEqual(len(warnings), 1)

    async def test_delegation_enabled_with_workload_path_only(self) -> None:
        self.token_path.write_text("projected.jwt")
        settings = _settings(
            workload_token_path=str(self.token_path),
            service_client_id="",
            service_client_secret="",
        )
        exchange = AsyncMock(return_value=("delegated-token", 300))
        with patch.object(dc.DelegationClient, "exchange", exchange):
            result = await dc.obtain_delegated_token(settings, "user-1", "subject.jwt")
        self.assertEqual(result, "delegated-token")


if __name__ == "__main__":
    unittest.main()
