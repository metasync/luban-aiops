"""Toolkit assembly and role narrowing for the AgentKernel (decomposition Stage 1).

``ToolkitAssembler`` owns the per-token toolkit cache and the discovery →
HITL-filter → read-only-filter → role-narrow pipeline that was
``AgentKernel._ensure_toolkit`` and its helpers. ``_ensure_toolkit`` is already
the seam the specs name (SPEC-073/076 narrow "at the
``_ensure_toolkit(read_only=True)`` seam"), so this formalizes a boundary the
specs already talk about.

``AgentKernel`` keeps a thin delegator for every method here
(``_ensure_toolkit``, ``_filter_mutating_for_hitl``, ``_filter_read_only``,
``_narrow_for_role``, ``_build_task_tools``, ``_count_gateway_tools``) plus a
read-through ``_mutating_tools_excluded`` property, so every caller and test is
unchanged. Method bodies are extracted verbatim from ``runtime_kernel.
AgentKernel`` (behavior byte-identical); see
``docs/workspace/agent-kernel-decomposition-spike.md``.
"""

import asyncio
import logging

from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.agent_role import AgentRole, current_agent_role

LOGGER = logging.getLogger(__name__)


class ToolkitAssembler:
    """The kernel's toolkit assembly / narrowing collaborator.

    Holds a back-reference to the owning ``AgentKernel`` and reads ``settings``
    *live* through it (never a captured snapshot), so a later
    ``kernel.settings = ...`` reassignment is observed exactly as the
    pre-extraction methods did. The per-token toolkit cache, its build lock, and
    the SPEC-021 mutating-excluded posture flag are owned here.
    """

    def __init__(self, kernel) -> None:
        self._kernel = kernel
        # Per-token toolkit cache (SPEC-008 R-5): a toolkit is built per owning
        # user's delegated token so discovery runs once per token. Tool
        # closures read the current token from the DELEGATED_TOKEN contextvar
        # at call time (SPEC-018 R-2), so cached toolkits keep working across
        # portal token refresh.
        self._toolkits: dict[str, object] = {}
        self._toolkit_lock = asyncio.Lock()
        # SPEC-021 R-3: set when a toolkit build excluded mutating tools
        # because HITL bridging is disabled, so streamed turns surface the
        # mutating-unavailable posture honestly.
        self._mutating_tools_excluded = False

    @property
    def settings(self) -> RuntimeSettings:
        return self._kernel.settings

    async def ensure_toolkit(
        self, bearer_token: str | None = None, read_only: bool = False
    ):
        """Build (once per token) and return the Toolkit with gateway tools.

        Toolkits are cached per delegated token so discovery runs once per
        token; tool closures read the current token from ``DELEGATED_TOKEN``
        at call time, so a cached toolkit keeps working across portal token
        refresh (SPEC-018 R-2). Empty discovery results are intentionally NOT
        cached: the next caller retries discovery instead of being poisoned.

        ``read_only`` selects a separate cache entry whose toolkit is
        restricted to read-level tools (automated diagnostic turns).

        A bound ``AGENT_ROLE`` (SPEC-073 R-2) selects a further separate cache
        entry whose toolkit is narrowed per role — subtractive only, never
        wider than the unscoped toolkit for the same token. An unscoped turn
        (no role bound — the only case in phase 2, which wires no orchestration
        caller) keeps today's exact key and one cache entry, byte-identical.
        """
        # SPEC-073 R-2: a bound agent-role joins the cache key so a role-scoped
        # toolkit never leaks into an unscoped (or differently-scoped) turn,
        # mirroring ``read_only``. Read once so the key and the narrowing below
        # agree across the discovery await.
        role = current_agent_role()
        cache_key = (bearer_token or "") + ("::read-only" if read_only else "")
        if role is not None:
            cache_key = f"{cache_key}::{role.value}"
        cached = self._toolkits.get(cache_key)
        if cached is not None:
            return cached

        from agentscope.tool import Toolkit

        async with self._toolkit_lock:
            # Re-check: a concurrent caller may have built it while we waited.
            cached = self._toolkits.get(cache_key)
            if cached is not None:
                return cached

            task_tools = (
                self.build_task_tools()
                if self.settings.task_tools_enabled
                else []
            )
            # SPEC-080 R-5: admit the read-only ``AskUser`` external tool only
            # behind the default-off flag. Builtins ride the same bucket as the
            # task tools — added to the toolkit directly, never through the
            # discovered-gateway-definition filters (``AskUser`` is read-only +
            # always-ALLOW, so it needs no HITL / read-only / role narrowing and
            # is excluded from ``count_gateway_tools``). With the flag off
            # ``builtin_tools`` is exactly ``task_tools``, so the unscoped chat
            # path is byte-identical.
            builtin_tools = task_tools + (
                self.build_askuser_tool()
                if self.settings.askuser_enabled
                else []
            )

            if self.settings.tool_gateway_url:
                from agent_service.tools.gateway_tools import (
                    build_gateway_toolkit,
                    discover_tools,
                )

                try:
                    definitions = await discover_tools(
                        self.settings.tool_gateway_url, bearer_token
                    )
                    if definitions:
                        definitions = self.filter_mutating_for_hitl(
                            definitions
                        )
                    if definitions and read_only:
                        definitions = self.filter_read_only(definitions)
                    if definitions and role is not None:
                        definitions = self.narrow_for_role(definitions, role)
                    if definitions:
                        toolkit = build_gateway_toolkit(
                            definitions,
                            self.settings.tool_gateway_url,
                        )
                        if builtin_tools:
                            toolkit.tool_groups[0].tools.extend(builtin_tools)
                        self._toolkits[cache_key] = toolkit
                        return toolkit
                except Exception as exc:
                    LOGGER.warning("failed to build gateway toolkit: %s", exc)

            # No gateway (or nothing discovered): builtin tools only, returned
            # uncached so a later turn can retry discovery.
            return Toolkit(tools=builtin_tools)

    def filter_mutating_for_hitl(self, definitions: list[dict]) -> list[dict]:
        """Drop non-read tools when HITL bridging is disabled (SPEC-021 R-3).

        A mutating tool can never execute without a human confirmation; when
        ``AGENT_HITL_CONFIRM_TIMEOUT=0`` there is no confirmation surface, so
        non-read tools are excluded from the toolkit entirely instead of
        parking silently. Read tools are untouched.
        """
        if self.settings.hitl_confirm_timeout > 0:
            return definitions
        kept = [
            definition
            for definition in definitions
            if definition.get("risk_level", "read") == "read"
        ]
        excluded = len(definitions) - len(kept)
        if excluded:
            self._mutating_tools_excluded = True
            LOGGER.warning(
                "HITL bridging disabled (AGENT_HITL_CONFIRM_TIMEOUT=0); "
                "excluded %d mutating tool(s) from the agent toolkit",
                excluded,
            )
        return kept

    def filter_read_only(self, definitions: list[dict]) -> list[dict]:
        """Restrict the toolkit to read-level tools for read-only turns.

        Automated diagnostic turns (incident triage) must never invoke — or
        silently park on — a mutating tool, regardless of what the model
        decides, so non-read tools are excluded structurally instead of
        relying on prompt discipline alone.
        """
        kept = [
            definition
            for definition in definitions
            if definition.get("risk_level", "read") == "read"
        ]
        excluded = len(definitions) - len(kept)
        if excluded:
            LOGGER.info(
                "read-only turn: excluded %d mutating tool(s) from the "
                "agent toolkit",
                excluded,
            )
        return kept

    def narrow_for_role(
        self, definitions: list[dict], role: AgentRole
    ) -> list[dict]:
        """Narrow discovered tools to a role's toolkit (SPEC-073 R-2/R-5).

        Subtractive only: the result is always a subset of the unscoped toolkit
        for the same token, so a role can never grant a tool the underlying
        token's ``roles`` could not already reach at the gateway (the real
        deny-by-default enforcement edge, unchanged in phase 2).

        - ``diagnostician``: read-level tools only (reuses ``filter_read_only``).
        - ``executor``: the full discovered set — a mutating tool still parks on
          the existing HITL confirmation (R-4) and dispatches only through the
          signed at-most-one-dispatch path with a distinct human approver.
        - ``orchestrator``: no direct gateway tools — it delegates, it does not
          itself invoke tools.
        - anything else: fail closed to the most restrictive posture (empty),
          never a wider one.
        """
        if role is AgentRole.DIAGNOSTICIAN:
            return self.filter_read_only(definitions)
        if role is AgentRole.EXECUTOR:
            return definitions
        if role is AgentRole.ORCHESTRATOR:
            return []
        # Defensive: the closed enum plus the fail-closed bind make this
        # unreachable, but an unrecognized role must never widen authority.
        LOGGER.warning(
            "unrecognized agent role %r; failing closed to no gateway tools",
            role,
        )
        return []

    def build_task_tools(self) -> list:
        """Built-in agentscope task tools, opt-in (SPEC-018 R-5).

        These mutate only session-local agent state, so the SPEC-017
        snapshot/restore persists them with no extra work.
        """
        from agentscope.tool import TaskCreate, TaskGet, TaskList, TaskUpdate

        return [TaskCreate(), TaskGet(), TaskList(), TaskUpdate()]

    def build_askuser_tool(self) -> list:
        """The agentscope ``AskUser`` external tool, opt-in (SPEC-080 R-5).

        ``AskUser`` is ``is_read_only=True`` + ``is_external_tool=True`` and is
        always-ALLOW at the tool gateway, so admitting it neither widens the
        mutation surface nor bypasses the gateway — it executes nothing. When
        the agent calls it, the kernel parks the reply as a read-only
        clarification (R-2) the session owner answers in-line; the resumed turn
        re-drives the SAME reply via an injected ``ExternalExecutionResultEvent``.
        Admitted only behind ``AGENT_ASKUSER_ENABLED`` (default off), so an unset
        deployment never sees the tool and the unscoped chat path is unchanged.
        """
        from agentscope.tool import AskUser

        return [AskUser()]

    def count_gateway_tools(self, toolkit) -> int:
        """Count gateway-backed tools in a toolkit.

        Task tools and builtins are excluded: only gateway tools ground the
        model in live data, which is what the no-tools guard cares about
        (SPEC-018 R-5).
        """
        count = 0
        for group in getattr(toolkit, "tool_groups", None) or []:
            for tool in getattr(group, "tools", None) or []:
                if getattr(tool, "gateway_tool_name", None):
                    count += 1
        return count
