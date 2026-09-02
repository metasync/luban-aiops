"""Browser connector: bounded web-check tool surface (SPEC-049 R-1..R-6).

Drives the pod's chromium-headless-shell sidecar over CDP through a
stateful session pool and registers a small, fixed tool surface:

  read tier   web.navigate, web.snapshot, web.screenshot,
              web.fill_credential
  write tier  web.click, web.type

Enforcement surfaces (all server-side, never model-trusted):

- Origin allowlist (R-2): navigation to an origin outside
  ``GATEWAY_BROWSER_ALLOW_ORIGINS`` is denied; redirects landing outside
  halt the page and error, and every read-tier capture re-checks the live
  origin first, so a post-load client-side redirect can't be snapshotted
  or screenshotted off-allowlist (or off the bound flow). An empty
  allowlist denies everything.
- Flow binding + deviation guard (R-4): ``web.navigate`` with a
  ``skill_id`` validates the skill's ``web_target``/``risk_class``
  declaration against skills-hub and binds the flow to the session.
  Interactions only execute inside a bound, approved, unexhausted flow —
  anything else is denied, never run silently. Write-tier interactions
  additionally ride the existing SPEC-020 confirmation bridge and SPEC-037
  signed execution upstream of the gateway, so an interaction that
  executes here is evidence of operator approval (recorded on the flow).
- Credential sets (R-5): login values resolve from a secret-mounted file
  at fill time; they never appear in results, snapshots, or logs.

Identity note: sessions key on the caller's chat session id (SPEC-049
R-1) so one stateful browser context spans a whole web-check flow —
including the owner→approver identity switch the SPEC-020/037 write path
introduces, where the resumed write-tier interaction legitimately arrives
under the approver's subject. The chat session id is a correlation handle
forwarded by trusted internal callers (the kernel and the execution
worker), never a model-supplied parameter; authority still rides the
verified bearer token. When no chat session id is present (a non-chat
caller) the connector falls back to the verified subject.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from urllib.parse import urlparse

import httpx

from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from tool_gateway.tools.browser_sessions import (
    BrowserNotReady,
    BrowserSessionEntry,
    BrowserSessionPool,
    FlowState,
)
from tool_gateway.tools.credential_sets import CredentialSetStore
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "browser"
CATEGORY = "browser"

NAVIGATION_TIMEOUT_MS = 30_000
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_SNAPSHOT_ELEMENTS = 200
SNAPSHOT_MAX_CHARS = 16_000
SCREENSHOT_QUALITIES = (70, 55, 40, 25, 15)
SCREENSHOT_CLIP_FRACTIONS = (0.75, 0.5, 0.35, 0.25)
SKILL_PATH_TEMPLATE = "/api/v1/skills/{skill_id}"
# Same contract pattern as the skills connector: the id is interpolated
# into the upstream URL path, so anything else is untrusted input.
_SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)+$")
# Interactive elements addressable by snapshot refs.
INTERACTIVE_SELECTOR = (
    "a, button, input, select, textarea, "
    "[role=button], [role=link], [role=tab], [role=checkbox], [onclick]"
)
_ELEMENT_INSPECT_JS = """
el => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute("type") || "",
    role: el.getAttribute("role") || "",
    name: ((el.getAttribute("aria-label") || el.getAttribute("name")
        || el.getAttribute("placeholder") || "")).slice(0, 120),
    text: ((el.innerText || "")).trim().slice(0, 120),
    value: (typeof el.value === "string") ? el.value : "",
    disabled: Boolean(el.disabled),
})
"""
CREDENTIAL_FIELDS = ("username", "password")
# Password-tier values are masked out of screenshots (R-5): a legacy target
# may render a password into a ``type=text`` field a raw capture would leak
# into evidence. A fixed-length dot mask avoids revealing the value's length;
# a filled username is never masked here (it is the visible sign-in evidence).
_SCREENSHOT_MASK_JS = """
(vals) => {
    let n = 0;
    document.querySelectorAll("input,textarea").forEach(el => {
        if (typeof el.value === "string" && vals.includes(el.value)) {
            el.setAttribute("data-cv-mask", el.value);
            el.value = "••••••••";
            n += 1;
        }
    });
    return n;
}
"""
_SCREENSHOT_UNMASK_JS = """
() => {
    document.querySelectorAll("[data-cv-mask]").forEach(el => {
        el.value = el.getAttribute("data-cv-mask");
        el.removeAttribute("data-cv-mask");
    });
}
"""


def _path_under(url_path: str, target_path: str) -> bool:
    """True when ``url_path`` equals ``target_path`` or sits under it as
    whole path segments — a declared ``/login`` admits ``/login`` and
    ``/login/sso`` but not ``/loginfoo``. A trailing slash on the declared
    target is insignificant (``/login/`` still admits ``/login``), and a
    root target (``/``) admits every path on the origin."""
    target = target_path.rstrip("/")
    if not target:  # a root target ("/") admits every path on the origin
        return True
    return url_path == target or url_path.startswith(target + "/")


def origin_of(url: str) -> str | None:
    """Return the normalized ``scheme://host[:port]`` origin, or None."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _denied(tool_name: str, code: str, message: str, risk_level: str) -> ToolResult:
    """Denial envelope with a connector-specific code (R-2/R-4)."""
    return ToolResult(
        tool_name=tool_name,
        status="denied",
        evidence=build_evidence(risk_level, SOURCE_SYSTEM, 0),
        error={"code": code, "message": message},
    )


class BrowserConnector:
    """Registers the bounded web.* tool surface behind the browser flag."""

    def __init__(
        self,
        cdp_endpoint: str,
        allow_origins: tuple[str, ...] = (),
        session_ttl_seconds: int = 600,
        max_sessions: int = 4,
        flow_max_steps: int = 20,
        credential_sets_path: str = "",
        screenshot_max_bytes: int = 65536,
        skills_service_url: str = "",
        skills_client_id: str = "",
        skills_client_secret: str = "",
        playwright_factory=None,
    ) -> None:
        # Origins compare normalized and lowercase; patterns in config are
        # trusted operator input but normalized defensively.
        self._allow_origins = frozenset(
            origin.strip().lower() for origin in allow_origins if origin.strip()
        )
        self._flow_max_steps = flow_max_steps
        self._screenshot_max_bytes = screenshot_max_bytes
        self._skills_url = skills_service_url
        self._skills_client_id = skills_client_id
        self._skills_client_secret = skills_client_secret
        self.pool = BrowserSessionPool(
            cdp_endpoint=cdp_endpoint,
            ttl_seconds=session_ttl_seconds,
            max_sessions=max_sessions,
            playwright_factory=playwright_factory,
        )
        self.credentials = CredentialSetStore(credential_sets_path)

    # --- Lifecycle (wired to app startup/shutdown when the flag is on) ---

    async def start(self) -> bool:
        return await self.pool.start()

    async def stop(self) -> None:
        await self.pool.stop()

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register all web.* tools with the given registry.

        The write-tier interaction tools are offered unconditionally; the
        registry's risk-tier admission (SPEC-021 R-1) refuses them when
        GATEWAY_MUTATING_TOOLS_ENABLED is off, exactly like k8s.delete_pod.
        """
        registry.register(WebNavigateTool(self))
        registry.register(WebSnapshotTool(self))
        registry.register(WebScreenshotTool(self))
        registry.register(WebFillCredentialTool(self))
        registry.register(WebClickTool(self))
        registry.register(WebTypeTool(self))

    # --- Enforcement surfaces ---

    def is_origin_allowed(self, url: str) -> bool:
        """Deny-by-default: an empty allowlist denies every origin."""
        origin = origin_of(url)
        return origin is not None and origin in self._allow_origins

    def _session_key(self, identity: dict) -> str | None:
        """Chat session id is the pool key (SPEC-049 R-1); subject is the
        fallback for callers that forward no chat session.

        Keying on the chat session id — not the verified subject — keeps
        one browser context bound to a whole web-check flow across the
        owner→approver HITL identity switch: the read-tier setup and the
        resumed write-tier interaction share a chat session but carry
        different subjects, and the flow (and its bound skill) must
        survive that switch. The chat session id is injected by trusted
        internal callers, never taken from model-controlled parameters.
        """
        chat_session_id = identity.get("chat_session_id")
        if chat_session_id:
            return str(chat_session_id)
        subject = identity.get("sub")
        return str(subject) if subject else None

    async def _resolve_session(
        self, tool_name: str, identity: dict, risk_level: str
    ) -> tuple[BrowserSessionEntry | None, ToolResult | None]:
        """Shared front door: identity key + pool readiness + session get."""
        session_key = self._session_key(identity)
        if not session_key:
            return None, make_error_result(
                tool_name, "BROWSER_NO_IDENTITY",
                "No verified caller identity is available for a browser "
                "session.", risk_level=risk_level, source_system=SOURCE_SYSTEM,
            )
        try:
            entry = await self.pool.get_or_create(session_key)
        except BrowserNotReady as exc:
            return None, make_error_result(
                tool_name, "BROWSER_NOT_READY", str(exc),
                risk_level=risk_level, source_system=SOURCE_SYSTEM,
            )
        return entry, None

    async def fetch_skill(self, skill_id: str) -> tuple[dict | None, str, str]:
        """Fetch one skill from skills-hub for flow validation (R-4).

        Returns ``(record, error_code, error_message)``; the record is
        None on any failure and the caller surfaces the structured error.
        """
        if not self._skills_url:
            return None, "SKILLS_NOT_CONFIGURED", (
                "Flow binding needs the skills connector "
                "(GATEWAY_SKILLS_SERVICE_URL) to validate the skill "
                "declaration."
            )
        if not _SKILL_ID_PATTERN.match(skill_id):
            return None, "INVALID_PARAMETERS", (
                "Parameter 'skill_id' is not a valid namespaced skill id."
            )
        path = SKILL_PATH_TEMPLATE.format(skill_id=skill_id)
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    f"{self._skills_url.rstrip('/')}{path}",
                    auth=(self._skills_client_id, self._skills_client_secret),
                )
        except httpx.HTTPError as exc:
            LOGGER.warning("skill lookup transport error: %s", exc)
            return None, "SKILLS_UNAVAILABLE", "skills-hub is unreachable."
        if response.status_code == 404:
            return None, "SKILL_NOT_FOUND", (
                f"Skill '{skill_id}' was not found in the skills hub."
            )
        if response.status_code != 200:
            return None, "SKILLS_UNAVAILABLE", (
                f"skills-hub returned HTTP {response.status_code}."
            )
        payload = response.json()
        return (payload if isinstance(payload, dict) else None), "", ""

    def bind_flow(
        self, entry: BrowserSessionEntry, skill_id: str, url: str, skill: dict
    ) -> ToolResult | None:
        """Validate the declaration and bind the flow; error result or None.

        The navigated URL must land on the declared ``web_target``'s
        origin and on (or under) its path; the declared ``risk_class``
        defaults to ``read`` when absent.
        """
        web_target = skill.get("web_target")
        if not web_target:
            return make_error_result(
                "web.navigate", "SKILL_NOT_WEB_FLOW",
                f"Skill '{skill_id}' does not declare a web_target and "
                "cannot bind a browser flow.",
                source_system=SOURCE_SYSTEM,
            )
        risk_class = skill.get("risk_class") or "read"
        target_origin = origin_of(str(web_target))
        url_origin = origin_of(url)
        if (
            target_origin is None
            or url_origin != target_origin
            or not _path_under(
                urlparse(url).path, urlparse(str(web_target)).path
            )
        ):
            return _denied(
                "web.navigate", "BROWSER_FLOW_TARGET_MISMATCH",
                f"URL '{url}' does not match skill '{skill_id}' declared "
                f"web_target '{web_target}'.", "read",
            )
        entry.flow = FlowState(
            skill_id=skill_id,
            origin=url_origin,
            risk_class=risk_class,
            max_steps=self._flow_max_steps,
            approved=(risk_class == "read"),
        )
        entry.reset_page_state()
        return None

    def gate_interaction(
        self, entry: BrowserSessionEntry, tool_name: str, require_write_class: bool
    ) -> ToolResult | None:
        """Deviation guard (R-4): an interaction never executes silently.

        Returns a denial result when the flow is absent, read-only but
        asked for a write-tier action, denied, or exhausted; None when the
        interaction may proceed. Write-tier calls additionally pass the
        SPEC-020/037 gate upstream before they ever reach this check.
        """
        risk_level = "write" if require_write_class else "read"
        flow = entry.flow
        if flow is None:
            return _denied(
                tool_name, "BROWSER_FLOW_NOT_BOUND",
                "No web-check flow is bound to this browser session; "
                "navigate to a skill's declared web_target first.",
                risk_level,
            )
        if flow.denied:
            return _denied(
                tool_name, "BROWSER_FLOW_DENIED",
                "The bound web-check flow was denied; further interactions "
                "are refused.", risk_level,
            )
        # R-4 deviation guard: the interaction must land on the origin the
        # flow was bound to (and the operator approved). A plain navigate to
        # another allowlisted origin leaves the flow bound, so re-check the
        # live page origin here — an off-origin interaction is refused, never
        # run under an approval that named a different target.
        current_origin = origin_of(entry.page.url)
        if current_origin is None or current_origin != flow.origin:
            return _denied(
                tool_name, "BROWSER_FLOW_ORIGIN_DEVIATED",
                "The current page origin does not match the bound flow's "
                f"approved origin '{flow.origin}'; the interaction is "
                "refused. Navigate back to the flow's target first.",
                risk_level,
            )
        if require_write_class and flow.risk_class != "write":
            return _denied(
                tool_name, "BROWSER_FLOW_READ_ONLY",
                f"The bound flow declares risk_class 'read'; write-tier "
                "interactions are refused.", risk_level,
            )
        if flow.steps_used >= flow.max_steps:
            return _denied(
                tool_name, "BROWSER_FLOW_EXHAUSTED",
                f"The bound flow exceeded its step budget "
                f"({flow.max_steps} steps); further interactions are "
                "refused.", risk_level,
            )
        return None

    async def gate_capture(
        self, entry: BrowserSessionEntry, tool_name: str
    ) -> ToolResult | None:
        """Read-tier origin re-check (R-2/R-4): a snapshot/screenshot never
        captures a page that drifted off the allowlist or off the bound
        flow's origin.

        ``web.navigate`` re-checks the landing origin at goto time, but a
        post-load client-side redirect is not otherwise caught before the
        next navigate — so the read tier re-validates the live origin here,
        the mirror of the write-tier deviation guard (``gate_interaction``).
        An off-allowlist page is halted (as the navigate redirect guard
        does) and refused; an off-flow but allowlisted page is refused
        without a halt. Returns None when the capture may proceed.
        """
        live_url = entry.page.url
        if not self.is_origin_allowed(live_url):
            offending = origin_of(live_url) or live_url
            try:
                await entry.page.goto("about:blank")
            except Exception:  # noqa: BLE001 - halt is best effort
                pass
            entry.reset_page_state()
            entry.flow = None
            return make_error_result(
                tool_name, "BROWSER_REDIRECT_NOT_ALLOWED",
                f"The current page ('{offending}') is not on the browser "
                "origin allowlist; the page was halted and the capture "
                "refused. Navigate to an allowed target first.",
                risk_level="read", source_system=SOURCE_SYSTEM,
            )
        flow = entry.flow
        if flow is not None and origin_of(live_url) != flow.origin:
            return _denied(
                tool_name, "BROWSER_FLOW_ORIGIN_DEVIATED",
                "The current page origin does not match the bound flow's "
                f"approved origin '{flow.origin}'; the capture is refused. "
                "Navigate back to the flow's target first.",
                "read",
            )
        return None


def _invalid_ref(tool_name: str, ref: object) -> ToolResult:
    return make_error_result(
        tool_name, "BROWSER_REF_UNKNOWN",
        f"Parameter 'ref' must be a snapshot element reference (1-based "
        f"integer), got {ref!r}. Take a web.snapshot to obtain refs.",
        risk_level="write", source_system=SOURCE_SYSTEM,
    )


def _resolve_ref(
    entry: BrowserSessionEntry, tool_name: str, ref: object
) -> tuple[object | None, ToolResult | None]:
    try:
        index = int(ref)
    except (TypeError, ValueError):
        return None, _invalid_ref(tool_name, ref)
    if index < 1 or index > len(entry.refs):
        return None, make_error_result(
            tool_name, "BROWSER_REF_UNKNOWN",
            f"Snapshot ref {index} is not valid for the current page; take "
            "a fresh web.snapshot.", risk_level="write",
            source_system=SOURCE_SYSTEM,
        )
    return entry.refs[index - 1], None


# --- Tool implementations ---


class WebNavigateTool(BaseTool):
    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.navigate",
            description=(
                "Open a URL in the session's browser and wait for load. "
                "Targets must be on the platform's origin allowlist. Pass "
                "the skill_id of a web-check skill to bind its declared "
                "flow (web_target/risk_class) to the session."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute http(s) URL to open.",
                    },
                    "skill_id": {
                        "type": "string",
                        "description": (
                            "Namespaced skill id declaring this web-check "
                            "flow (web_target/risk_class frontmatter)."
                        ),
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        connector = self._connector
        url = parameters.get("url")
        if not isinstance(url, str) or origin_of(url) is None:
            return make_error_result(
                "web.navigate", "INVALID_PARAMETERS",
                "Parameter 'url' must be an absolute http(s) URL.",
                source_system=SOURCE_SYSTEM,
            )
        # R-2: server-side allowlist check before any navigation.
        if not connector.is_origin_allowed(url):
            return _denied(
                "web.navigate", "BROWSER_ORIGIN_NOT_ALLOWED",
                f"Origin '{origin_of(url)}' is not on the browser origin "
                "allowlist.", "read",
            )

        entry, error = await connector._resolve_session(
            "web.navigate", identity, "read"
        )
        if error is not None:
            return error
        assert entry is not None

        # R-4: flow binding validates the skill declaration upstream of
        # any page interaction.
        skill_id = parameters.get("skill_id")
        bound_here = False
        if skill_id is not None:
            skill, code, message = await connector.fetch_skill(str(skill_id))
            if skill is None:
                return make_error_result(
                    "web.navigate", code, message, source_system=SOURCE_SYSTEM,
                )
            bind_error = connector.bind_flow(entry, str(skill_id), url, skill)
            if bind_error is not None:
                return bind_error
            bound_here = True

        try:
            await entry.page.goto(
                url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("web.navigate failed: %s", exc)
            if bound_here:
                # The flow bound on this call never reached its target; drop
                # it so a stale binding can't be interacted with (R-4). A
                # pre-existing flow is left intact — the page did not move.
                entry.flow = None
                entry.reset_page_state()
            return make_error_result(
                "web.navigate", "BROWSER_NAVIGATION_ERROR", str(exc),
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)

        # R-2: redirect coverage — the landing origin is re-checked.
        final_url = entry.page.url
        if not connector.is_origin_allowed(final_url):
            offending = origin_of(final_url) or final_url
            try:
                await entry.page.goto("about:blank")
            except Exception:  # noqa: BLE001 - halt is best effort
                pass
            entry.reset_page_state()
            entry.flow = None
            return make_error_result(
                "web.navigate", "BROWSER_REDIRECT_NOT_ALLOWED",
                f"Navigation landed outside the allowlist on origin "
                f"'{offending}'; the session page was halted.",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )

        entry.reset_page_state()
        data: dict = {"url": final_url, "title": await entry.page.title()}
        if entry.flow is not None:
            data["flow"] = entry.flow.to_dict()
        return ToolResult(
            tool_name="web.navigate",
            status="success",
            data=data,
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


class WebSnapshotTool(BaseTool):
    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.snapshot",
            description=(
                "Return a bounded text snapshot of the current page with "
                "interactive elements enumerated as refs (1-based) usable "
                "by web.click / web.type / web.fill_credential."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={"type": "object", "properties": {}},
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        connector = self._connector
        entry, error = await connector._resolve_session(
            "web.snapshot", identity, "read"
        )
        if error is not None:
            return error
        assert entry is not None
        # C-2: re-check the live origin before capturing. A post-load
        # client-side redirect could otherwise produce a snapshot of a
        # page that drifted off the allowlist or off the bound flow.
        gate = await connector.gate_capture(entry, "web.snapshot")
        if gate is not None:
            return gate
        try:
            snapshot_text, count = await _build_snapshot(entry)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("web.snapshot failed: %s", exc)
            return make_error_result(
                "web.snapshot", "BROWSER_SNAPSHOT_ERROR", str(exc),
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ToolResult(
            tool_name="web.snapshot",
            status="success",
            data={
                "url": entry.page.url,
                "title": await entry.page.title(),
                "elements": count,
                "snapshot": snapshot_text,
            },
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


async def _build_snapshot(entry: BrowserSessionEntry) -> tuple[str, int]:
    """Enumerate interactive elements into addressable, masked refs (R-5)."""
    elements = await entry.page.query_selector_all(INTERACTIVE_SELECTOR)
    elements = elements[:MAX_SNAPSHOT_ELEMENTS]
    entry.refs = elements
    lines = [f"URL: {entry.page.url}", ""]
    for index, element in enumerate(elements, start=1):
        info = await element.evaluate(_ELEMENT_INSPECT_JS)
        if not isinstance(info, dict):
            info = {}
        label = info.get("name") or info.get("text") or ""
        bits = [str(info.get("tag", "element")).lower()]
        elem_type = str(info.get("type") or "").lower()
        if elem_type:
            bits.append(f"type={elem_type}")
        if info.get("role"):
            bits.append(f"role={info['role']}")
        line = f"[{index}] <{' '.join(bits)}>"
        if label:
            line += f' "{label}"'
        value = info.get("value") or ""
        if value:
            # R-5: filled credential values (and any password field) are
            # masked in every downstream representation.
            masked = (
                elem_type == "password" or value in entry.filled_values
            )
            line += f" value={'***' if masked else repr(value)}"
        if info.get("disabled"):
            line += " (disabled)"
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > SNAPSHOT_MAX_CHARS:
        text = text[:SNAPSHOT_MAX_CHARS] + "\n[truncated]"
    return text, len(elements)


class WebScreenshotTool(BaseTool):
    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.screenshot",
            description=(
                "Capture a bounded JPEG screenshot of the current page, "
                "returned base64-encoded beside the page title and URL."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={"type": "object", "properties": {}},
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        connector = self._connector
        entry, error = await connector._resolve_session(
            "web.screenshot", identity, "read"
        )
        if error is not None:
            return error
        assert entry is not None
        # C-2: re-check the live origin before capturing.
        gate = await connector.gate_capture(entry, "web.screenshot")
        if gate is not None:
            return gate
        try:
            raw = await _capture_screenshot(
                entry.page, connector._screenshot_max_bytes,
                frozenset(entry.secret_values),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("web.screenshot failed: %s", exc)
            return make_error_result(
                "web.screenshot", "BROWSER_SCREENSHOT_ERROR", str(exc),
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        duration_ms = int((time.perf_counter() - start) * 1000)
        if raw is None:
            return make_error_result(
                "web.screenshot", "BROWSER_SCREENSHOT_TOO_LARGE",
                "The screenshot could not be compressed within the byte "
                "cap.", source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        return ToolResult(
            tool_name="web.screenshot",
            status="success",
            data={
                "title": await entry.page.title(),
                "url": entry.page.url,
                "format": "jpeg",
                "bytes": len(raw),
                "screenshot": base64.b64encode(raw).decode("ascii"),
            },
            evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
        )


async def _capture_screenshot(
    page, max_bytes: int, secret_values: frozenset[str] = frozenset()
) -> bytes | None:
    """JPEG under the byte cap: quality loop, then shrinking clip (R-6).

    Password-tier credential values are masked out of the capture first
    (R-5). Masking is fail-closed: if the mask injection raises, the
    exception propagates and no screenshot is taken rather than risk
    leaking a plaintext password a legacy ``type=text`` field rendered.
    """
    masked = False
    if secret_values:
        masked = bool(
            await page.evaluate(_SCREENSHOT_MASK_JS, list(secret_values))
        )
    try:
        raw = b""
        for quality in SCREENSHOT_QUALITIES:
            raw = await page.screenshot(type="jpeg", quality=quality)
            if len(raw) <= max_bytes:
                return raw
        viewport = getattr(page, "viewport_size", None) or {}
        width, height = viewport.get("width", 0), viewport.get("height", 0)
        if width and height:
            for fraction in SCREENSHOT_CLIP_FRACTIONS:
                clip = {
                    "x": 0,
                    "y": 0,
                    "width": int(width * fraction),
                    "height": int(height * fraction),
                }
                raw = await page.screenshot(type="jpeg", quality=40, clip=clip)
                if len(raw) <= max_bytes:
                    return raw
        return raw if len(raw) <= max_bytes else None
    finally:
        if masked:
            try:
                await page.evaluate(_SCREENSHOT_UNMASK_JS)
            except Exception as exc:  # noqa: BLE001 - unmask is best effort
                # The secret stays masked (fail-safe) but the page keeps its
                # dot mask; log the class only (never a value) so a stuck
                # mask is visible.
                LOGGER.warning(
                    "screenshot credential unmask failed: %s",
                    exc.__class__.__name__,
                )


class _WebInteractionTool(BaseTool):
    """Shared plumbing for ref-addressed interaction tools."""

    tool_name = ""
    risk_level = "read"

    def __init__(self, connector: BrowserConnector) -> None:
        self._connector = connector

    async def _guarded_handle(
        self, entry: BrowserSessionEntry, parameters: dict
    ) -> tuple[object | None, ToolResult | None]:
        """Deviation guard first, then ref resolution."""
        gate = self._connector.gate_interaction(
            entry, self.tool_name, require_write_class=(self.risk_level == "write")
        )
        if gate is not None:
            return None, gate
        return _resolve_ref(entry, self.tool_name, parameters.get("ref"))

    def _step_result(
        self, entry: BrowserSessionEntry, start: float, extra: dict | None = None
    ) -> ToolResult:
        flow = entry.flow
        assert flow is not None  # guaranteed by the deviation guard
        flow.steps_used += 1
        flow.approved = True
        duration_ms = int((time.perf_counter() - start) * 1000)
        data = {
            "url": entry.page.url,
            "steps_used": flow.steps_used,
            "steps_budget": flow.max_steps,
        }
        if extra:
            data.update(extra)
        return ToolResult(
            tool_name=self.tool_name,
            status="success",
            data=data,
            evidence=build_evidence(self.risk_level, SOURCE_SYSTEM, duration_ms),
        )


class WebClickTool(_WebInteractionTool):
    tool_name = "web.click"
    risk_level = "write"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.click",
            description=(
                "Click the element identified by a web.snapshot ref inside "
                "a bound, approved write-class web-check flow. This is a "
                "mutating action on the target application and requires "
                "operator confirmation."
            ),
            risk_level="write",
            category=CATEGORY,
            parameters_schema={
                "type": "object",
                "required": ["ref"],
                "properties": {
                    "ref": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Element ref from the latest web.snapshot.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        entry, error = await self._connector._resolve_session(
            self.tool_name, identity, "write"
        )
        if error is not None:
            return error
        assert entry is not None
        handle, guard = await self._guarded_handle(entry, parameters)
        if guard is not None:
            return guard
        try:
            await handle.click()
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("web.click failed: %s", exc)
            return make_error_result(
                self.tool_name, "BROWSER_ACTION_ERROR", str(exc),
                risk_level="write", source_system=SOURCE_SYSTEM,
                duration_ms=duration_ms,
            )
        return self._step_result(entry, start)


class WebTypeTool(_WebInteractionTool):
    tool_name = "web.type"
    risk_level = "write"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.type",
            description=(
                "Type text into the element identified by a web.snapshot "
                "ref inside a bound, approved write-class web-check flow. "
                "This is a mutating action on the target application and "
                "requires operator confirmation. Never type credentials "
                "with this tool — use web.fill_credential."
            ),
            risk_level="write",
            category=CATEGORY,
            parameters_schema={
                "type": "object",
                "required": ["ref", "text"],
                "properties": {
                    "ref": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Element ref from the latest web.snapshot.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type into the element.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        entry, error = await self._connector._resolve_session(
            self.tool_name, identity, "write"
        )
        if error is not None:
            return error
        assert entry is not None
        text = parameters.get("text")
        if not isinstance(text, str):
            return make_error_result(
                self.tool_name, "INVALID_PARAMETERS",
                "Parameter 'text' must be a string.",
                risk_level="write", source_system=SOURCE_SYSTEM,
            )
        handle, guard = await self._guarded_handle(entry, parameters)
        if guard is not None:
            return guard
        try:
            await handle.fill(text)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("web.type failed: %s", exc)
            return make_error_result(
                self.tool_name, "BROWSER_ACTION_ERROR", str(exc),
                risk_level="write", source_system=SOURCE_SYSTEM,
                duration_ms=duration_ms,
            )
        return self._step_result(entry, start)


class WebFillCredentialTool(_WebInteractionTool):
    """Fill a login field from a named credential set (R-5, read tier).

    Read tier by design (D-3): filling a form field submits nothing; the
    write-class flow's gate lands on the submitting interaction. The
    credential value only ever flows into the Playwright fill call — it
    never appears in results, snapshots, evidence, or logs.
    """

    tool_name = "web.fill_credential"
    risk_level = "read"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web.fill_credential",
            description=(
                "Fill a username or password field (web.snapshot ref) from "
                "a platform-managed named credential set inside a bound "
                "web-check flow. Credentials are never part of skills or "
                "tool outputs."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={
                "type": "object",
                "required": ["ref", "credential_set", "field"],
                "properties": {
                    "ref": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Element ref from the latest web.snapshot.",
                    },
                    "credential_set": {
                        "type": "string",
                        "description": "Name of the configured credential set.",
                    },
                    "field": {
                        "type": "string",
                        "enum": list(CREDENTIAL_FIELDS),
                        "description": "Which credential value to fill.",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        connector = self._connector
        entry, error = await connector._resolve_session(
            self.tool_name, identity, "read"
        )
        if error is not None:
            return error
        assert entry is not None

        set_name = parameters.get("credential_set")
        field = parameters.get("field")
        if not isinstance(set_name, str) or not set_name:
            return make_error_result(
                self.tool_name, "INVALID_PARAMETERS",
                "Parameter 'credential_set' is required.",
                source_system=SOURCE_SYSTEM,
            )
        if field not in CREDENTIAL_FIELDS:
            return make_error_result(
                self.tool_name, "INVALID_PARAMETERS",
                "Parameter 'field' must be one of: "
                + ", ".join(CREDENTIAL_FIELDS) + ".",
                source_system=SOURCE_SYSTEM,
            )
        credential = connector.credentials.get(set_name)
        if credential is None:
            # W-3: do not enumerate available set names to the model — the
            # list is an information disclosure that lets the model probe
            # which sets exist. A generic message is sufficient.
            return make_error_result(
                self.tool_name, "CREDENTIAL_SET_NOT_FOUND",
                f"Credential set '{set_name}' is not configured.",
                source_system=SOURCE_SYSTEM,
            )

        handle, guard = await self._guarded_handle(entry, parameters)
        if guard is not None:
            return guard
        value = credential[field]
        try:
            await handle.fill(value)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            # Log the exception class only: messages can echo input state
            # and must never leak the credential value.
            LOGGER.warning(
                "web.fill_credential failed: %s", exc.__class__.__name__
            )
            return make_error_result(
                self.tool_name, "BROWSER_ACTION_ERROR",
                "Filling the credential field failed.",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        entry.filled_values.add(value)
        if field == "password":
            # Track the password separately so screenshots can mask it even
            # when a legacy target renders it into a non-password field.
            entry.secret_values.add(value)
        return self._step_result(
            entry, start, {"filled": field, "credential_set": set_name}
        )
