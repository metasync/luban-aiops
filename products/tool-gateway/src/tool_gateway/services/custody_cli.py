"""SPEC-070 R-6a/R-6b backend operator CLI for delegated-custody administration.

Explicit, auditable administration of the gateway-owned custody runtime. It is
the operator surface the plan's §"Provisioning and operator operations" requires:
migrate, readiness/status, local revoke, a single remote-revoke attempt,
key-policy rotation, bounded re-encryption, and externally fenced recovery — plus
a ``validate-config`` leg the provisioning scripts call before any mutation.

Discipline (plan lines 167-168):

* It accepts secret *file paths* (``--dsn-file``, ``--keyring-file``,
  ``--refresh-token-file``) and NEVER a DSN or token literal on the command line,
  so no credential is exposed through ``ps`` argv, shell history, or logs.
* It has NO enrollment or manual-user-token command: a durable grant is only ever
  established through the human-initiated ``/api/v2/targets/authorizations``
  workflow, never minted here.
* ``revoke`` commits the local revocation first — invalidating the next cache
  check on every replica — and reports ``local_revoked_remote_unconfirmed``
  without any remote call. ``remote-revoke`` is a *separate* command that may then
  spend one fenced, memory-only refresh credential on a single configured provider
  revocation attempt; a remote failure never rolls back the local revocation and
  is never retried automatically. A missing endpoint or token yields an explicit
  ``remote_unconfirmed``.
* Migration/rotation/recovery delegate to the explicit custody primitives; runtime
  never issues DDL, and this CLI never enables a feature flag or a real target.

Invoke as::

    uv run --frozen --project products/tool-gateway \
        python -m tool_gateway.services.custody_cli <command> [options]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import SecretStr

from tool_gateway.services.custody_crypto import CustodyError, Keyring
from tool_gateway.services.delegated_custody import (
    Owner,
    PostgresCustodyStore,
    migrate_custody,
    recover_custody,
)
from tool_gateway.tools.delegated_configuration import ConfigurationError, load_snapshot

# Bounded, non-secret result strings. A remote revocation is only ever reported
# as accepted or unconfirmed; this CLI never claims a provider-side guarantee it
# did not observe, and never echoes a credential, DSN, or provider message.
LOCAL_REVOKE_STATUS = "local_revoked_remote_unconfirmed"
REMOTE_REVOKED = "revoked"
REMOTE_UNCONFIRMED = "remote_unconfirmed"

# ``reencrypt`` batch bound, mirrored from ``PostgresCustodyStore.reencrypt``.
REENCRYPT_MIN = 1
REENCRYPT_MAX = 1000


class CliError(Exception):
    """A bounded operator-facing refusal; never wraps a secret or driver message."""


def _read_secret_file(path: str, *, field: str) -> str:
    """Read a required secret from a file path; refuse an unreadable/empty file."""
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        raise CliError(f"{field}_file_unreadable") from None
    if not value:
        raise CliError(f"{field}_file_empty")
    return value


def _read_optional_secret_file(path: str) -> str | None:
    """Read an optional secret file; a missing/empty file is ``None``, not an error.

    A remote-revoke attempt with no supplied refresh credential is an explicit
    ``remote_unconfirmed`` (plan line 168), not a refusal.
    """
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _default_store_factory(dsn, keyring, config_path, set_id, callback):
    return PostgresCustodyStore(dsn, keyring, config_path, set_id, callback)


async def _default_remote_revoke(config, refresh_secret):
    from tool_gateway.tools.user_delegated_client import UserDelegatedClient

    # The revocation attempt uses only the hardened provider channel; it reads no
    # custody state, so the acquisition client is composed without a store here.
    return await UserDelegatedClient(custody=None).revoke_token(config, refresh_secret)


async def _dispatch(args, *, store_factory, migrate_fn, recover_fn, remote_revoke_fn) -> str:
    command = args.command

    # -- no store, no secrets beyond the (secret-bearing) config file ---------
    if command == "validate-config":
        load_snapshot(args.config_file, args.set_id, args.callback)
        return "configuration valid"

    if command == "remote-revoke":
        config, _linkage = load_snapshot(args.config_file, args.set_id, args.callback)
        if config.remote_revocation != "supported":
            return f"{REMOTE_UNCONFIRMED} (no configured revocation endpoint)"
        token = _read_optional_secret_file(args.refresh_token_file)
        if token is None:
            return f"{REMOTE_UNCONFIRMED} (no refresh credential supplied)"
        # Exactly one attempt; the callee never retries and never touches the
        # already-committed local revocation.
        return await remote_revoke_fn(config, SecretStr(token))

    # -- explicit migration / recovery primitives (operator role, DDL) --------
    if command == "migrate":
        dsn = _read_secret_file(args.dsn_file, field="dsn")
        await migrate_fn(dsn, Keyring(args.keyring_file))
        return "custody schema migrated"

    if command == "recover":
        dsn = _read_secret_file(args.dsn_file, field="dsn")
        await recover_fn(dsn, Keyring(args.keyring_file), expected_epoch=args.expected_epoch)
        return "custody recovered under a new epoch"

    # -- live-store operations (runtime role, DML only) -----------------------
    def _make_store():
        dsn = _read_secret_file(args.dsn_file, field="dsn")
        return store_factory(dsn, Keyring(args.keyring_file), args.config_file, args.set_id, args.callback)

    if command in ("readiness", "status"):
        return "ready" if await _make_store().ready() else "not_ready"

    if command == "revoke":
        owner = Owner(args.owner_namespace, args.owner_sub)
        status = await _make_store().revoke(owner)
        # Local revocation commits first; the durable store already invalidated
        # the next cache check on every replica. No remote call is made here.
        return status or LOCAL_REVOKE_STATUS

    if command == "rotate-key":
        await _make_store().rotate_key(args.expected_key_id)
        return "key policy rotated"

    if command == "reencrypt":
        # Bound the batch before touching the store; an out-of-bound limit is a
        # refusal, never a partial or unbounded re-encryption.
        if not (REENCRYPT_MIN <= args.limit <= REENCRYPT_MAX):
            raise CliError("invalid_batch")
        count = await _make_store().reencrypt(limit=args.limit)
        return f"reencrypted {count} credential(s)"

    raise CliError("unknown_command")


def _build_parser() -> argparse.ArgumentParser:
    # ``allow_abbrev=False`` is set on the main parser AND every subparser:
    # argparse does NOT propagate it to subparsers, and an abbreviated ``--dsn``
    # or ``--refresh-token`` must be rejected outright rather than silently
    # accepted as a prefix of the ``*-file`` secret-path options (plan line 167:
    # it accepts secret file paths, never token literals).
    parser = argparse.ArgumentParser(
        prog="custody_cli",
        description="Administer SPEC-070 delegated custody. Secret file paths only; "
                    "no enrollment or manual-token command.",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add(name, **kwargs):
        return sub.add_parser(name, allow_abbrev=False, **kwargs)

    def _dsn_keyring(p):
        p.add_argument("--dsn-file", required=True,
                       help="path to a file containing the custody DSN (never a literal)")
        p.add_argument("--keyring-file", required=True,
                       help="path to the versioned custody keyring JSON mount")

    def _store_config(p):
        _dsn_keyring(p)
        p.add_argument("--config-file", required=True, help="path to the administered delegated config JSON")
        p.add_argument("--set-id", required=True, help="the administered credential-set id")
        p.add_argument("--callback", required=True, help="the exact trusted HTTPS callback URL")

    p = _add("migrate", help="create/upgrade the custody schema (operator role)")
    _dsn_keyring(p)

    # ``status`` is an operator-friendly alias for ``readiness``.
    for name in ("readiness", "status"):
        _store_config(_add(name, help="report schema + configuration readiness"))

    p = _add("revoke", help="commit a LOCAL revocation first; never a remote call")
    _store_config(p)
    p.add_argument("--owner-namespace", required=True, help="verified requester namespace to revoke")
    p.add_argument("--owner-sub", required=True, help="verified requester subject to revoke")

    p = _add("remote-revoke",
             help="ONE configured provider revocation attempt; never retried, never rolls back local")
    p.add_argument("--config-file", required=True, help="path to the administered delegated config JSON")
    p.add_argument("--set-id", required=True, help="the administered credential-set id")
    p.add_argument("--callback", required=True, help="the exact trusted HTTPS callback URL")
    p.add_argument("--refresh-token-file", required=True,
                   help="path to a fenced, memory-only refresh credential (never a literal)")

    p = _add("rotate-key", help="rotate the active custody key policy")
    _store_config(p)
    p.add_argument("--expected-key-id", required=True, help="the currently active key id being rotated from")

    p = _add("reencrypt", help="bounded re-encryption under the active key")
    _store_config(p)
    p.add_argument("--limit", type=int, default=100,
                   help=f"batch bound, {REENCRYPT_MIN}..{REENCRYPT_MAX}")

    p = _add("recover", help="externally fenced recovery under a new epoch")
    _dsn_keyring(p)
    p.add_argument("--expected-epoch", required=True, help="the prior recovery epoch being fenced")

    p = _add("validate-config", help="validate the administered config + mapping before mutation")
    p.add_argument("--config-file", required=True, help="path to the administered delegated config JSON")
    p.add_argument("--set-id", required=True, help="the administered credential-set id")
    p.add_argument("--callback", required=True, help="the exact trusted HTTPS callback URL")

    return parser


def main(argv=None, *, store_factory=None, migrate_fn=None, recover_fn=None, remote_revoke_fn=None) -> int:
    """Run one administration command. Returns a process exit code (0 on success).

    Dependencies are injectable so the command surface is provable without a live
    Postgres or provider; the defaults wire the real custody primitives.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_dispatch(
            args,
            store_factory=store_factory or _default_store_factory,
            migrate_fn=migrate_fn or migrate_custody,
            recover_fn=recover_fn or recover_custody,
            remote_revoke_fn=remote_revoke_fn or _default_remote_revoke,
        ))
    except (CliError, CustodyError, ConfigurationError) as exc:
        # A bounded refusal class only; never a DSN, token, or driver message.
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
