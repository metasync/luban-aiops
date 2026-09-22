"""One-time secret-delivery buffer and the delivery-channel interface.

SPEC-062 R-3/R-5. A generated password must reach a human without ever riding a
stream frame, a render tree, a log line or the durable transcript. Two seams
make that structural:

- ``SecretDeliveryBuffer`` — a single-use, owner-scoped, TTL-bounded stash. The
  generated value is held here (never in a result projection) and released only
  by one authenticated redemption. It is a ``@runtime_checkable`` ``Protocol``
  mirroring ``agent_service.services.session_store.SessionStore``: an in-memory
  backend (default; dev/CI, ``replicas: 1``, modeled on ``browser_sessions``'s
  monotonic-clock TTL + eviction) and an additive Redis backend (``replicas > 1``)
  using ``SET … EX`` for the TTL and atomic ``GETDEL`` for single-use redemption.
  Backend selection fails open to in-memory with a recorded fallback, exactly
  like ``build_session_store``.

- ``DeliveryChannel`` — the transport seam every external sender implements, so
  adding Teams/Slack later is a new class plus a registry entry and touches
  neither generation, nor the buffer, nor the audit event, nor the masking.

Neither seam ever logs a delivered value.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

DEFAULT_DELIVERY_TTL_SECONDS = 300
DEFAULT_DELIVERY_MAX_ENTRIES = 256
DEFAULT_REDIS_HOST = "127.0.0.1"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_DB = 2
REDIS_PING_TIMEOUT_SECONDS = 3.0

_REDIS_KEY_PREFIX = "secret_delivery:"


# ---------------------------------------------------------------------------
# Buffer protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SecretDeliveryBuffer(Protocol):
    """Single-use, owner-scoped, TTL-bounded secret stash (SPEC-062 R-3)."""

    @property
    def backend_name(self) -> str: ...

    def stash(
        self,
        value: str,
        owner_sub: str,
        session_id: str | None,
        ttl_seconds: int,
    ) -> str:
        """Store ``value`` and return an opaque, unguessable ``delivery_id``."""
        ...

    def redeem(self, delivery_id: str, owner_sub: str) -> str | None:
        """Return the value once for the owner, then destroy it.

        A second redemption, an expired handle, or a wrong owner all yield
        ``None`` — and in every case the value is already gone, so a probe can
        never be replayed.
        """
        ...

    def discard(self, delivery_id: str, owner_sub: str) -> bool:
        """Destroy a stashed value WITHOUT revealing it (SPEC-062 R-3 deny path).

        The burn counterpart to ``redeem``: when a gated reset is denied, its
        mutation fails, or its park expires, the held handle is destroyed at once
        rather than left redeemable until the TTL lapses. Owner-scoped — a wrong
        owner discards nothing — and idempotent: an unknown, expired, or
        already-spent handle returns ``False``. Returns ``True`` only when a live,
        owner-matched entry was destroyed. Never returns or logs the value.
        """
        ...

    def is_ready(self) -> bool: ...

    def __len__(self) -> int: ...


@dataclass
class _Entry:
    value: str
    owner_sub: str
    session_id: str | None
    expires_at: float  # monotonic clock


class InMemorySecretDeliveryBuffer:
    """Process-local buffer with monotonic-clock TTL and max-entry eviction.

    Single-replica and non-persistent; suitable for dev/CI and as the fallback
    when Redis is unreachable. ``clock`` is injectable so TTL/eviction behavior
    is deterministic under test without sleeping.
    """

    backend_name = "memory"

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_DELIVERY_TTL_SECONDS,
        max_entries: int = DEFAULT_DELIVERY_MAX_ENTRIES,
        clock: Any = time.monotonic,
    ) -> None:
        self._ttl_seconds = int(ttl_seconds)
        self._max_entries = max(1, int(max_entries))
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    def _purge_expired(self, now: float) -> None:
        expired = [
            delivery_id
            for delivery_id, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for delivery_id in expired:
            self._entries.pop(delivery_id, None)

    def _evict_oldest(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest_id = min(
                self._entries, key=lambda k: self._entries[k].expires_at
            )
            self._entries.pop(oldest_id, None)

    def stash(
        self,
        value: str,
        owner_sub: str,
        session_id: str | None,
        ttl_seconds: int | None = None,
    ) -> str:
        now = self._clock()
        self._purge_expired(now)
        ttl = self._ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        delivery_id = str(uuid4())
        self._entries[delivery_id] = _Entry(
            value=value,
            owner_sub=owner_sub,
            session_id=session_id,
            expires_at=now + ttl,
        )
        self._evict_oldest()
        return delivery_id

    def redeem(self, delivery_id: str, owner_sub: str) -> str | None:
        now = self._clock()
        self._purge_expired(now)
        # Pop unconditionally: single-use, and a wrong-owner probe still burns
        # the handle so it can never be replayed (fail-safe, matching Redis's
        # atomic GETDEL). The delivery_id is an unguessable uuid4, so this is
        # defense-in-depth over owner-scope, not the primary control.
        entry = self._entries.pop(delivery_id, None)
        if entry is None or entry.expires_at <= now:
            return None
        if entry.owner_sub != owner_sub:
            return None
        return entry.value

    def discard(self, delivery_id: str, owner_sub: str) -> bool:
        now = self._clock()
        self._purge_expired(now)
        entry = self._entries.get(delivery_id)
        if entry is None or entry.expires_at <= now:
            return False
        # Owner-scoped: never destroy a handle that is not the caller's. The
        # unguessable uuid4 + gateway auth already make a cross-owner probe
        # moot, but keeping the guarantee structural mirrors ``redeem`` and
        # means a mis-routed discard can never burn another owner's secret.
        if not owner_sub or entry.owner_sub != owner_sub:
            return False
        self._entries.pop(delivery_id, None)
        return True

    def is_ready(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self._entries)


class RedisSecretDeliveryBuffer:
    """Redis-backed buffer for ``replicas > 1`` (SPEC-062 R-3, D-2).

    ``SET … EX`` carries the TTL; ``GETDEL`` makes redemption atomic and
    single-use across replicas. A wrong owner is treated as not-found and the
    value is already gone. An additive tool-gateway dependency: ``redis`` is
    imported lazily by the factory so the in-memory default needs no extra
    package.
    """

    backend_name = "redis"

    def __init__(
        self,
        client: Any,
        ttl_seconds: int = DEFAULT_DELIVERY_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._ttl_seconds = int(ttl_seconds)

    def _key(self, delivery_id: str) -> str:
        return f"{_REDIS_KEY_PREFIX}{delivery_id}"

    def stash(
        self,
        value: str,
        owner_sub: str,
        session_id: str | None,
        ttl_seconds: int | None = None,
    ) -> str:
        ttl = self._ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        delivery_id = str(uuid4())
        payload = json.dumps(
            {"value": value, "owner_sub": owner_sub, "session_id": session_id}
        )
        self._client.set(self._key(delivery_id), payload, ex=ttl)
        return delivery_id

    def redeem(self, delivery_id: str, owner_sub: str) -> str | None:
        raw = self._client.getdel(self._key(delivery_id))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or not owner_sub or data.get("owner_sub") != owner_sub:
            return None
        value = data.get("value")
        return value if isinstance(value, str) else None

    def discard(self, delivery_id: str, owner_sub: str) -> bool:
        key = self._key(delivery_id)
        # Peek to verify ownership before destroying: a wrong owner discards
        # nothing. GET+DELETE is not atomic, but the handle is an unguessable
        # uuid4 and the route is authenticated, so the only race is against a
        # concurrent owner redemption — and either way the entry ends up gone,
        # preserving single-use. The value is parsed past, never logged.
        raw = self._client.get(key)
        if raw is None:
            return False
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return False
        if not isinstance(data, dict) or not owner_sub or data.get("owner_sub") != owner_sub:
            return False
        self._client.delete(key)
        return True

    def is_ready(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001 - readiness never raises
            return False

    def __len__(self) -> int:
        try:
            return len(self._client.keys(f"{_REDIS_KEY_PREFIX}*"))
        except Exception:  # noqa: BLE001
            return 0


def build_secret_delivery_buffer(
    backend: str = "memory",
    ttl_seconds: int = DEFAULT_DELIVERY_TTL_SECONDS,
    max_entries: int = DEFAULT_DELIVERY_MAX_ENTRIES,
    redis_host: str = DEFAULT_REDIS_HOST,
    redis_port: int = DEFAULT_REDIS_PORT,
    redis_db: int = DEFAULT_REDIS_DB,
) -> SecretDeliveryBuffer:
    """Create the delivery buffer from ``GATEWAY_SECRET_DELIVERY_BACKEND``.

    ``memory`` (default) and ``redis`` are supported; an unknown value fails
    startup. Redis connection failure fails **open** to in-memory with a
    recorded fallback so the tool surface stays usable, mirroring
    ``build_session_store``.
    """
    if backend == "memory":
        LOGGER.info("secret delivery buffer: in-memory backend")
        return InMemorySecretDeliveryBuffer(
            ttl_seconds=ttl_seconds, max_entries=max_entries
        )
    if backend != "redis":
        raise ValueError(
            f"Unknown GATEWAY_SECRET_DELIVERY_BACKEND: {backend!r} "
            "(expected 'memory' or 'redis')"
        )
    try:
        import redis

        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_timeout=REDIS_PING_TIMEOUT_SECONDS,
            socket_connect_timeout=REDIS_PING_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        client.ping()
        LOGGER.info(
            "secret delivery buffer: Redis backend connected",
            extra={"host": redis_host, "port": redis_port, "db": redis_db},
        )
        return RedisSecretDeliveryBuffer(client=client, ttl_seconds=ttl_seconds)
    except Exception as exc:  # noqa: BLE001 - fail open to in-memory
        LOGGER.warning(
            "secret delivery buffer: Redis unreachable (%s), falling back to "
            "in-memory",
            exc.__class__.__name__,
        )
        return InMemorySecretDeliveryBuffer(
            ttl_seconds=ttl_seconds, max_entries=max_entries
        )


# ---------------------------------------------------------------------------
# Delivery-channel interface (R-5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryOutcome:
    """Result of one channel send.

    Carries ``channel`` regardless of transport so ``secret_delivered`` is
    attributable, and — for the local portal-copy handoff — the opaque
    ``delivery_id`` / ``expires_at`` the kernel turns into a ``secret_delivery``
    frame. It never carries the value.
    """

    channel: str
    delivered: bool
    recipient: str | None = None
    delivery_id: str | None = None
    expires_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class DeliveryChannel(Protocol):
    """A transport that can carry a generated secret to a human (R-5)."""

    @property
    def name(self) -> str: ...

    async def send(
        self,
        value: str,
        recipient: str | None,
        context: dict,
    ) -> DeliveryOutcome:
        """Deliver ``value``; never log it. ``context`` carries identity/session."""
        ...
