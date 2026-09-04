"""Stateful browser session pool for the browser connector (SPEC-049 R-1).

One warm browser process per tool-gateway pod — a chromium-headless-shell
sidecar container reached over CDP (``connect_over_cdp`` against
``GATEWAY_BROWSER_CDP_ENDPOINT``, spec D-6) — and sessions as browser
contexts keyed by the caller's chat session id (SPEC-049 R-1). The chat
session id is a correlation handle the gateway receives on both call paths
— the agent-platform kernel forwards it on the inline read path and the
execution worker forwards it from the signed envelope on the write path —
so one browser context spans a whole web-check flow even across the
owner→approver identity switch the SPEC-020/037 confirmation path
introduces (the resumed write-tier interaction carries the approver's
subject but the same chat session). It is never a model-supplied
parameter and carries no authority: identity and policy still ride the
delegated bearer token. When a caller forwards no chat session id the
connector falls back to the verified subject (see ``browser_connector``).

Sessions idle-expire after ``GATEWAY_BROWSER_SESSION_TTL`` and the pool is
capped at ``GATEWAY_BROWSER_MAX_SESSIONS`` with oldest-idle eviction; both
paths close the browser context so the sidecar's memory budget stays
bounded. The pool never launches a browser binary itself — with the flag
off it is never constructed, and with the sidecar absent every operation
fails closed with a structured error instead of an exception.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

LOGGER = logging.getLogger(__name__)


def _normalize_cdp_endpoint(endpoint: str) -> str:
    """Rewrite a bare ``ws://host:port`` CDP endpoint to its ``http://`` form.

    Playwright's ``connect_over_cdp`` treats an ``http(s)://`` endpoint as
    the DevTools discovery base (fetching ``/json/version`` for the real
    browser websocket) but dials a ``ws://`` URL verbatim — so a bare
    ``ws://host:port`` (the committed knob default, matching the sidecar's
    listening port) 404s on ``/``. A ``ws://`` URL carrying an explicit
    path (e.g. ``/devtools/browser/<id>``) is a complete browser websocket
    and passes through untouched.
    """
    if not endpoint.startswith(("ws://", "wss://")):
        return endpoint
    parsed = urlsplit(endpoint)
    if parsed.path not in ("", "/"):
        return endpoint
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunsplit((scheme, parsed.netloc, "/", "", ""))


@dataclass
class FlowState:
    """Skill-declared web-check flow bound to a session (SPEC-049 R-4).

    ``approved`` is set at bind time for ``read``-class flows (they run
    under ``tools:invoke`` with no extra gate) and recorded when the first
    interaction of a ``write``-class flow executes — an interaction can
    only reach the gateway through the SPEC-020/037 confirmation and
    signing path, so its execution is evidence of approval, not a gate the
    deviation guard re-checks (the guard consults bound/denied/origin/
    risk_class/steps). ``denied`` is a reserved gateway-side kill-switch
    the guard honors, but the HITL path enforces denial upstream — the
    SPEC-020 bridge refuses the write so it never reaches the gateway to
    flip this flag — so it is not currently set in production.
    """

    skill_id: str
    origin: str
    risk_class: str  # "read" | "write"
    max_steps: int
    # Human-readable skill metadata for the flow-semantic confirmation card
    # (SPEC-051 R-6): populated at bind_flow from the fetched skill's
    # frontmatter (title/description) and surfaced on to_dict() so it rides
    # web.navigate's data["flow"] to the kernel, which renders it as the card
    # headline above the per-call tool detail. Empty when the skill declares
    # none — the kernel card then falls back to tool-level rendering.
    title: str = ""
    description: str = ""
    steps_used: int = 0
    approved: bool = False
    denied: bool = False

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "origin": self.origin,
            "risk_class": self.risk_class,
            "title": self.title,
            "description": self.description,
            "steps_used": self.steps_used,
            "max_steps": self.max_steps,
            "approved": self.approved,
        }


@dataclass
class BrowserSessionEntry:
    """One caller's browser context, page, and flow bookkeeping."""

    context: Any
    page: Any
    last_used: float
    flow: FlowState | None = None
    # Interactive-element handles from the most recent web.snapshot; refs
    # are 1-based indices into this list and invalidate on the next
    # snapshot or navigation.
    refs: list = field(default_factory=list)
    # Credential values filled during this session (SPEC-049 R-5): held
    # only to mask them out of snapshots — never serialized into results.
    filled_values: set = field(default_factory=set)
    # Password-tier values only (SPEC-049 R-5): additionally masked out of
    # screenshots, since a legacy target may render a password into a
    # ``type=text`` field a raw capture would leak. A filled username is
    # deliberately NOT here — seeing who the flow signed in as is the point
    # of the visual evidence.
    secret_values: set = field(default_factory=set)
    # Frame stack for web.switch_frame (SPEC-050 R-9): when non-empty the
    # top entry is the active frame target for subsequent operations.
    # web.navigate resets this to the main frame (empty stack).
    frame_stack: list = field(default_factory=list)

    def reset_page_state(self) -> None:
        """Drop refs bound to a page that navigated or re-snapshotted."""
        self.refs = []
        self.frame_stack = []

    @property
    def active_target(self) -> Any:
        """The current page or frame target for operations."""
        if self.frame_stack:
            return self.frame_stack[-1]
        return self.page


class BrowserSessionPool:
    """Session contexts over one shared CDP browser connection.

    ``playwright_factory`` and ``clock`` are injection points: unit tests
    substitute a fake Playwright layer and a controllable monotonic clock
    so TTL/eviction behavior is deterministic without a real browser.
    """

    def __init__(
        self,
        cdp_endpoint: str,
        ttl_seconds: int,
        max_sessions: int,
        playwright_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cdp_endpoint = cdp_endpoint
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max(1, max_sessions)
        self._clock = clock
        self._playwright_factory = playwright_factory
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._sessions: dict[str, BrowserSessionEntry] = {}
        # Serializes first-use context creation (see get_or_create) so two
        # concurrent callers for the same key can't each build a context.
        self._create_lock = asyncio.Lock()

    # --- Connection lifecycle ---

    async def start(self) -> bool:
        """Connect eagerly to the sidecar over CDP (idempotent).

        Called at pod startup when the connector flag is on, so the
        first-navigate latency is paid here rather than at first use.
        A missing sidecar logs and returns False; the tool surface stays
        registered and fails closed with BROWSER_NOT_READY until the
        connection comes up (a lazy retry runs on each session request).
        The bootstrap runs under the create lock so it can't race a
        concurrent lazy retry into spawning two Playwright hosts (W-1).
        """
        async with self._create_lock:
            return await self._connect()

    async def _connect(self) -> bool:
        """Idempotent CDP bootstrap; the caller holds ``_create_lock``."""
        if self._browser is not None:
            return True
        try:
            factory = self._playwright_factory or self._default_factory()
            self._playwright = await factory().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                _normalize_cdp_endpoint(self._cdp_endpoint)
            )
        except Exception as exc:
            LOGGER.warning(
                "browser sidecar not reachable at %s: %s",
                self._cdp_endpoint,
                exc,
            )
            await self._teardown_playwright()
            return False
        LOGGER.info("browser connector connected to %s", self._cdp_endpoint)
        return True

    async def stop(self) -> None:
        """Close every session, the CDP connection, and the Playwright host."""
        for entry in list(self._sessions.values()):
            await _close_quietly(entry.context)
        self._sessions.clear()
        await _close_quietly(self._browser)
        self._browser = None
        await self._teardown_playwright()

    async def _teardown_playwright(self) -> None:
        playwright, self._playwright = self._playwright, None
        if playwright is None:
            return
        try:
            await playwright.stop()
        except Exception:  # noqa: BLE001 - teardown must never raise
            pass

    @staticmethod
    def _default_factory() -> Callable[[], Any]:
        from playwright.async_api import async_playwright

        return async_playwright

    @property
    def connected(self) -> bool:
        return self._browser is not None

    # --- Session lifecycle ---

    async def get_or_create(self, session_key: str) -> BrowserSessionEntry:
        """Return the caller's session, creating it on first use.

        Runs the idle sweep before every lookup and evicts oldest-idle
        sessions when the cap is exceeded, so both TTL and cap hold even
        without a background timer.
        """
        # Fast path (unlocked): already connected and the session exists.
        if self.connected:
            self.sweep_expired()
            entry = self._sessions.get(session_key)
            if entry is not None:
                entry.last_used = self._clock()
                return entry
        # Slow path: hold the create lock across BOTH the CDP bootstrap and
        # the context creation. Two concurrent cold callers must not each
        # spawn a Playwright host (W-1) nor each build a context for one key
        # (the second insert would orphan the first until pod shutdown). The
        # double-checks inside the lock return work another coroutine did
        # while we waited.
        async with self._create_lock:
            if not self.connected:
                if not await self._connect():
                    raise BrowserNotReady(self._cdp_endpoint)
            self.sweep_expired()
            entry = self._sessions.get(session_key)
            if entry is not None:
                entry.last_used = self._clock()
                return entry
            while len(self._sessions) >= self._max_sessions:
                await self._evict_oldest()
            assert self._browser is not None  # guarded by the connect above
            context = await self._browser.new_context()
            page = await context.new_page()
            entry = BrowserSessionEntry(
                context=context, page=page, last_used=self._clock()
            )
            self._sessions[session_key] = entry
            return entry

    def sweep_expired(self) -> list[str]:
        """Close contexts idle beyond the TTL; returns the evicted keys."""
        now = self._clock()
        expired = [
            key
            for key, entry in self._sessions.items()
            if (now - entry.last_used) > self._ttl_seconds
        ]
        for key in expired:
            entry = self._sessions.pop(key)
            _schedule_close(entry.context)
        if expired:
            LOGGER.info("browser sessions expired: %s", ", ".join(sorted(expired)))
        return expired

    async def _evict_oldest(self) -> None:
        key, entry = min(
            self._sessions.items(), key=lambda item: item[1].last_used
        )
        self._sessions.pop(key)
        await _close_quietly(entry.context)
        LOGGER.info("browser session evicted (cap reached): %s", key)

    async def drop(self, session_key: str) -> None:
        entry = self._sessions.pop(session_key, None)
        if entry is not None:
            await _close_quietly(entry.context)

    def get(self, session_key: str) -> BrowserSessionEntry | None:
        return self._sessions.get(session_key)

    @property
    def session_count(self) -> int:
        return len(self._sessions)


class BrowserNotReady(Exception):
    """The browser sidecar is not reachable (structured error upstream)."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(
            f"browser sidecar is not reachable at {endpoint}; web.* tools "
            "are unavailable until the sidecar is running"
        )
        self.endpoint = endpoint


# Strong refs to in-flight best-effort close tasks: asyncio keeps only a
# weak reference to a task, so an unreferenced close task can be garbage
# collected mid-flight and silently skip the context close (S-5).
_PENDING_CLOSES: set = set()


def _schedule_close(context: Any) -> None:
    """Best-effort async close from a sync path (the TTL sweep)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_close_quietly(context))
    _PENDING_CLOSES.add(task)
    task.add_done_callback(_PENDING_CLOSES.discard)


async def _close_quietly(target: Any) -> None:
    """Close a Playwright object without ever raising on teardown."""
    if target is None:
        return
    try:
        await target.close()
    except Exception:  # noqa: BLE001 - teardown must never raise
        pass
