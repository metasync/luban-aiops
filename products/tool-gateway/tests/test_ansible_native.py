"""SPEC-069 R-2 tests: the native read-only ``ansible-inventory`` fallback (OQ-1).

Asserts the fallback registers under the same read-tier seam, fails closed on
every fault class, returns only inventory topology (never ``_meta.hostvars``
secrets), and never invokes ``--check``/dry-run or any mutating command.
``subprocess.run`` is patched, so CI runs no live ``ansible-inventory``.
"""

import asyncio
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from tool_gateway.ingestion.ansible_native import (
    AnsibleNativeConnector,
    ListInventoryHostsTool,
    _parse_topology,
)
from tool_gateway.tools.base import ToolResult, build_evidence, make_error_result
from tool_gateway.tools.registry import ToolRegistry

_SUBPROCESS = "tool_gateway.ingestion.ansible_native.subprocess.run"

_INVENTORY_JSON = json.dumps({
    "all": {"children": ["ungrouped", "webservers"]},
    "ungrouped": {"hosts": ["host-a"]},
    "webservers": {"hosts": ["web-1", "web-2"]},
    "_meta": {
        "hostvars": {
            "web-1": {"ansible_password": "SUPERSECRET-PW", "ansible_host": "10.0.0.1"},
        }
    },
})


def _run(coro):
    return asyncio.run(coro)


def _completed(stdout="", stderr="", returncode=0):
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


class NativeRegistrationTests(unittest.TestCase):
    def test_registers_one_read_tier_tool(self) -> None:
        registry = ToolRegistry()
        AnsibleNativeConnector(inventory_path="/tmp/inv").register_tools(registry)
        defs = registry.list_definitions()
        self.assertEqual([d.name for d in defs], ["ansible.list_inventory_hosts"])
        self.assertEqual(defs[0].risk_level, "read")
        self.assertEqual(defs[0].category, "ansible")

    def test_not_configured_fails_closed(self) -> None:
        registry = ToolRegistry()
        AnsibleNativeConnector(inventory_path="").register_tools(registry)
        result = _run(registry.invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ANSIBLE_NOT_CONFIGURED")


class NativeExecutionTests(unittest.TestCase):
    def _registry(self, **kwargs):
        registry = ToolRegistry()
        AnsibleNativeConnector(inventory_path="/tmp/inv", **kwargs).register_tools(registry)
        return registry

    def test_success_returns_topology_without_hostvars(self) -> None:
        with patch(_SUBPROCESS, return_value=_completed(stdout=_INVENTORY_JSON)) as run:
            result = _run(self._registry().invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["hosts"], ["host-a", "web-1", "web-2"])
        self.assertEqual(result.data["groups"]["webservers"]["hosts"], ["web-1", "web-2"])
        # The secret-bearing hostvars are never emitted.
        blob = json.dumps(result.to_dict())
        self.assertNotIn("SUPERSECRET-PW", blob)
        self.assertNotIn("_meta", blob)
        self.assertNotIn("ansible_password", blob)
        # Read-only argv: ansible-inventory -i <src> --list, never --check.
        argv = run.call_args[0][0]
        self.assertIn("--list", argv)
        self.assertNotIn("--check", argv)
        self.assertEqual(argv[0], "ansible-inventory")

    def test_executable_not_found_fails_closed(self) -> None:
        with patch(_SUBPROCESS, side_effect=FileNotFoundError("ansible-inventory")):
            result = _run(self._registry().invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ANSIBLE_EXECUTABLE_NOT_FOUND")

    def test_nonzero_exit_fails_closed(self) -> None:
        with patch(_SUBPROCESS, return_value=_completed(stderr="boom", returncode=1)):
            result = _run(self._registry().invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ANSIBLE_INVENTORY_ERROR")

    def test_timeout_fails_closed_not_success(self) -> None:
        with patch(_SUBPROCESS, side_effect=subprocess.TimeoutExpired("ansible-inventory", 10)):
            result = _run(self._registry().invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ANSIBLE_INVENTORY_TIMEOUT")

    def test_malformed_json_fails_closed(self) -> None:
        with patch(_SUBPROCESS, return_value=_completed(stdout="not json")):
            result = _run(self._registry().invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ANSIBLE_INVENTORY_ERROR")

    def test_custom_executable_is_honoured(self) -> None:
        with patch(_SUBPROCESS, return_value=_completed(stdout=_INVENTORY_JSON)) as run:
            _run(self._registry(executable="/opt/bin/ansible-inventory")
                 .invoke("ansible.list_inventory_hosts", {}, {}))
        self.assertEqual(run.call_args[0][0][0], "/opt/bin/ansible-inventory")


class TopologyParserTests(unittest.TestCase):
    def test_drops_meta_and_variable_values(self) -> None:
        topo = _parse_topology(_INVENTORY_JSON)
        self.assertNotIn("_meta", topo["groups"])
        self.assertEqual(topo["count"], 3)
        self.assertEqual(topo["groups"]["all"]["children"], ["ungrouped", "webservers"])

    def test_non_object_output_raises(self) -> None:
        from tool_gateway.ingestion.ansible_native import AnsibleInventoryError
        with self.assertRaises(AnsibleInventoryError):
            _parse_topology("[1, 2, 3]")


class NativeAuditAttributionTests(unittest.TestCase):
    """SPEC-069 R-4/R-5: the fallback reports the acting-service target-identity
    mode and attributes a reachability failure ``target_unavailable`` — but not a
    gateway config gap (``ANSIBLE_NOT_CONFIGURED``)."""

    def _tool(self) -> ListInventoryHostsTool:
        return ListInventoryHostsTool(AnsibleNativeConnector(inventory_path="/tmp/inv"))

    def test_success_attribution_is_identity_mode_only(self) -> None:
        ok = ToolResult(
            tool_name="ansible.list_inventory_hosts", status="success",
            data={}, evidence=build_evidence("read", "ansible", 1),
        )
        self.assertEqual(
            self._tool().audit_attribution(ok),
            {"target_identity_mode": "acting_service"},
        )

    def test_timeout_attribution_is_target_unavailable(self) -> None:
        err = make_error_result(
            "ansible.list_inventory_hosts", "ANSIBLE_INVENTORY_TIMEOUT",
            "timed out", source_system="ansible",
        )
        self.assertEqual(
            self._tool().audit_attribution(err),
            {"target_identity_mode": "acting_service",
             "failure_class": "target_unavailable"},
        )

    def test_config_gap_is_not_target_unavailable(self) -> None:
        err = make_error_result(
            "ansible.list_inventory_hosts", "ANSIBLE_NOT_CONFIGURED",
            "unset", source_system="ansible",
        )
        self.assertNotIn("failure_class", self._tool().audit_attribution(err))


class NativeNoCheckModeTests(unittest.TestCase):
    """SPEC-069 R-5 / OQ-3: the fallback argv is pinned read-only — never --check."""

    def test_argv_is_pinned_read_only_inventory_listing(self) -> None:
        registry = ToolRegistry()
        AnsibleNativeConnector(inventory_path="/tmp/inv").register_tools(registry)
        with patch(_SUBPROCESS, return_value=_completed(stdout=_INVENTORY_JSON)) as run:
            _run(registry.invoke("ansible.list_inventory_hosts", {}, {}))
        # Exactly the read-only inventory listing: no --check/--diff/dry-run flag
        # can appear because the argv is fixed to these four tokens.
        self.assertEqual(
            run.call_args[0][0],
            ["ansible-inventory", "-i", "/tmp/inv", "--list"],
        )


if __name__ == "__main__":
    unittest.main()
