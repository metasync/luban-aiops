"""Pending kernel confirmations for HITL bridging (SPEC-020 R-2).

When the AgentScope kernel parks a reply on an ``ASK`` permission decision
(``RequireUserConfirmEvent``), the runtime registers the parked tool calls
here and surfaces a ``confirmation_request`` frame on the SSE stream. The
confirm endpoint later resolves the entry and resumes the parked reply.

The registry is deliberately in-memory and per-process: a parked
confirmation never survives a restart — after an agent rebuild the entry is
simply gone and any confirm attempt fails closed (404/410), never
auto-running a parked tool call.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field


class ConfirmationNotFound(LookupError):
    """No pending confirmation matches the session/confirm_id pair."""


class ConfirmationExpired(LookupError):
    """The pending confirmation exceeded its time-to-live."""


# Policy action a parked call maps to, derived from its risk tier snapshot
# (SPEC-030 R-3): the platform-gateway confirm bridge evaluates this action
# against the policy bundle. Tools without a gateway risk tier carry no
# action and stay on the implicit no-rule path.
RISK_LEVEL_ACTIONS = {
    "read": "tools:invoke",
    "write": "tools:mutate",
    "admin": "tools:mutate",
}


@dataclass
class PendingConfirmation:
    confirm_id: str
    session_id: str
    user_id: str
    reply_id: str
    # Kernel ToolCallBlock instances, held opaquely until resume feeds them
    # back into ``reply_stream`` — no agentscope types leak past this module.
    tool_calls: list = field(default_factory=list)
    # Sanitized tool name -> risk tier snapshot taken at park time (SPEC-021
    # R-3); entries exist only for gateway tools with a known risk level and
    # ride the confirmation_request/confirmation_result frames so the portal
    # can flag mutating batches.
    risk_levels: dict = field(default_factory=dict)
    # Sanitized tool name -> dotted gateway canonical name, captured at park
    # time from the toolkit. Parked tool calls carry the model-visible
    # sanitized name (dots become underscores), but the signed execution
    # envelope and the worker's gateway invocation need the canonical name
    # the registry knows — without this map an approved mutating call fails
    # closed with TOOL_NOT_FOUND at the gateway.
    gateway_names: dict = field(default_factory=dict)
    # Browser element map from the last web.snapshot (SPEC-050 follow-up):
    # maps ref numbers to human-readable element descriptions so confirmation
    # cards show what element will be clicked/typed into, not just the raw ref.
    browser_element_map: dict[int, str] = field(default_factory=dict)
    # Flow-semantic card headline (SPEC-051 R-6): the bound browser flow's
    # summary (skill_id, origin, title, description, risk_class) captured from
    # the kernel's session-scoped FlowContext at park time. Empty when no flow
    # is bound (a per-action confirmation), so the card falls back to today's
    # tool-level rendering. Also the source of the approved flow identity that
    # ``resume_confirmation`` scopes the FlowApproval to (R-1).
    browser_flow: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    resolved: bool = False
    # Single-flight guard set by ``claim`` before a decision streams back:
    # a claimed entry is invisible to further confirms but keeps the
    # session parked (409) until ``resolve`` runs.
    claimed: bool = False

    def is_expired(self, timeout: float) -> bool:
        return timeout > 0 and (time.monotonic() - self.created_at) > timeout

    def pending_calls_payload(self) -> list[dict]:
        """Serialize the parked calls for the confirmation_request frame."""
        # Browser interaction tools that reference snapshot elements.
        browser_ref_tools = {
            "web.click", "web.type", "web.select",
            "web.press_key", "web.upload_file",
        }
        payload = []
        for tool_call in self.tool_calls:
            sanitized = str(getattr(tool_call, "name", "") or "")
            # Emit the gateway canonical name so confirmation cards, durable
            # records, audit events, and the signed execution envelope all
            # agree on the name the registry resolves.
            tool_name = self.gateway_names.get(sanitized, sanitized)
            parameters = _parse_parameters(tool_call)
            entry = {
                "call_id": str(getattr(tool_call, "id", "") or ""),
                "tool_name": tool_name,
                "parameters": parameters,
            }
            # SPEC-050 follow-up: add a display hint for browser tools that
            # reference snapshot elements. This is separate from parameters
            # so the args_digest for signing/verification stays unchanged.
            if tool_name in browser_ref_tools and self.browser_element_map:
                ref = parameters.get("ref")
                if isinstance(ref, int) and ref in self.browser_element_map:
                    entry["display_hint"] = self.browser_element_map[ref]
            risk_level = self.risk_levels.get(sanitized)
            if risk_level:
                entry["risk_level"] = risk_level
                action = RISK_LEVEL_ACTIONS.get(risk_level)
                if action:
                    entry["action"] = action
            payload.append(entry)
        return payload

    def highest_action(self) -> str | None:
        """The strictest policy action in the parked batch (SPEC-030 R-3).

        ``tools:mutate`` wins over ``tools:invoke``; ``None`` means no call
        carries a gateway risk tier (task tools), which the confirm bridge
        treats as the implicit no-rule path.
        """
        actions = {
            action
            for risk_level in self.risk_levels.values()
            if (action := RISK_LEVEL_ACTIONS.get(risk_level))
        }
        if "tools:mutate" in actions:
            return "tools:mutate"
        if "tools:invoke" in actions:
            return "tools:invoke"
        return None

    def tool_names(self) -> list[str]:
        return [
            str(getattr(tool_call, "name", "") or "")
            for tool_call in self.tool_calls
        ]

    def flow_summary(self) -> dict | None:
        """The card-level flow headline payload (SPEC-051 R-6), or ``None``.

        Present only when a browser flow is bound to this confirmation, so the
        portal renders the workflow headline above the per-call tool detail and
        falls back to tool-level rendering otherwise. Carries the approved flow
        identity (``skill_id``/``origin``) that ``resume_confirmation`` scopes
        the flow authority to (R-1).
        """
        return dict(self.browser_flow) if self.browser_flow else None


def _parse_parameters(tool_call) -> dict:
    """Parse a tool call's raw JSON input into a parameters dict."""
    raw = getattr(tool_call, "input", "") or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_snapshot_elements(snapshot_text: str) -> dict[int, str]:
    """Parse a web.snapshot text into a ref -> element description map.

    The snapshot format is ``[ref] <tag type=... role=...> "label"``.
    This extracts the ref number and a human-readable description for
    use in confirmation cards (SPEC-050 follow-up: show what element
    will be clicked, not just the raw ref number).
    """
    elements: dict[int, str] = {}
    for line in snapshot_text.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            bracket_end = line.index("]")
            ref = int(line[1:bracket_end])
        except (ValueError, IndexError):
            continue
        # Extract the element description after the ref
        rest = line[bracket_end + 1:].strip()
        # Format: <tag type=... role=...> "label"
        # We want to show: tag + label (if present)
        description = rest
        # Try to extract the label in quotes
        if '"' in rest:
            try:
                label_start = rest.index('"')
                label_end = rest.rindex('"')
                if label_start < label_end:
                    label = rest[label_start + 1:label_end]
                    # Extract the tag part
                    tag_end = rest.index(">")
                    tag_part = rest[:tag_end + 1]
                    description = f"{tag_part} \"{label}\""
            except ValueError:
                pass
        elements[ref] = description
    return elements


class ConfirmationRegistry:
    """Per-process map of session_id -> pending confirmation.

    At most one confirmation may be parked per session; new chat turns on a
    parked session are rejected upstream (409) rather than forking state.
    Expiry never silently evicts: a TTL breach is always closed through the
    kernel's ``expire_confirmation`` (``UserInterruptEvent``) so the parked
    reply cannot wedge the agent. Both ``claim`` (decision path) and
    ``take_for_expiry`` (cleanup path) set the same single-flight flag, so
    one parked batch is never resumed twice and an in-flight resume is
    never interrupted by a racing expiry.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, PendingConfirmation] = {}

    def register(
        self,
        session_id: str,
        user_id: str,
        reply_id: str,
        tool_calls: list,
        timeout: float,
        risk_levels: dict | None = None,
        gateway_names: dict | None = None,
        browser_element_map: dict[int, str] | None = None,
        browser_flow: dict | None = None,
    ) -> PendingConfirmation:
        pending = PendingConfirmation(
            confirm_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            reply_id=reply_id,
            tool_calls=list(tool_calls),
            risk_levels=dict(risk_levels or {}),
            gateway_names=dict(gateway_names or {}),
            browser_element_map=dict(browser_element_map or {}),
            browser_flow=dict(browser_flow or {}),
        )
        self._by_session[session_id] = pending
        return pending

    def get(
        self, session_id: str, confirm_id: str, timeout: float
    ) -> PendingConfirmation:
        """Return the matching unclaimed, unresolved entry or raise.

        ``ConfirmationNotFound`` covers unknown, claimed, resolved, and
        foreign confirm_ids alike; ``ConfirmationExpired`` marks a TTL
        breach so the caller can close the parked calls and 410. Expired
        entries are never silently evicted — expiry stays observable until
        ``expire_confirmation`` interrupts the parked reply and resolves
        the entry.
        """
        pending = self._by_session.get(session_id)
        if (
            pending is None
            or pending.confirm_id != confirm_id
            or pending.resolved
            or pending.claimed
        ):
            raise ConfirmationNotFound(confirm_id)
        if pending.is_expired(timeout):
            raise ConfirmationExpired(confirm_id)
        return pending

    def claim(
        self, session_id: str, confirm_id: str, timeout: float
    ) -> PendingConfirmation:
        """Atomically take exclusive ownership of a decision.

        Runs before any response headers go out, so a duplicate confirm
        (retry, second tab, second operator) fails closed with
        ``ConfirmationNotFound`` instead of double-resuming the parked
        batch. The entry stays registered (and ``is_parked`` stays true)
        until ``resolve`` so new chat turns keep 409-ing during the
        resumed stream.
        """
        pending = self.get(session_id, confirm_id, timeout)
        pending.claimed = True
        return pending

    def take_for_expiry(
        self, session_id: str, confirm_id: str
    ) -> PendingConfirmation:
        """Atomically claim an unresolved entry for expiry closure.

        The expiry path must reach an expired entry regardless of TTL (a
        plain ``get`` would raise before the cleanup could run), but it
        still honors the single-flight flag: a claimed entry is owned by
        a decision resume — or a concurrent expiry — whose ``finally``
        will resolve it, so interrupting it here could abort a resume
        that is already streaming. The flag is set synchronously before
        returning, so two concurrent expirers can never both interrupt.
        """
        pending = self._by_session.get(session_id)
        if (
            pending is None
            or pending.confirm_id != confirm_id
            or pending.resolved
            or pending.claimed
        ):
            raise ConfirmationNotFound(confirm_id)
        pending.claimed = True
        return pending

    def peek_parked(self, session_id: str) -> PendingConfirmation | None:
        """Return the session's unresolved entry regardless of TTL.

        Lets the chat routes distinguish "parked" (409) from "parked but
        expired" (close via ``expire_confirmation``, then let the turn
        proceed) without silently evicting anything.
        """
        pending = self._by_session.get(session_id)
        if pending is not None and not pending.resolved:
            return pending
        return None

    def resolve(self, session_id: str, confirm_id: str) -> None:
        pending = self._by_session.get(session_id)
        if pending is not None and pending.confirm_id == confirm_id:
            pending.resolved = True
            del self._by_session[session_id]

    def is_parked(self, session_id: str, timeout: float) -> bool:
        return self.has_pending(session_id)

    def has_pending(self, session_id: str) -> bool:
        """True when the session holds an unresolved parked confirmation.

        TTL-agnostic on purpose: an expired park still awaits closure via
        the confirm endpoint, so the session API (SPEC-022 R-1) must keep
        badging it until a decision or ``expire_confirmation`` resolves it.
        """
        pending = self._by_session.get(session_id)
        return pending is not None and not pending.resolved


# Process-wide singleton shared by the runtime kernel and the v2 routes.
# Tests may clear it between cases; production code never replaces it.
CONFIRMATION_REGISTRY = ConfirmationRegistry()
