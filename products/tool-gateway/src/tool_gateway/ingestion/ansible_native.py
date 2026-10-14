"""Native read-only ``ansible-inventory`` fallback connector (SPEC-069 R-2, OQ-1).

The documented **fallback** path for when no suitable self-hosted Ansible MCP
server is wired. It shells to ``ansible-inventory`` — a pure read tool — and
registers the *same* SPEC-007 ``BaseTool`` seam as the MCP adapter, so a caller
sees an ``ansible.*`` read tool either way. It does **not** prove the
MCP-ingestion substrate, which is why Stage-0 preferred the real-AWX MCP path and
retains this only as a fallback.

Two hard safety rules:

* **Never ``--check``/dry-run and never a mutating command** (OQ-3). Only
  ``ansible-inventory`` is invoked; no ``ansible``/``ansible-playbook`` ad-hoc or
  playbook run exists here. ``--check`` is not even a flag ``ansible-inventory``
  accepts.
* **No variable values are returned.** ``ansible-inventory --list`` embeds every
  host's vars under ``_meta.hostvars``, which can carry secrets
  (``ansible_password``, key paths, ...). This connector returns only the
  group/host **topology** (names + membership) and drops ``_meta`` entirely, so
  the fallback cannot leak an inventory secret into a tool result. Live
  host facts/vars stay the deferred ``gather_facts`` gap (OQ-5 "defer, don't
  fake"), not something this fallback fabricates.

The inventory source and executable path are operator configuration, never
model-selected arguments.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from functools import partial

from tool_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from tool_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "ansible"
CATEGORY = "ansible"
# Bound a diagnostic stderr snippet; a failing inventory load can echo a path or
# a vault-encrypted blob, so only a short tail is surfaced and never the vars.
_MAX_STDERR = 400


class AnsibleInventoryError(RuntimeError):
    """A non-zero ``ansible-inventory`` exit (stderr bounded)."""


def _parse_topology(stdout: str) -> dict:
    """Reduce ``ansible-inventory --list`` JSON to names + membership only.

    Drops ``_meta`` (hostvars — potential secrets) and every variable value,
    keeping just each group's ``hosts`` and ``children`` so the result is a safe
    read-only topology.
    """
    raw = json.loads(stdout)
    if not isinstance(raw, dict):
        raise AnsibleInventoryError("inventory output was not a JSON object")
    groups: dict[str, dict] = {}
    for group, body in raw.items():
        if group == "_meta":
            continue  # never emit hostvars
        if not isinstance(body, dict):
            continue
        groups[group] = {
            "hosts": sorted(body.get("hosts") or []),
            "children": sorted(body.get("children") or []),
        }
    all_hosts = sorted({h for g in groups.values() for h in g["hosts"]})
    return {"groups": groups, "hosts": all_hosts, "count": len(all_hosts)}


class AnsibleNativeConnector:
    """Read-only inventory listing via ``ansible-inventory`` (no MCP substrate)."""

    def __init__(
        self,
        *,
        inventory_path: str = "",
        executable: str = "ansible-inventory",
        timeout_ms: int = 10000,
    ) -> None:
        self._inventory_path = inventory_path
        self._executable = executable or "ansible-inventory"
        self._timeout_s = max(timeout_ms, 1) / 1000.0

    @property
    def configured(self) -> bool:
        return bool(self._inventory_path)

    def register_tools(self, registry: ToolRegistry) -> None:
        registry.register(ListInventoryHostsTool(self))

    def _list_hosts_sync(self) -> dict:
        """Run ``ansible-inventory -i <src> --list`` (read-only) and parse it."""
        cmd = [self._executable, "-i", self._inventory_path, "--list"]
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, operator config
            cmd, capture_output=True, text=True, timeout=self._timeout_s
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip()[-_MAX_STDERR:]
            raise AnsibleInventoryError(detail or f"exit {proc.returncode}")
        return _parse_topology(proc.stdout)


class ListInventoryHostsTool(BaseTool):
    """List the inventory's groups and hosts (names/membership only)."""

    def __init__(self, connector: AnsibleNativeConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ansible.list_inventory_hosts",
            description=(
                "List the configured Ansible inventory's groups and hosts "
                "(names and membership only; no host variables or facts)."
            ),
            risk_level="read",
            category=CATEGORY,
            parameters_schema={"type": "object", "properties": {}},
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        name = "ansible.list_inventory_hosts"
        if not self._connector.configured:
            return make_error_result(
                name, "ANSIBLE_NOT_CONFIGURED",
                "No Ansible inventory source is configured "
                "(GATEWAY_ANSIBLE_INVENTORY_PATH).",
                source_system=SOURCE_SYSTEM,
            )
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None, partial(self._connector._list_hosts_sync)
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name=name,
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except FileNotFoundError:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return make_error_result(
                name, "ANSIBLE_EXECUTABLE_NOT_FOUND",
                f"The '{self._connector._executable}' executable was not found.",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("ansible-inventory timed out")
            return make_error_result(
                name, "ANSIBLE_INVENTORY_TIMEOUT",
                "The ansible-inventory read timed out.",
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        except (AnsibleInventoryError, json.JSONDecodeError) as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.warning("ansible-inventory failed: %s", exc.__class__.__name__)
            return make_error_result(
                name, "ANSIBLE_INVENTORY_ERROR", str(exc),
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
        except Exception as exc:  # never fabricate a success
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("ansible.list_inventory_hosts failed")
            return make_error_result(
                name, "ANSIBLE_INVENTORY_ERROR", str(exc),
                source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
