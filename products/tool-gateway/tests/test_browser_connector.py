"""Browser connector tests with a fake Playwright layer (SPEC-049).

Covers the session pool lifecycle (create/reuse/TTL/eviction), the origin
allowlist matrix, flow binding and the deviation-guard state machine,
credential-set handling with a leak assertion, and the screenshot byte
cap — all without a real browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import patch

from tool_gateway.core.config import GatewaySettings
from tool_gateway.tools.browser_connector import (
    BrowserConnector,
    _redact_secret_query,
    origin_of,
)
from tool_gateway.tools.browser_sessions import BrowserSessionPool, FlowState
from tool_gateway.tools.registry import ToolRegistry

ALLOWED_ORIGIN = "https://inventory.internal:8443"
IDENTITY = {"sub": "dev.operator", "username": "dev.operator", "roles": ["operator"]}
PASSWORD_LITERAL = "s3cret-PASSWORD-xyz"


def _run(coro):
    return asyncio.run(coro)


# --- Fake Playwright layer -------------------------------------------------


class FakeElementHandle:
    def __init__(self, info: dict, page: "FakePage") -> None:
        self.info = info
        self.page = page
        self.clicks = 0
        self.fills: list[str] = []
        self.selects: list[str] = []
        self.hovers = 0
        self.focuses = 0
        self.uploaded_files: list[str] = []
        self._frame: FakeFrame | None = None

    async def evaluate(self, _js: str):
        return self.info

    async def click(self) -> None:
        self.clicks += 1

    async def fill(self, value: str) -> None:
        self.fills.append(value)
        # Like a real input, the value becomes readable on the next
        # snapshot — the leak assertion depends on gateway-side masking.
        self.info["value"] = value

    async def select_option(self, value: str) -> None:
        if self.info.get("tag", "").lower() != "select":
            raise RuntimeError("Element is not a select element")
        options = self.info.get("options", [])
        if value not in options:
            raise RuntimeError(f"Option '{value}' not found in select")
        self.selects.append(value)
        self.info["value"] = value

    async def hover(self) -> None:
        self.hovers += 1

    async def focus(self) -> None:
        self.focuses += 1

    async def set_input_files(self, path: str) -> None:
        if self.info.get("type", "").lower() != "file":
            raise RuntimeError("Element is not a file input")
        self.uploaded_files.append(path)

    async def content_frame(self) -> "FakeFrame | None":
        return self._frame


class FakeKeyboard:
    """Stand-in for Playwright's page.keyboard."""

    def __init__(self) -> None:
        self.presses: list[str] = []

    async def press(self, key: str) -> None:
        self.presses.append(key)


class FakeMouse:
    """Stand-in for Playwright's page.mouse."""

    def __init__(self) -> None:
        self.wheels: list[tuple[int, int]] = []
        self.moves: list[tuple[float, float]] = []

    async def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    async def wheel(self, delta_x: int, delta_y: int) -> None:
        self.wheels.append((delta_x, delta_y))


class FakeFrameElement:
    """Stand-in for the ``<iframe>`` ElementHandle from Frame.frame_element().

    Only ``bounding_box()`` is needed: web.scroll centers the cursor over
    the frame before dispatching a Page-level wheel.
    """

    def __init__(self, box: dict | None) -> None:
        self._box = box

    async def bounding_box(self) -> dict | None:
        return self._box


class FakeFrame:
    """Stand-in for a Playwright Frame (iframe content).

    Real Playwright Frame objects do NOT expose .keyboard or .mouse —
    those live on Page only. The production code dispatches keyboard and
    mouse through entry.page, so the fake must not provide them here.
    """

    def __init__(self, url: str = "about:blank", box: dict | None = None) -> None:
        self.url = url
        self._title = "Frame"
        self.elements: list[FakeElementHandle] = []
        # Bounding box of the <iframe> element within the parent page; used
        # by web.scroll to center the cursor over the frame before wheeling.
        self._box = box if box is not None else {
            "x": 100.0, "y": 80.0, "width": 400.0, "height": 300.0,
        }

    async def frame_element(self) -> FakeFrameElement:
        return FakeFrameElement(self._box)

    async def title(self) -> str:
        return self._title

    async def query_selector_all(self, _selector: str) -> list[FakeElementHandle]:
        return list(self.elements)

    async def query_selector(self, selector: str) -> FakeElementHandle | None:
        for el in self.elements:
            if el.info.get("tag", "").lower() == selector.lower():
                return el
        return None

    async def evaluate(self, _js: str, arg=None):
        return None

    async def wait_for_selector(self, selector: str, **kwargs) -> FakeElementHandle | None:
        for el in self.elements:
            if el.info.get("tag", "").lower() == selector.lower():
                return el
        return None


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self._title = "Fake App"
        self.elements: list[FakeElementHandle] = []
        self.goto_calls: list[str] = []
        self.redirect_to: str | None = None
        self.viewport_size = {"width": 1280, "height": 720}
        # (quality, clip) -> byte length; default rule fits the 64 KiB cap.
        self.screenshot_rule = lambda quality, clip: b"x" * (quality * 100)
        # Values each element held at the last screenshot() call, so
        # masking tests can assert a credential never survives into it.
        self.last_capture_values: list = []
        # SPEC-050: keyboard, mouse, and wait support.
        self.keyboard = FakeKeyboard()
        self.mouse = FakeMouse()
        # wait_for_selector behaviour: by default the first matching element
        # is returned immediately; set wait_fail = True to simulate timeout.
        self.wait_fail = False

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append(url)
        if self.redirect_to is not None:
            self.url, self.redirect_to = self.redirect_to, None
        else:
            self.url = url

    async def title(self) -> str:
        return self._title

    async def query_selector_all(self, _selector: str) -> list[FakeElementHandle]:
        return list(self.elements)

    async def query_selector(self, selector: str) -> FakeElementHandle | None:
        """Return the first element whose tag matches the selector."""
        for el in self.elements:
            if el.info.get("tag", "").lower() == selector.lower():
                return el
        return None

    async def wait_for_selector(
        self, selector: str, **kwargs
    ) -> FakeElementHandle | None:
        if self.wait_fail:
            raise RuntimeError("Timeout exceeded")
        return await self.query_selector(selector)

    async def screenshot(self, type: str | None = None, quality: int | None = None,
                         clip: dict | None = None) -> bytes:
        self.last_capture_values = [el.info.get("value") for el in self.elements]
        return self.screenshot_rule(quality or 70, clip)

    async def evaluate(self, _js: str, arg=None):
        # Stand-in for the screenshot credential mask/unmask JS: a mask pass
        # (called with the secret-value list) rewrites matching element
        # values to dots and stashes the originals; the unmask pass (no arg)
        # restores them. Mirrors _SCREENSHOT_MASK_JS/_SCREENSHOT_UNMASK_JS.
        if arg is not None:
            count = 0
            for el in self.elements:
                value = el.info.get("value")
                if isinstance(value, str) and value in arg:
                    el.info["__cv_orig"] = value
                    el.info["value"] = "\u2022" * 8
                    count += 1
            return count
        for el in self.elements:
            if "__cv_orig" in el.info:
                el.info["value"] = el.info.pop("__cv_orig")
        return None

    def add_element(self, **info) -> FakeElementHandle:
        handle = FakeElementHandle(info, self)
        self.elements.append(handle)
        return handle


class FakeContext:
    def __init__(self, browser: "FakeBrowser") -> None:
        self._browser = browser
        self.closed = False
        self.page = FakePage()

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[FakeContext] = []
        self.closed = False

    async def new_context(self) -> FakeContext:
        context = FakeContext(self)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: FakeBrowser, fail: bool) -> None:
        self._browser = browser
        self._fail = fail
        self.dialed: list[str] = []

    async def connect_over_cdp(self, endpoint: str) -> FakeBrowser:
        self.dialed.append(endpoint)
        if self._fail:
            raise RuntimeError("sidecar unreachable")
        return self._browser


class _FakePlaywrightHost:
    def __init__(self, browser: FakeBrowser, fail: bool) -> None:
        self.chromium = _FakeChromium(browser, fail)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def _playwright_factory(browser: FakeBrowser, fail: bool = False):
    host = _FakePlaywrightHost(browser, fail)

    class _Starter:
        async def start(self):
            return host

    return lambda: _Starter(), host


def _make_connector(
    allow_origins: tuple[str, ...] = (ALLOWED_ORIGIN,),
    session_ttl_seconds: int = 600,
    max_sessions: int = 4,
    flow_max_steps: int = 20,
    credential_sets_path: str = "",
    screenshot_max_bytes: int = 65536,
    browser: FakeBrowser | None = None,
    fail_connect: bool = False,
) -> tuple[BrowserConnector, FakeBrowser]:
    browser = browser or FakeBrowser()
    factory, _host = _playwright_factory(browser, fail_connect)
    connector = BrowserConnector(
        cdp_endpoint="ws://localhost:9222",
        allow_origins=allow_origins,
        session_ttl_seconds=session_ttl_seconds,
        max_sessions=max_sessions,
        flow_max_steps=flow_max_steps,
        credential_sets_path=credential_sets_path,
        screenshot_max_bytes=screenshot_max_bytes,
        skills_service_url="http://skills-hub:8000",
        playwright_factory=factory,
    )
    return connector, browser


def _registry(connector: BrowserConnector, allow_mutating: bool = True) -> ToolRegistry:
    registry = ToolRegistry(allow_mutating=allow_mutating)
    connector.register_tools(registry)
    return registry


def _stub_skill(connector: BrowserConnector, record: dict | None) -> None:
    async def _fetch(skill_id: str):
        if record is None:
            return None, "SKILL_NOT_FOUND", f"Skill '{skill_id}' was not found."
        return record, "", ""

    connector.fetch_skill = _fetch  # type: ignore[method-assign]


def _web_skill(risk_class: str | None = "write") -> dict:
    return {
        "skill_id": "team-a/web/inventoryhealth",
        "web_target": f"{ALLOWED_ORIGIN}/login",
        "risk_class": risk_class,
    }


# --- Settings ---------------------------------------------------------------


class BrowserSettingsTests(unittest.TestCase):
    def test_knobs_parse_from_env(self) -> None:
        env = {
            "GATEWAY_BROWSER_ENABLED": "true",
            "GATEWAY_BROWSER_CDP_ENDPOINT": "ws://browser:9223",
            "GATEWAY_BROWSER_SESSION_TTL": "120",
            "GATEWAY_BROWSER_MAX_SESSIONS": "2",
            "GATEWAY_BROWSER_ALLOW_ORIGINS": "https://a.internal, https://b.internal:8443",
            "GATEWAY_BROWSER_FLOW_MAX_STEPS": "7",
            "GATEWAY_BROWSER_CREDENTIAL_SETS": "/etc/luban/browser-creds.json",
            "GATEWAY_BROWSER_SCREENSHOT_MAX_BYTES": "1024",
        }
        with patch.dict(os.environ, env):
            settings = GatewaySettings.from_env()
        self.assertTrue(settings.browser_enabled)
        self.assertEqual(settings.browser_cdp_endpoint, "ws://browser:9223")
        self.assertEqual(settings.browser_session_ttl_seconds, 120)
        self.assertEqual(settings.browser_max_sessions, 2)
        self.assertEqual(
            settings.browser_allow_origins,
            ("https://a.internal", "https://b.internal:8443"),
        )
        self.assertEqual(settings.browser_flow_max_steps, 7)
        self.assertEqual(
            settings.browser_credential_sets_path, "/etc/luban/browser-creds.json"
        )
        self.assertEqual(settings.browser_screenshot_max_bytes, 1024)

    def test_defaults_are_off_and_deny_all(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = GatewaySettings.from_env()
        self.assertFalse(settings.browser_enabled)
        self.assertEqual(settings.browser_allow_origins, ())
        self.assertEqual(settings.browser_credential_sets_path, "")
        self.assertEqual(settings.browser_screenshot_max_bytes, 65536)

    def test_disabled_posture_registers_nothing(self) -> None:
        from tool_gateway.app import _build_tool_registry
        from tool_gateway.core.config import get_settings

        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GATEWAY_")
        }
        with patch.dict(os.environ, env, clear=True):
            get_settings.cache_clear()
            try:
                registry, browser_connector = _build_tool_registry()
            finally:
                get_settings.cache_clear()
        self.assertIsNone(browser_connector)
        names = {d.name for d in registry.list_definitions()}
        self.assertFalse(any(name.startswith("web.") for name in names))


# --- Session pool -----------------------------------------------------------


class SessionPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = [0.0]
        self.clock = lambda: self.now[0]
        self.browser = FakeBrowser()
        factory, host = _playwright_factory(self.browser)
        self.host = host
        self.pool = BrowserSessionPool(
            cdp_endpoint="ws://localhost:9222",
            ttl_seconds=600,
            max_sessions=2,
            playwright_factory=factory,
            clock=self.clock,
        )

    def test_session_reused_within_ttl(self) -> None:
        first = _run(self.pool.get_or_create("user-a"))
        second = _run(self.pool.get_or_create("user-a"))
        self.assertIs(first.page, second.page)
        self.assertEqual(self.pool.session_count, 1)
        self.assertEqual(len(self.browser.contexts), 1)

    def test_session_expires_after_ttl(self) -> None:
        entry = _run(self.pool.get_or_create("user-a"))
        self.now[0] = 601.0
        _run(self.pool.get_or_create("user-b"))
        context = self.browser.contexts[0]
        self.assertTrue(context.closed)
        self.assertNotIn("user-a", self.pool._sessions)
        self.assertIsNot(entry, self.pool.get("user-b"))

    def test_cap_evicts_oldest_idle(self) -> None:
        first = _run(self.pool.get_or_create("user-a"))
        self.now[0] = 10.0
        _run(self.pool.get_or_create("user-b"))
        self.now[0] = 20.0
        _run(self.pool.get_or_create("user-c"))
        self.assertTrue(self.browser.contexts[0].closed)  # oldest-idle
        self.assertEqual(self.pool.session_count, 2)
        self.assertIsNotNone(first)

    def test_drop_closes_context(self) -> None:
        _run(self.pool.get_or_create("user-a"))
        _run(self.pool.drop("user-a"))
        self.assertTrue(self.browser.contexts[0].closed)
        self.assertEqual(self.pool.session_count, 0)

    def test_start_failure_reports_not_ready(self) -> None:
        browser = FakeBrowser()
        factory, _ = _playwright_factory(browser, fail=True)
        pool = BrowserSessionPool(
            "ws://localhost:9222", 600, 4, playwright_factory=factory
        )
        self.assertFalse(_run(pool.start()))
        from tool_gateway.tools.browser_sessions import BrowserNotReady

        with self.assertRaises(BrowserNotReady):
            _run(pool.get_or_create("user-a"))

    def test_bare_ws_endpoint_dialed_as_http_discovery_base(self) -> None:
        # Playwright dials a bare ws:// endpoint verbatim and 404s on "/";
        # the pool must hand it the http:// discovery base instead so it
        # resolves /json/version for the real browser websocket.
        _run(self.pool.get_or_create("user-a"))
        self.assertEqual(self.host.chromium.dialed, ["http://localhost:9222/"])

    def test_endpoint_normalization_matrix(self) -> None:
        from tool_gateway.tools.browser_sessions import _normalize_cdp_endpoint

        cases = {
            "ws://localhost:9222": "http://localhost:9222/",
            "ws://localhost:9222/": "http://localhost:9222/",
            "wss://browser.example:9222": "https://browser.example:9222/",
            # a complete browser websocket URL passes through untouched
            "ws://localhost:9222/devtools/browser/abc-123": (
                "ws://localhost:9222/devtools/browser/abc-123"
            ),
            # http(s) discovery bases pass through untouched
            "http://localhost:9222": "http://localhost:9222",
        }
        for endpoint, expected in cases.items():
            with self.subTest(endpoint=endpoint):
                self.assertEqual(_normalize_cdp_endpoint(endpoint), expected)

    def test_concurrent_same_key_creates_one_context(self) -> None:
        # Two first-use callers for the same key must not each build a
        # browser context (the second insert would orphan the first). The
        # per-key creation lock + double-check collapse them onto one.
        _run(self.pool.start())  # isolate creation from the connect path

        async def _scenario():
            return await asyncio.gather(
                self.pool.get_or_create("user-a"),
                self.pool.get_or_create("user-a"),
            )

        first, second = _run(_scenario())
        self.assertIs(first, second)
        self.assertIs(first.page, second.page)
        self.assertEqual(len(self.browser.contexts), 1)
        self.assertEqual(self.pool.session_count, 1)


# --- Registration -----------------------------------------------------------


class RegistrationTests(unittest.TestCase):
    def test_read_tools_only_without_mutating_admission(self) -> None:
        connector, _ = _make_connector()
        registry = _registry(connector, allow_mutating=False)
        names = {d.name: d for d in registry.list_definitions()}
        # Read-tier tools only. web.evaluate is write-tier (arbitrary JS can
        # mutate the DOM and read back masked secrets), so it is NOT
        # registered when mutating admission is off.
        read_names = {
            "web.navigate", "web.snapshot", "web.screenshot",
            "web.fill_credential",
            # SPEC-050 read-tier tools.
            "web.extract", "web.wait_for", "web.hover",
            "web.scroll", "web.switch_frame",
        }
        self.assertEqual(set(names), read_names)
        # Write-tier tools must be absent.
        for write_name in ("web.click", "web.type", "web.select",
                           "web.press_key", "web.upload_file",
                           "web.evaluate"):
            self.assertNotIn(write_name, names)

    def test_interaction_tools_admitted_with_mutating_flag(self) -> None:
        connector, _ = _make_connector()
        registry = _registry(connector, allow_mutating=True)
        names = {d.name: d for d in registry.list_definitions()}
        # 6 original + 9 new SPEC-050 tools = 15 total.
        self.assertEqual(len(names), 15)
        # SPEC-049 write-tier.
        self.assertEqual(names["web.click"].risk_level, "write")
        self.assertEqual(names["web.type"].risk_level, "write")
        # SPEC-050 write-tier.
        self.assertEqual(names["web.select"].risk_level, "write")
        self.assertEqual(names["web.press_key"].risk_level, "write")
        self.assertEqual(names["web.upload_file"].risk_level, "write")
        # web.evaluate is write-tier (issues #2/#3): arbitrary JS can mutate
        # the DOM and read masked secrets, so it inherits the HITL gate.
        self.assertEqual(names["web.evaluate"].risk_level, "write")
        # SPEC-050 read-tier.
        self.assertEqual(names["web.navigate"].risk_level, "read")
        self.assertEqual(names["web.extract"].risk_level, "read")
        self.assertEqual(names["web.wait_for"].risk_level, "read")
        self.assertEqual(names["web.hover"].risk_level, "read")
        self.assertEqual(names["web.scroll"].risk_level, "read")
        self.assertEqual(names["web.switch_frame"].risk_level, "read")
        self.assertEqual(names["web.click"].category, "browser")

    def test_browser_not_ready_is_structured(self) -> None:
        connector, _ = _make_connector(fail_connect=True)
        registry = _registry(connector)
        result = _run(
            registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/login"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_NOT_READY")


# --- Origin allowlist -------------------------------------------------------


class AllowlistTests(unittest.TestCase):
    def test_origin_of(self) -> None:
        self.assertEqual(
            origin_of("https://Inventory.Internal:8443/login?x=1"),
            "https://inventory.internal:8443",
        )
        self.assertIsNone(origin_of("ftp://x.internal"))
        self.assertIsNone(origin_of("not a url"))

    def test_allowlist_matrix(self) -> None:
        connector, _ = _make_connector()
        self.assertTrue(connector.is_origin_allowed(f"{ALLOWED_ORIGIN}/login"))
        self.assertFalse(connector.is_origin_allowed("https://evil.example/x"))
        empty, _ = _make_connector(allow_origins=())
        self.assertFalse(empty.is_origin_allowed(f"{ALLOWED_ORIGIN}/login"))

    def test_navigate_outside_allowlist_denied(self) -> None:
        connector, browser = _make_connector()
        registry = _registry(connector)
        result = _run(
            registry.invoke(
                "web.navigate", {"url": "https://evil.example/login"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_ORIGIN_NOT_ALLOWED")
        self.assertIn("evil.example", result.error["message"])
        self.assertEqual(browser.contexts, [])  # no session was created

    def test_empty_allowlist_denies_all(self) -> None:
        connector, _ = _make_connector(allow_origins=())
        registry = _registry(connector)
        result = _run(
            registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/login"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_ORIGIN_NOT_ALLOWED")

    def test_redirect_landing_outside_allowlist_errors_and_halts(self) -> None:
        connector, browser = _make_connector()
        registry = _registry(connector)

        async def _scenario():
            entry = await connector.pool.get_or_create("dev.operator")
            entry.page.redirect_to = "https://evil.example/phish"
            return await registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/login"}, IDENTITY
            )

        result = _run(_scenario())
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_REDIRECT_NOT_ALLOWED")
        self.assertIn("evil.example", result.error["message"])
        # The session page was halted and its flow cleared.
        entry = connector.pool.get("dev.operator")
        self.assertEqual(entry.page.goto_calls[-1], "about:blank")
        self.assertIsNone(entry.flow)


# --- Secret query-param redaction (SPEC-049 R-5) ---------------------------


class SecretQueryRedactionTests(unittest.TestCase):
    def test_masks_secret_param_value(self) -> None:
        url = "https://app.internal/reset?user=alice&newpw=TempPass123!"
        self.assertEqual(
            _redact_secret_query(url),
            "https://app.internal/reset?user=alice&newpw=***",
        )

    def test_masks_multiple_secret_params_keeps_others(self) -> None:
        redacted = _redact_secret_query(
            "https://app.internal/x?password=a&token=b&q=keep"
        )
        self.assertIn("password=***", redacted)
        self.assertIn("token=***", redacted)
        self.assertIn("q=keep", redacted)
        self.assertNotIn("=a", redacted)
        self.assertNotIn("=b", redacted)

    def test_param_match_is_case_insensitive(self) -> None:
        self.assertIn(
            "NewPassword=***",
            _redact_secret_query("https://app.internal/x?NewPassword=hunter2"),
        )

    def test_param_match_is_substring(self) -> None:
        redacted = _redact_secret_query(
            "https://app.internal/x?user_password=p&api_key=k"
        )
        self.assertIn("user_password=***", redacted)
        self.assertIn("api_key=***", redacted)

    def test_url_without_secret_params_is_unchanged(self) -> None:
        url = "https://app.internal/status?user=alice&page=2"
        self.assertEqual(_redact_secret_query(url), url)

    def test_url_without_query_is_unchanged(self) -> None:
        url = "https://app.internal/status"
        self.assertEqual(_redact_secret_query(url), url)


# --- Navigate + flow binding ------------------------------------------------


class FlowBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)

    def _navigate(self, params: dict):
        return _run(self.registry.invoke("web.navigate", params, IDENTITY))

    def test_navigate_success_without_skill(self) -> None:
        result = self._navigate({"url": f"{ALLOWED_ORIGIN}/status"})
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["url"], f"{ALLOWED_ORIGIN}/status")
        self.assertEqual(result.data["title"], "Fake App")
        self.assertNotIn("flow", result.data)
        self.assertEqual(result.evidence["source_system"], "browser")
        self.assertEqual(result.evidence["risk_level"], "read")

    def test_navigate_redacts_secret_query_params(self) -> None:
        # The password-reset demo passes ``?newpw=...`` so the legacy target
        # can auto-fill it; the plaintext value must never enter evidence
        # (SPEC-049 R-5), but the page still navigates with the real value.
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/admin/reset?user=alice&newpw=TempPass123!"}
        )
        self.assertEqual(result.status, "success")
        self.assertNotIn("TempPass123!", result.data["url"])
        self.assertIn("newpw=***", result.data["url"])
        self.assertIn("user=alice", result.data["url"])
        # The real value still reached the page.
        entry = self.connector.pool.get("dev.operator")
        self.assertIn("newpw=TempPass123!", entry.page.url)

    def test_navigate_binds_write_flow(self) -> None:
        _stub_skill(self.connector, _web_skill("write"))
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login", "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["flow"]["skill_id"], "team-a/web/inventoryhealth")
        self.assertEqual(result.data["flow"]["risk_class"], "write")
        self.assertFalse(result.data["flow"]["approved"])
        flow = self.connector.pool.get("dev.operator").flow
        self.assertIsInstance(flow, FlowState)
        self.assertEqual(flow.origin, "https://inventory.internal:8443")

    def test_navigate_binds_read_flow_approved(self) -> None:
        _stub_skill(self.connector, _web_skill("read"))
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login", "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(result.status, "success")
        self.assertTrue(result.data["flow"]["approved"])

    def test_risk_class_defaults_read_when_absent(self) -> None:
        skill = _web_skill(None)
        skill.pop("risk_class")
        _stub_skill(self.connector, skill)
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login", "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["flow"]["risk_class"], "read")

    def test_flow_target_mismatch_denied(self) -> None:
        _stub_skill(self.connector, _web_skill("write"))
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/other", "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_TARGET_MISMATCH")

    def test_skill_without_web_target_errors(self) -> None:
        _stub_skill(self.connector, {"skill_id": "team-a/plain"})
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login", "skill_id": "team-a/plain"}
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SKILL_NOT_WEB_FLOW")

    def test_unknown_skill_errors(self) -> None:
        _stub_skill(self.connector, None)
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login", "skill_id": "team-a/web/ghost"}
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "SKILL_NOT_FOUND")

    def test_invalid_url_rejected(self) -> None:
        result = self._navigate({"url": "javascript:alert(1)"})
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_flow_target_path_requires_segment_boundary(self) -> None:
        _stub_skill(self.connector, _web_skill("write"))
        # A sibling path sharing only the "/login" prefix is NOT "under" the
        # declared target and must be refused...
        denied = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/loginfoo",
             "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(denied.status, "denied")
        self.assertEqual(denied.error["code"], "BROWSER_FLOW_TARGET_MISMATCH")
        # ...while a real sub-path of the target is admitted.
        allowed = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login/sso",
             "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(allowed.status, "success")

    def test_navigation_error_after_bind_clears_flow(self) -> None:
        _stub_skill(self.connector, _web_skill("write"))
        entry = _run(self.connector.pool.get_or_create("dev.operator"))

        async def _boom(url: str, **kwargs) -> None:
            raise RuntimeError("dns failure")

        entry.page.goto = _boom  # type: ignore[method-assign]
        result = self._navigate(
            {"url": f"{ALLOWED_ORIGIN}/login",
             "skill_id": "team-a/web/inventoryhealth"}
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_NAVIGATION_ERROR")
        # The flow bound on this call never reached its target, so it is
        # dropped rather than left stale for a later interaction.
        self.assertIsNone(entry.flow)


# --- Deviation guard --------------------------------------------------------


class DeviationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector(flow_max_steps=2)
        self.registry = _registry(self.connector)

    def _bind_write_flow(self) -> None:
        _stub_skill(self.connector, _web_skill("write"))
        result = _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "success")
        page = self.connector.pool.get("dev.operator").page
        page.add_element(tag="BUTTON", text="Submit")
        # Refs are only minted by a snapshot (R-2/R-4 contract).
        snap = _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        self.assertEqual(snap.status, "success")

    def test_click_without_bound_flow_denied(self) -> None:
        result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_NOT_BOUND")

    def test_click_in_read_flow_denied(self) -> None:
        _stub_skill(self.connector, _web_skill("read"))
        _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                IDENTITY,
            )
        )
        result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_READ_ONLY")

    def test_approved_write_flow_executes_and_records(self) -> None:
        self._bind_write_flow()
        result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.evidence["risk_level"], "write")
        self.assertEqual(result.data["steps_used"], 1)
        self.assertEqual(result.data["steps_budget"], 2)
        flow = self.connector.pool.get("dev.operator").flow
        self.assertTrue(flow.approved)  # execution is evidence of approval
        element = self.connector.pool.get("dev.operator").page.elements[0]
        self.assertEqual(element.clicks, 1)

    def test_denied_flow_refuses_interactions(self) -> None:
        self._bind_write_flow()
        self.connector.pool.get("dev.operator").flow.denied = True
        result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_DENIED")
        element = self.connector.pool.get("dev.operator").page.elements[0]
        self.assertEqual(element.clicks, 0)

    def test_step_budget_exhaustion_denies(self) -> None:
        self._bind_write_flow()
        for expected_steps in (1, 2):
            result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
            self.assertEqual(result.status, "success")
            self.assertEqual(result.data["steps_used"], expected_steps)
        result = _run(self.registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_EXHAUSTED")

    def test_unknown_ref_errors(self) -> None:
        self._bind_write_flow()
        result = _run(self.registry.invoke("web.click", {"ref": 99}, IDENTITY))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_REF_UNKNOWN")

    def test_type_executes_inside_bound_flow(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        field = page.add_element(tag="INPUT", type="text", name="note")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.type", {"ref": 2, "text": "maintenance window"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(field.fills, ["maintenance window"])

    def test_interaction_off_flow_origin_denied(self) -> None:
        # A plain navigate to a *second* allowlisted origin leaves the flow
        # bound to the first; the guard must refuse the off-origin write
        # rather than run it under an approval that named the first target.
        other = "https://other.internal:8443"
        connector, _ = _make_connector(allow_origins=(ALLOWED_ORIGIN, other))
        registry = _registry(connector)
        _stub_skill(connector, _web_skill("write"))
        bind = _run(
            registry.invoke(
                "web.navigate",
                {"url": f"{ALLOWED_ORIGIN}/login",
                 "skill_id": "team-a/web/inventoryhealth"},
                IDENTITY,
            )
        )
        self.assertEqual(bind.status, "success")
        # Drift to the other allowlisted origin without rebinding the flow.
        drift = _run(
            registry.invoke("web.navigate", {"url": f"{other}/admin"}, IDENTITY)
        )
        self.assertEqual(drift.status, "success")
        entry = connector.pool.get("dev.operator")
        self.assertIsNotNone(entry.flow)  # still bound to the first origin
        entry.page.add_element(tag="BUTTON", text="Delete")
        _run(registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(registry.invoke("web.click", {"ref": 1}, IDENTITY))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_ORIGIN_DEVIATED")
        self.assertEqual(entry.page.elements[0].clicks, 0)


# --- Chat-session keying (SPEC-049 R-1) -------------------------------------


class ChatSessionKeyingTests(unittest.TestCase):
    """The pool keys on the chat session id, so one browser context spans a
    whole web-check flow across the owner→approver HITL identity switch:
    the resumed write-tier interaction carries the approver's subject but
    the same chat session, and must land on the flow the owner bound."""

    def setUp(self) -> None:
        self.connector, self.browser = _make_connector(flow_max_steps=5)
        self.registry = _registry(self.connector)
        _stub_skill(self.connector, _web_skill("write"))

    def test_session_key_prefers_chat_session_then_subject(self) -> None:
        self.assertEqual(
            self.connector._session_key(
                {"sub": "luban-operator", "chat_session_id": "ses-1"}
            ),
            "ses-1",
        )
        self.assertEqual(
            self.connector._session_key({"sub": "luban-operator"}),
            "luban-operator",
        )
        self.assertIsNone(self.connector._session_key({"username": "x"}))

    def _bind_write_flow(self, identity: dict) -> None:
        result = _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                identity,
            )
        )
        self.assertEqual(result.status, "success")
        page = self.connector.pool.get(identity["chat_session_id"]).page
        page.add_element(tag="BUTTON", text="Submit")
        snap = _run(self.registry.invoke("web.snapshot", {}, identity))
        self.assertEqual(snap.status, "success")

    def test_write_flow_survives_owner_to_approver_switch(self) -> None:
        owner = {
            "sub": "luban-operator",
            "username": "luban-operator",
            "roles": ["operator"],
            "chat_session_id": "ses-flow-1",
        }
        approver = {
            "sub": "luban-approver",
            "username": "luban-approver",
            "roles": ["approver"],
            "chat_session_id": "ses-flow-1",
        }
        self._bind_write_flow(owner)
        # The approver resumes the write-tier interaction under a different
        # subject but the same chat session: it lands on the owner's bound
        # flow, never a fresh about:blank context.
        result = _run(self.registry.invoke("web.click", {"ref": 1}, approver))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["steps_used"], 1)
        self.assertEqual(self.connector.pool.session_count, 1)
        self.assertIsNotNone(self.connector.pool.get("ses-flow-1"))
        element = self.connector.pool.get("ses-flow-1").page.elements[0]
        self.assertEqual(element.clicks, 1)

    def test_different_chat_session_does_not_share_flow(self) -> None:
        owner = {
            "sub": "luban-operator",
            "roles": ["operator"],
            "chat_session_id": "ses-flow-1",
        }
        other = {
            "sub": "luban-operator",
            "roles": ["operator"],
            "chat_session_id": "ses-flow-2",
        }
        self._bind_write_flow(owner)
        # A different chat session is a different flow even for the same
        # subject: keying is per chat session, never global.
        result = _run(self.registry.invoke("web.click", {"ref": 1}, other))
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_NOT_BOUND")


# --- Snapshot + masking -----------------------------------------------------


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _stub_skill(self.connector, _web_skill("write"))
        _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                IDENTITY,
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_snapshot_enumerates_refs(self) -> None:
        self.page.add_element(tag="BUTTON", text="Sign in")
        self.page.add_element(tag="INPUT", type="text", name="username", value="svc-check")
        result = _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["elements"], 2)
        snapshot = result.data["snapshot"]
        self.assertIn('[1] <button> "Sign in"', snapshot)
        self.assertIn("[2] <input type=text>", snapshot)
        self.assertIn("'svc-check'", snapshot)

    def test_password_values_masked(self) -> None:
        self.page.add_element(tag="INPUT", type="password", value=PASSWORD_LITERAL)
        result = _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        snapshot = result.data["snapshot"]
        self.assertIn("value=***", snapshot)
        self.assertNotIn(PASSWORD_LITERAL, json.dumps(result.to_dict()))


# --- Credentials ------------------------------------------------------------


class CredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(
            {"inventory-app": {"username": "svc-check", "password": PASSWORD_LITERAL}},
            self._tmp,
        )
        self._tmp.close()
        self.connector, self.browser = _make_connector(
            credential_sets_path=self._tmp.name
        )
        self.registry = _registry(self.connector)
        _stub_skill(self.connector, _web_skill("write"))
        _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                IDENTITY,
            )
        )
        self.page = self.connector.pool.get("dev.operator").page
        self.password_field = self.page.add_element(
            tag="INPUT", type="password", name="password"
        )
        snap = _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        self.assertEqual(snap.status, "success")

    def tearDown(self) -> None:
        os.unlink(self._tmp.name)

    def test_fill_credential_end_to_end(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.fill_credential",
                {"ref": 1, "credential_set": "inventory-app", "field": "password"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["filled"], "password")
        self.assertEqual(self.password_field.fills, [PASSWORD_LITERAL])
        # Leak assertion: the password literal appears in no result field.
        self.assertNotIn(PASSWORD_LITERAL, json.dumps(result.to_dict()))

    def test_filled_value_masked_in_subsequent_snapshot(self) -> None:
        _run(
            self.registry.invoke(
                "web.fill_credential",
                {"ref": 1, "credential_set": "inventory-app", "field": "password"},
                IDENTITY,
            )
        )
        result = _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        serialized = json.dumps(result.to_dict())
        self.assertNotIn(PASSWORD_LITERAL, serialized)
        self.assertIn("value=***", result.data["snapshot"])

    def test_unknown_credential_set_errors(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.fill_credential",
                {"ref": 1, "credential_set": "ghost", "field": "password"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "CREDENTIAL_SET_NOT_FOUND")
        # W-3: the error must name the unknown set but must NOT enumerate
        # the available sets (information disclosure).
        self.assertIn("ghost", result.error["message"])
        self.assertNotIn("inventory-app", result.error["message"])

    def test_invalid_field_rejected(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.fill_credential",
                {"ref": 1, "credential_set": "inventory-app", "field": "token"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_fill_requires_bound_flow(self) -> None:
        connector, _ = _make_connector(credential_sets_path=self._tmp.name)
        registry = _registry(connector)
        page_entry = _run(connector.pool.get_or_create("dev.operator"))
        page_entry.page.add_element(tag="INPUT", type="password")
        result = _run(
            registry.invoke(
                "web.fill_credential",
                {"ref": 1, "credential_set": "inventory-app", "field": "password"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_NOT_BOUND")

    def test_password_masked_out_of_screenshot(self) -> None:
        # A legacy target may render a password into a type=text field; the
        # connector masks password-tier values out of the capture (R-5) and
        # restores the page afterward, so the secret never reaches evidence.
        legacy = self.page.add_element(tag="INPUT", type="text", name="legacy")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))  # mint ref 2
        fill = _run(
            self.registry.invoke(
                "web.fill_credential",
                {"ref": 2, "credential_set": "inventory-app", "field": "password"},
                IDENTITY,
            )
        )
        self.assertEqual(fill.status, "success")
        shot = _run(self.registry.invoke("web.screenshot", {}, IDENTITY))
        self.assertEqual(shot.status, "success")
        # At capture time the password was masked to dots...
        self.assertNotIn(PASSWORD_LITERAL, self.page.last_capture_values)
        self.assertIn("\u2022" * 8, self.page.last_capture_values)
        # ...and the field was restored afterward (masking is transient).
        self.assertEqual(legacy.info["value"], PASSWORD_LITERAL)


# --- Screenshots ------------------------------------------------------------


class ScreenshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector(screenshot_max_bytes=65536)
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/status"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_screenshot_success_within_cap(self) -> None:
        result = _run(self.registry.invoke("web.screenshot", {}, IDENTITY))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["format"], "jpeg")
        self.assertLessEqual(result.data["bytes"], 65536)
        import base64

        self.assertEqual(
            len(base64.b64decode(result.data["screenshot"])), result.data["bytes"]
        )

    def test_oversize_screenshot_compressed_to_cap(self) -> None:
        # Every quality alone exceeds the cap; only the shrinking clip fits.
        def _rule(quality: int, clip: dict | None) -> bytes:
            size = 100_000
            if clip is not None:
                size = int(size * clip["width"] * clip["height"] / (1280 * 720))
            return b"x" * size

        self.page.screenshot_rule = _rule
        result = _run(self.registry.invoke("web.screenshot", {}, IDENTITY))
        self.assertEqual(result.status, "success")
        self.assertLessEqual(result.data["bytes"], 65536)

    def test_uncompressible_screenshot_errors(self) -> None:
        self.page.screenshot_rule = lambda quality, clip: b"x" * 200_000
        result = _run(self.registry.invoke("web.screenshot", {}, IDENTITY))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_SCREENSHOT_TOO_LARGE")


# --- SPEC-050: new tool tests -----------------------------------------------


class _BoundFlowMixin:
    """Shared helper: bind a write flow and mint refs for interaction tests."""

    connector: BrowserConnector
    registry: ToolRegistry

    def _bind_write_flow(self, identity=None) -> None:
        identity = identity or IDENTITY
        _stub_skill(self.connector, _web_skill("write"))
        result = _run(
            self.registry.invoke(
                "web.navigate",
                {
                    "url": f"{ALLOWED_ORIGIN}/login",
                    "skill_id": "team-a/web/inventoryhealth",
                },
                identity,
            )
        )
        self.assertEqual(result.status, "success")
        page = self.connector.pool.get(
            identity.get("chat_session_id", identity["sub"])
        ).page
        page.add_element(tag="BUTTON", text="Submit")
        snap = _run(self.registry.invoke("web.snapshot", {}, identity))
        self.assertEqual(snap.status, "success")


class WebSelectTests(unittest.TestCase, _BoundFlowMixin):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)

    def test_select_success(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        select_el = page.add_element(
            tag="SELECT", name="priority", options=["low", "high"]
        )
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.select", {"ref": 2, "value": "high"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(select_el.selects, ["high"])
        self.assertEqual(result.data["selected"], "high")
        self.assertEqual(result.data["steps_used"], 1)

    def test_select_not_a_select_element(self) -> None:
        self._bind_write_flow()
        # ref 1 is the BUTTON from _bind_write_flow
        result = _run(
            self.registry.invoke(
                "web.select", {"ref": 1, "value": "x"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_SELECT_NOT_A_SELECT")

    def test_select_option_not_found(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        page.add_element(
            tag="SELECT", name="priority", options=["low", "high"]
        )
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.select", {"ref": 2, "value": "missing"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_SELECT_OPTION_NOT_FOUND")

    def test_select_without_flow_denied(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.select", {"ref": 1, "value": "x"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FLOW_NOT_BOUND")


class WebPressKeyTests(unittest.TestCase, _BoundFlowMixin):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)

    def test_press_key_success(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        result = _run(
            self.registry.invoke(
                "web.press_key", {"key": "Enter"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(page.keyboard.presses, ["Enter"])
        self.assertEqual(result.data["key"], "Enter")

    def test_press_key_with_ref_focuses_first(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        field = page.add_element(tag="INPUT", type="text", name="search")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.press_key", {"ref": 2, "key": "Tab"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(field.focuses, 1)
        self.assertEqual(page.keyboard.presses, ["Tab"])

    def test_press_key_without_flow_denied(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.press_key", {"key": "Enter"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "denied")


class WebExtractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/status"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_extract_list_items(self) -> None:
        self.page.add_element(tag="LI", text="Alert 1")
        self.page.add_element(tag="LI", text="Alert 2")
        result = _run(
            self.registry.invoke(
                "web.extract", {"selector": "li"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["count"], 2)
        self.assertIn("Alert 1", result.data["items"])

    def test_extract_empty_result(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.extract", {"selector": ".nonexistent"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["items"], [])
        self.assertEqual(result.data["count"], 0)


class WebWaitForTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/status"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_wait_for_visible_success(self) -> None:
        self.page.add_element(tag="DIV", text="Loaded")
        result = _run(
            self.registry.invoke(
                "web.wait_for", {"selector": "div"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["state"], "visible")

    def test_wait_for_timeout(self) -> None:
        self.page.wait_fail = True
        result = _run(
            self.registry.invoke(
                "web.wait_for",
                {"selector": ".loading", "timeout_ms": 1000},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_WAIT_TIMEOUT")

    def test_wait_for_timeout_capped(self) -> None:
        self.page.wait_fail = True
        result = _run(
            self.registry.invoke(
                "web.wait_for",
                {"selector": ".x", "timeout_ms": 99999},
                IDENTITY,
            )
        )
        # Server caps at 30000ms; the error message should reflect the cap.
        self.assertEqual(result.status, "error")
        self.assertIn("30000", result.error["message"])


class WebHoverTests(unittest.TestCase, _BoundFlowMixin):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)

    def test_hover_success(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        btn = page.add_element(tag="BUTTON", text="Menu")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        # Hover is read-tier, so no write flow needed — just need a bound
        # flow for gate_capture. Use a read flow instead.
        _stub_skill(self.connector, _web_skill("read"))
        _run(
            self.registry.invoke(
                "web.navigate",
                {"url": f"{ALLOWED_ORIGIN}/login",
                 "skill_id": "team-a/web/inventoryhealth"},
                IDENTITY,
            )
        )
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke("web.hover", {"ref": 2}, IDENTITY)
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(btn.hovers, 1)


class WebEvaluateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/status"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_evaluate_simple_expression(self) -> None:
        # The fake evaluate returns None for any JS, which serializes fine.
        result = _run(
            self.registry.invoke(
                "web.evaluate", {"expression": "document.title"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        # Write tier (issues #2/#3): the evidence reflects the HITL-gated
        # classification, not the old read tier.
        self.assertEqual(result.evidence["risk_level"], "write")

    def test_evaluate_empty_expression_errors(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate", {"expression": ""}, IDENTITY
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_evaluate_blocks_click_mutation(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate",
                {"expression": "document.querySelector('button').click()"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_EVAL_MUTATION_BLOCKED")

    def test_evaluate_blocks_submit_mutation(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate",
                {"expression": "document.forms[0].submit()"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_EVAL_MUTATION_BLOCKED")

    def test_evaluate_blocks_fetch(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate",
                {"expression": "fetch('/api/delete', {method:'DELETE'})"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_EVAL_MUTATION_BLOCKED")

    def test_evaluate_blocks_innerHTML_assignment(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate",
                {"expression": "document.body.innerHTML = '<p>pwned</p>'"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_EVAL_MUTATION_BLOCKED")

    def test_evaluate_blocks_navigation(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.evaluate",
                {"expression": "window.location = 'http://evil.com'"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_EVAL_MUTATION_BLOCKED")

    def test_evaluate_allows_read_only_expressions(self) -> None:
        # These should pass the guard (no mutation patterns).
        for expr in (
            "document.title",
            "document.querySelectorAll('a').length",
            "JSON.stringify(window.performance.timing)",
            "document.cookie",
            "navigator.userAgent",
            "window.innerWidth",
            # Equality comparisons must NOT be blocked (issue #7)
            "document.querySelector('#user').value === 'alice'",
            "el.textContent === 'Deployed'",
            "document.querySelectorAll('td')[0].innerText == 'OK'",
            "cb.checked === true",
            "btn.disabled == false",
            # String.prototype.replace is a read-only transform
            "[...tds].map(td => td.innerText.replace(/\\s+/g,' '))",
            # classList.contains is a read
            "document.querySelector('.row').classList.contains('active')",
            # Reading style properties is legitimate
            "el.style.zIndex",
            "getComputedStyle(el).display",
        ):
            result = _run(
                self.registry.invoke(
                    "web.evaluate", {"expression": expr}, IDENTITY
                )
            )
            self.assertNotEqual(
                result.error.get("code") if result.error else None,
                "BROWSER_EVAL_MUTATION_BLOCKED",
                f"Expression wrongly blocked: {expr}",
            )


class WebScrollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/status"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_scroll_success(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.scroll", {"delta_x": 0, "delta_y": 500}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(self.page.mouse.wheels, [(0, 500)])
        # No frame is active, so the cursor is never repositioned.
        self.assertEqual(self.page.mouse.moves, [])

    def test_scroll_defaults(self) -> None:
        result = _run(self.registry.invoke("web.scroll", {}, IDENTITY))
        self.assertEqual(result.status, "success")
        # Default: delta_x=0, delta_y=300.
        self.assertEqual(self.page.mouse.wheels, [(0, 300)])

    def test_scroll_centers_cursor_over_active_frame(self) -> None:
        # A Page-level wheel scrolls whatever is under the cursor, so when
        # an iframe is active web.scroll must first move the cursor to the
        # frame's center (issue #5).
        frame = FakeFrame(
            url=f"{ALLOWED_ORIGIN}/dashboard/chart",
            box={"x": 200.0, "y": 100.0, "width": 300.0, "height": 150.0},
        )
        iframe_el = self.page.add_element(tag="IFRAME", name="chart")
        iframe_el._frame = frame
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        switch = _run(
            self.registry.invoke(
                "web.switch_frame", {"selector": "iframe"}, IDENTITY
            )
        )
        self.assertEqual(switch.status, "success")
        result = _run(
            self.registry.invoke(
                "web.scroll", {"delta_x": 0, "delta_y": 250}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        # Cursor moved to the frame center (200+300/2, 100+150/2) first.
        self.assertEqual(self.page.mouse.moves, [(350.0, 175.0)])
        self.assertEqual(self.page.mouse.wheels, [(0, 250)])


class WebSwitchFrameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connector, self.browser = _make_connector()
        self.registry = _registry(self.connector)
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/dashboard"}, IDENTITY
            )
        )
        self.page = self.connector.pool.get("dev.operator").page

    def test_switch_frame_success(self) -> None:
        frame = FakeFrame(url=f"{ALLOWED_ORIGIN}/dashboard/chart")
        frame.add_element = lambda **kw: (
            el := FakeElementHandle(kw, self.page),
            frame.elements.append(el),
            el
        )[-1]
        iframe_el = self.page.add_element(tag="IFRAME", name="chart")
        iframe_el._frame = frame
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.switch_frame", {"selector": "iframe"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["frame_depth"], 1)
        entry = self.connector.pool.get("dev.operator")
        self.assertEqual(len(entry.frame_stack), 1)

    def test_switch_frame_not_found(self) -> None:
        result = _run(
            self.registry.invoke(
                "web.switch_frame", {"selector": "iframe"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_FRAME_NOT_FOUND")

    def test_switch_frame_cross_origin_denied(self) -> None:
        frame = FakeFrame(url="https://evil.example/embed")
        iframe_el = self.page.add_element(tag="IFRAME", name="ad")
        iframe_el._frame = frame
        # Bind a write flow first so the origin check fires.
        _stub_skill(self.connector, _web_skill("write"))
        _run(
            self.registry.invoke(
                "web.navigate",
                {"url": f"{ALLOWED_ORIGIN}/login",
                 "skill_id": "team-a/web/inventoryhealth"},
                IDENTITY,
            )
        )
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.switch_frame", {"selector": "iframe"}, IDENTITY
            )
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error["code"], "BROWSER_FRAME_ORIGIN_MISMATCH")

    def test_navigate_resets_frame_stack(self) -> None:
        frame = FakeFrame(url=f"{ALLOWED_ORIGIN}/inner")
        iframe_el = self.page.add_element(tag="IFRAME", name="inner")
        iframe_el._frame = frame
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        _run(
            self.registry.invoke(
                "web.switch_frame", {"selector": "iframe"}, IDENTITY
            )
        )
        entry = self.connector.pool.get("dev.operator")
        self.assertEqual(len(entry.frame_stack), 1)
        # Navigate resets the frame stack.
        _run(
            self.registry.invoke(
                "web.navigate", {"url": f"{ALLOWED_ORIGIN}/other"}, IDENTITY
            )
        )
        self.assertEqual(len(entry.frame_stack), 0)


class WebUploadFileTests(unittest.TestCase, _BoundFlowMixin):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        # Create a test file.
        self._test_file = os.path.join(self._tmpdir, "config.yaml")
        with open(self._test_file, "w") as f:
            f.write("test: true")
        self.connector, self.browser = _make_connector()
        self.connector._upload_dir = self._tmpdir
        self.registry = _registry(self.connector)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_upload_success(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        file_input = page.add_element(tag="INPUT", type="file", name="upload")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.upload_file",
                {"ref": 2, "filename": "config.yaml"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["uploaded"], "config.yaml")
        self.assertEqual(len(file_input.uploaded_files), 1)

    def test_upload_path_traversal_denied(self) -> None:
        self._bind_write_flow()
        result = _run(
            self.registry.invoke(
                "web.upload_file",
                {"ref": 1, "filename": "../etc/passwd"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_UPLOAD_PATH_NOT_ALLOWED")

    def test_upload_not_a_file_input(self) -> None:
        self._bind_write_flow()
        # ref 1 is the BUTTON from _bind_write_flow
        result = _run(
            self.registry.invoke(
                "web.upload_file",
                {"ref": 1, "filename": "config.yaml"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_UPLOAD_NOT_A_FILE_INPUT")

    def test_upload_file_not_found(self) -> None:
        self._bind_write_flow()
        page = self.connector.pool.get("dev.operator").page
        page.add_element(tag="INPUT", type="file", name="upload")
        _run(self.registry.invoke("web.snapshot", {}, IDENTITY))
        result = _run(
            self.registry.invoke(
                "web.upload_file",
                {"ref": 2, "filename": "nonexistent.txt"},
                IDENTITY,
            )
        )
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "BROWSER_UPLOAD_FILE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
