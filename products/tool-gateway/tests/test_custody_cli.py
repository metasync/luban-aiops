"""SPEC-070 R-6a/R-6b operator CLI (plan §"Provisioning and operator operations").

Failure-first proof of the backend operator CLI invariants:

* it accepts secret *file paths* (DSN, keyring, refresh token) and never a token
  or DSN literal on the command line;
* it has NO enrollment / manual-user-token command;
* local revoke commits first and reports ``local_revoked_remote_unconfirmed``
  without attempting any remote call;
* the remote-revoke attempt is a single, separately invoked operation that never
  retries, never rolls back the committed local revocation, and degrades to an
  explicit ``remote_unconfirmed`` on a missing endpoint, a missing token, or any
  transport/non-200 result;
* re-encryption is bounded and key rotation / recovery delegate to the explicit
  custody primitives.

These are unit proofs over an injected fake store and an injected remote-revoke
function; the real-Postgres lifecycle they administer is proven separately by
``make delegated-custody-test``.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import httpx
from pydantic import SecretStr

from tool_gateway.services.custody_cli import (
    LOCAL_REVOKE_STATUS,
    REMOTE_REVOKED,
    REMOTE_UNCONFIRMED,
    main,
)
from tool_gateway.tools.delegated_configuration import CALLBACK_PATH

CALLBACK = f"https://portal.test{CALLBACK_PATH}"


def _write_config(root: Path, *, revocation_url: str | None = None) -> tuple[str, str]:
    """Write a valid administered delegated config + linkage; return their paths."""
    mapping = root / "linkage.json"
    mapping.write_text(json.dumps([
        {"owner_namespace": "issuer", "owner_sub": "alice", "target_account": "42"},
        {"owner_namespace": "issuer", "owner_sub": "bob", "target_account": "43"},
    ]))
    entry = {
        "scheme": "oauth2_authorization_code", "target": "Automation",
        "authorization_url": "https://oauth.test/authorize", "token_url": "https://oauth.test/token",
        "renewal_url": "https://oauth.test/token", "identity_url": "https://oauth.test/whoami",
        "client_id": "client", "client_secret": "delegated-client-fixture",
        "client_auth": "client_secret_basic", "redirect_uri": CALLBACK,
        "scope": "read", "allowed_scopes": "read write",
        "oauth_origins": "https://oauth.test", "resource_origins": "https://resource.test",
        "pkce_method": "S256", "store": "postgres", "config_revision": "1",
        "identity_profile": "json_immutable_id", "identity_claim": "id",
        "identity_mapping_path": str(mapping),
        "access_cache_ttl_seconds": "300", "refresh_max_lifetime_seconds": "2592000",
    }
    if revocation_url is not None:
        entry["revocation_url"] = revocation_url
    config = root / "sets.json"
    config.write_text(json.dumps({"user": entry}))
    return str(config), str(mapping)


def _write_secrets(root: Path, *, dsn: str = "postgresql://custody_runtime:pw@postgres:5432/custody",
                   token: str | None = "delegated-refresh-fixture") -> tuple[str, str, str]:
    dsn_file = root / "dsn.txt"
    dsn_file.write_text(dsn + "\n")
    keyring_file = root / "keys.json"
    import base64
    import secrets as _secrets
    keyring_file.write_text(json.dumps({
        "active_key_id": "k1", "recovery_epoch": "epoch1",
        "fingerprint_key": base64.b64encode(_secrets.token_bytes(32)).decode(),
        "keys": {k: base64.b64encode(_secrets.token_bytes(32)).decode() for k in ("k1", "k2")},
    }))
    token_file = root / "refresh.txt"
    if token is not None:
        token_file.write_text(token)
    return str(dsn_file), str(keyring_file), str(token_file)


class _FakeStore:
    """Records the operator calls the CLI makes against the custody store."""

    def __init__(self, *, ready: bool = True, revoke_status: str = LOCAL_REVOKE_STATUS,
                 reencrypt_count: int = 3) -> None:
        self._ready = ready
        self._revoke_status = revoke_status
        self._reencrypt_count = reencrypt_count
        self.calls: list[tuple] = []

    async def ready(self) -> bool:
        self.calls.append(("ready",))
        return self._ready

    async def revoke(self, owner) -> str:
        self.calls.append(("revoke", owner))
        return self._revoke_status

    async def rotate_key(self, expected_key_id: str) -> None:
        self.calls.append(("rotate_key", expected_key_id))

    async def reencrypt(self, *, limit: int = 100) -> int:
        self.calls.append(("reencrypt", limit))
        return self._reencrypt_count


def _run(argv, **deps) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(argv, **deps)
    return code, out.getvalue()


class CustodyCliArgumentDisciplineTests(unittest.TestCase):
    """The CLI takes secret file paths and offers no enrollment surface."""

    def test_no_dsn_literal_argument_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_config(root)
            with self.assertRaises(SystemExit):
                main(["migrate", "--dsn", "postgresql://u:p@h/db", "--keyring-file", "k.json"])

    def test_no_refresh_token_literal_argument_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root, revocation_url="https://oauth.test/revoke")
            _, _, token_file = _write_secrets(root)
            with self.assertRaises(SystemExit):
                main(["remote-revoke", "--config-file", config, "--set-id", "user",
                      "--callback", CALLBACK, "--refresh-token", "literal",
                      "--refresh-token-file", token_file])

    def test_there_is_no_enrollment_or_manual_token_command(self) -> None:
        for command in ("enroll", "authorize", "mint", "token", "user-token", "issue"):
            with self.subTest(command=command), self.assertRaises(SystemExit):
                main([command])


class CustodyCliMigrateRecoverTests(unittest.TestCase):
    def test_migrate_reads_the_dsn_from_a_file_and_delegates(self) -> None:
        recorded: list[tuple] = []

        async def fake_migrate(dsn, keyring):
            # Resolve the lazy keyring snapshot here, while the tempdir mount
            # still exists, to prove migrate received a real file-backed Keyring.
            recorded.append((dsn, keyring.snapshot().active_key_id))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dsn_file, keyring_file, _ = _write_secrets(root, dsn="postgresql://op:pw@postgres:5432/custody")
            code, out = _run(["migrate", "--dsn-file", dsn_file, "--keyring-file", keyring_file],
                             migrate_fn=fake_migrate)
        self.assertEqual(code, 0)
        self.assertIn("migrated", out)
        self.assertEqual(len(recorded), 1)
        dsn, active_key_id = recorded[0]
        self.assertEqual(dsn, "postgresql://op:pw@postgres:5432/custody")
        # The keyring is a lazy Keyring over the file path, never an inlined value.
        self.assertEqual(active_key_id, "k1")

    def test_migrate_refuses_a_missing_dsn_file(self) -> None:
        async def fake_migrate(dsn, keyring):  # pragma: no cover - must not run
            raise AssertionError("migrate must not run without a readable DSN file")

        code, _ = _run(["migrate", "--dsn-file", "/nonexistent/dsn.txt", "--keyring-file", "/nonexistent/k.json"],
                       migrate_fn=fake_migrate)
        self.assertNotEqual(code, 0)

    def test_recover_requires_an_expected_epoch_and_delegates(self) -> None:
        recorded: list[tuple] = []

        async def fake_recover(dsn, keyring, *, expected_epoch):
            recorded.append((dsn, expected_epoch))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["recover", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--expected-epoch", "epoch0"], recover_fn=fake_recover)
        self.assertEqual(code, 0)
        self.assertIn("recovered", out)
        self.assertEqual(recorded, [("postgresql://custody_runtime:pw@postgres:5432/custody", "epoch0")])


class CustodyCliReadinessRevokeTests(unittest.TestCase):
    def _store_factory(self, store):
        def factory(dsn, keyring, config_path, set_id, callback):
            factory.seen = (dsn, config_path, set_id, callback)
            return store
        return factory

    def test_readiness_reports_ready(self) -> None:
        store = _FakeStore(ready=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root)
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["readiness", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--config-file", config, "--set-id", "user", "--callback", CALLBACK],
                             store_factory=self._store_factory(store))
        self.assertEqual(code, 0)
        self.assertIn("ready", out)
        self.assertIn(("ready",), store.calls)

    def test_readiness_reports_not_ready_without_failing_open(self) -> None:
        store = _FakeStore(ready=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root)
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["status", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--config-file", config, "--set-id", "user", "--callback", CALLBACK],
                             store_factory=self._store_factory(store))
        self.assertIn("not_ready", out)
        self.assertNotIn("\nready\n", out)

    def test_local_revoke_commits_and_reports_remote_unconfirmed_without_a_remote_call(self) -> None:
        store = _FakeStore()
        remote_called: list = []

        async def fake_remote(config, refresh_secret):  # pragma: no cover - must not run
            remote_called.append(config)
            return REMOTE_REVOKED

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root, revocation_url="https://oauth.test/revoke")
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["revoke", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--config-file", config, "--set-id", "user", "--callback", CALLBACK,
                              "--owner-namespace", "issuer", "--owner-sub", "alice"],
                             store_factory=self._store_factory(store), remote_revoke_fn=fake_remote)
        self.assertEqual(code, 0)
        self.assertIn(LOCAL_REVOKE_STATUS, out)
        self.assertEqual([c[0] for c in store.calls], ["revoke"])
        owner = store.calls[0][1]
        self.assertEqual((owner.namespace, owner.subject), ("issuer", "alice"))
        self.assertEqual(remote_called, [], "local revoke never attempts a remote call")


class CustodyCliRemoteRevokeTests(unittest.TestCase):
    def _deps(self, attempts: list, result: str):
        async def fake_remote(config, refresh_secret):
            attempts.append((config.value("target"), refresh_secret.get_secret_value()))
            return result
        return fake_remote

    def _base_argv(self, root: Path, *, revocation_url, token):
        config, _ = _write_config(root, revocation_url=revocation_url)
        _, _, token_file = _write_secrets(root, token=token)
        return ["remote-revoke", "--config-file", config, "--set-id", "user",
                "--callback", CALLBACK, "--refresh-token-file", token_file]

    def test_missing_revocation_endpoint_is_remote_unconfirmed_without_a_call(self) -> None:
        attempts: list = []
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._base_argv(Path(tmp), revocation_url=None, token="t")
            code, out = _run(argv, remote_revoke_fn=self._deps(attempts, REMOTE_REVOKED))
        self.assertEqual(code, 0)
        self.assertIn(REMOTE_UNCONFIRMED, out)
        self.assertEqual(attempts, [])

    def test_missing_token_is_remote_unconfirmed_without_a_call(self) -> None:
        attempts: list = []
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._base_argv(Path(tmp), revocation_url="https://oauth.test/revoke", token=None)
            code, out = _run(argv, remote_revoke_fn=self._deps(attempts, REMOTE_REVOKED))
        self.assertEqual(code, 0)
        self.assertIn(REMOTE_UNCONFIRMED, out)
        self.assertEqual(attempts, [])

    def test_a_configured_endpoint_and_token_make_exactly_one_attempt(self) -> None:
        attempts: list = []
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._base_argv(Path(tmp), revocation_url="https://oauth.test/revoke", token="delegated-refresh")
            code, out = _run(argv, remote_revoke_fn=self._deps(attempts, REMOTE_REVOKED))
        self.assertEqual(code, 0)
        self.assertIn(REMOTE_REVOKED, out)
        self.assertEqual(len(attempts), 1, "exactly one remote attempt; never retried")
        self.assertEqual(attempts[0][1], "delegated-refresh")

    def test_a_failed_remote_attempt_is_unconfirmed_and_never_retried(self) -> None:
        attempts: list = []
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._base_argv(Path(tmp), revocation_url="https://oauth.test/revoke", token="delegated-refresh")
            code, out = _run(argv, remote_revoke_fn=self._deps(attempts, REMOTE_UNCONFIRMED))
        self.assertEqual(code, 0)
        self.assertIn(REMOTE_UNCONFIRMED, out)
        self.assertEqual(len(attempts), 1, "an uncertain remote operation is never retried automatically")


class CustodyCliKeyPolicyTests(unittest.TestCase):
    def _store_factory(self, store):
        return lambda dsn, keyring, config_path, set_id, callback: store

    def test_rotate_key_delegates_the_expected_key_id(self) -> None:
        store = _FakeStore()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root)
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["rotate-key", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--config-file", config, "--set-id", "user", "--callback", CALLBACK,
                              "--expected-key-id", "k1"], store_factory=self._store_factory(store))
        self.assertEqual(code, 0)
        self.assertIn(("rotate_key", "k1"), store.calls)

    def test_reencrypt_is_bounded_and_delegates(self) -> None:
        store = _FakeStore(reencrypt_count=7)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root)
            dsn_file, keyring_file, _ = _write_secrets(root)
            code, out = _run(["reencrypt", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                              "--config-file", config, "--set-id", "user", "--callback", CALLBACK,
                              "--limit", "250"], store_factory=self._store_factory(store))
        self.assertEqual(code, 0)
        self.assertIn(("reencrypt", 250), store.calls)
        self.assertIn("7", out)

    def test_reencrypt_rejects_an_out_of_bound_limit(self) -> None:
        store = _FakeStore()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _ = _write_config(root)
            dsn_file, keyring_file, _ = _write_secrets(root)
            for bad in ("0", "1001"):
                with self.subTest(limit=bad):
                    code, _ = _run(["reencrypt", "--dsn-file", dsn_file, "--keyring-file", keyring_file,
                                    "--config-file", config, "--set-id", "user", "--callback", CALLBACK,
                                    "--limit", bad], store_factory=self._store_factory(store))
                    self.assertNotEqual(code, 0)
        self.assertEqual(store.calls, [], "an out-of-bound batch never reaches the store")


class CustodyCliValidateConfigTests(unittest.TestCase):
    def test_validate_config_accepts_a_well_formed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, _ = _write_config(Path(tmp))
            code, out = _run(["validate-config", "--config-file", config, "--set-id", "user",
                              "--callback", CALLBACK])
        self.assertEqual(code, 0)
        self.assertIn("valid", out)

    def test_validate_config_rejects_a_callback_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, _ = _write_config(Path(tmp))
            code, _ = _run(["validate-config", "--config-file", config, "--set-id", "user",
                            "--callback", "https://evil.test" + CALLBACK_PATH])
        self.assertNotEqual(code, 0)

    def test_validate_config_rejects_an_unknown_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config, _ = _write_config(Path(tmp))
            code, _ = _run(["validate-config", "--config-file", config, "--set-id", "nope",
                            "--callback", CALLBACK])
        self.assertNotEqual(code, 0)


class RemoteRevokeClientTests(unittest.IsolatedAsyncioTestCase):
    """The client's single bounded RFC 7009 attempt over the hardened channel."""

    def _client_and_config(self, tmp: Path, *, revocation_url, handler):
        from tool_gateway.tools.user_delegated_client import UserDelegatedClient
        config_path, _ = _write_config(tmp, revocation_url=revocation_url)
        from tool_gateway.tools.delegated_configuration import load_snapshot
        config, _linkage = load_snapshot(config_path, "user", CALLBACK)
        transport = httpx.MockTransport(handler)
        return UserDelegatedClient(custody=None, transport=transport), config

    async def test_a_200_response_is_revoked_over_exactly_one_request(self) -> None:
        seen: list = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={})

        with tempfile.TemporaryDirectory() as tmp:
            client, config = self._client_and_config(Path(tmp), revocation_url="https://oauth.test/revoke",
                                                     handler=handler)
            status = await client.revoke_token(config, SecretStr("delegated-refresh"))
        self.assertEqual(status, REMOTE_REVOKED)
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), "https://oauth.test/revoke")
        self.assertIn(b"token=delegated-refresh", seen[0].read())

    async def test_a_non_200_response_is_remote_unconfirmed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "temporarily_unavailable"})

        with tempfile.TemporaryDirectory() as tmp:
            client, config = self._client_and_config(Path(tmp), revocation_url="https://oauth.test/revoke",
                                                     handler=handler)
            status = await client.revoke_token(config, SecretStr("delegated-refresh"))
        self.assertEqual(status, REMOTE_UNCONFIRMED)

    async def test_a_transport_failure_is_remote_unconfirmed_and_not_retried(self) -> None:
        attempts: list = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(request)
            raise httpx.ConnectError("boom", request=request)

        with tempfile.TemporaryDirectory() as tmp:
            client, config = self._client_and_config(Path(tmp), revocation_url="https://oauth.test/revoke",
                                                     handler=handler)
            status = await client.revoke_token(config, SecretStr("delegated-refresh"))
        self.assertEqual(status, REMOTE_UNCONFIRMED)
        self.assertEqual(len(attempts), 1, "a failed remote revocation is never retried")

    async def test_a_missing_endpoint_makes_no_request(self) -> None:
        attempts: list = []

        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
            attempts.append(request)
            return httpx.Response(200, json={})

        with tempfile.TemporaryDirectory() as tmp:
            client, config = self._client_and_config(Path(tmp), revocation_url=None, handler=handler)
            status = await client.revoke_token(config, SecretStr("delegated-refresh"))
        self.assertEqual(status, REMOTE_UNCONFIRMED)
        self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
