"""Kubernetes read-only connector (SPEC-007 R-3).

Provides four read-only tools backed by the official kubernetes-client/python:
  - k8s.list_pods
  - k8s.get_pod
  - k8s.get_events
  - k8s.get_pod_logs

The connector uses in-cluster config when available, falling back to kubeconfig
for local development. When neither is available, tools return a structured
K8S_NOT_CONFIGURED error.
"""

from __future__ import annotations

import asyncio
import logging
import time
from functools import partial

from api_gateway.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
    build_evidence,
    make_error_result,
)
from api_gateway.tools.registry import ToolRegistry

LOGGER = logging.getLogger(__name__)

SOURCE_SYSTEM = "kubernetes"
MAX_TAIL_LINES = 1000
DEFAULT_TAIL_LINES = 100


class KubernetesConnector:
    """Manages K8s client lifecycle and registers read-only tools."""

    def __init__(self, default_namespace: str | None = None) -> None:
        self._default_namespace = default_namespace or "default"
        self._core_v1 = None
        self._configured: bool | None = None  # None = not yet attempted

    def _ensure_client(self) -> bool:
        """Lazily initialize the K8s client. Returns True if configured."""
        if self._configured is not None:
            return self._configured

        try:
            from kubernetes import client, config

            try:
                config.load_incluster_config()
                LOGGER.info("kubernetes client using in-cluster config")
            except config.ConfigException:
                try:
                    config.load_kube_config()
                    LOGGER.info("kubernetes client using kubeconfig")
                except config.ConfigException:
                    LOGGER.warning("kubernetes client not configured")
                    self._configured = False
                    return False

            self._core_v1 = client.CoreV1Api()
            self._configured = True
            return True
        except ImportError:
            LOGGER.warning("kubernetes package not installed")
            self._configured = False
            return False

    def _resolve_namespace(self, parameters: dict) -> str:
        return parameters.get("namespace") or self._default_namespace

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register all K8s tools with the given registry."""
        registry.register(ListPodsTool(self))
        registry.register(GetPodTool(self))
        registry.register(GetEventsTool(self))
        registry.register(GetPodLogsTool(self))

    # --- Sync operations (run in executor) ---

    def _list_pods_sync(self, namespace: str, label_selector: str | None) -> dict:
        from kubernetes import client

        kwargs: dict = {"namespace": namespace}
        if label_selector:
            kwargs["label_selector"] = label_selector
        pod_list = self._core_v1.list_namespaced_pod(**kwargs)
        pods = []
        for pod in pod_list.items:
            pods.append({
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node_name": pod.spec.node_name,
                "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
                "containers": [
                    {
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": _container_state(cs.state),
                    }
                    for cs in (pod.status.container_statuses or [])
                ],
                "labels": pod.metadata.labels or {},
            })
        return {"pods": pods, "count": len(pods)}

    def _get_pod_sync(self, name: str, namespace: str) -> dict:
        pod = self._core_v1.read_namespaced_pod(name=name, namespace=namespace)
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": pod.status.phase,
            "node_name": pod.spec.node_name,
            "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
            "containers": [
                {
                    "name": cs.name,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": _container_state(cs.state),
                }
                for cs in (pod.status.container_statuses or [])
            ],
            "labels": pod.metadata.labels or {},
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason}
                for c in (pod.status.conditions or [])
            ],
        }

    def _get_events_sync(self, namespace: str, field_selector: str | None) -> dict:
        kwargs: dict = {"namespace": namespace}
        if field_selector:
            kwargs["field_selector"] = field_selector
        event_list = self._core_v1.list_namespaced_event(**kwargs)
        events = []
        for event in event_list.items:
            events.append({
                "reason": event.reason,
                "message": event.message,
                "type": event.type,
                "count": event.count,
                "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
                "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
                "involved_object": {
                    "kind": event.involved_object.kind,
                    "name": event.involved_object.name,
                } if event.involved_object else None,
            })
        return {"events": events, "count": len(events)}

    def _get_pod_logs_sync(
        self,
        name: str,
        namespace: str,
        container: str | None,
        tail_lines: int,
    ) -> dict:
        kwargs: dict = {
            "name": name,
            "namespace": namespace,
            "tail_lines": tail_lines,
        }
        if container:
            kwargs["container"] = container
        logs = self._core_v1.read_namespaced_pod_log(**kwargs)
        return {"logs": logs, "pod": name, "container": container, "tail_lines": tail_lines}


def _container_state(state) -> str:
    """Extract a human-readable container state string."""
    if state is None:
        return "unknown"
    if state.running:
        return "running"
    if state.waiting:
        return f"waiting ({state.waiting.reason or 'unknown'})"
    if state.terminated:
        return f"terminated ({state.terminated.reason or 'exit ' + str(state.terminated.exit_code)})"
    return "unknown"


def _coerce_tail_lines(value: object) -> tuple[int, str | None]:
    """Clamp `tail_lines` into [1, MAX_TAIL_LINES], rejecting non-integer input.

    LLM-supplied parameters are untrusted, so a bad value must surface as a
    structured INVALID_PARAMETERS result rather than an exception.
    """
    if value is None:
        return DEFAULT_TAIL_LINES, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TAIL_LINES, f"Parameter 'tail_lines' must be an integer, got {value!r}."
    if parsed < 1:
        return DEFAULT_TAIL_LINES, f"Parameter 'tail_lines' must be at least 1, got {parsed}."
    return min(parsed, MAX_TAIL_LINES), None


# --- Tool implementations ---


class ListPodsTool(BaseTool):
    def __init__(self, connector: KubernetesConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="k8s.list_pods",
            description="List pods in a Kubernetes namespace with optional label selector filtering.",
            risk_level="read",
            category="kubernetes",
            parameters_schema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Target namespace (defaults to configured namespace)."},
                    "label_selector": {"type": "string", "description": "Kubernetes label selector, e.g. app=web."},
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result("k8s.list_pods", "K8S_NOT_CONFIGURED", "Kubernetes client is not configured.", source_system=SOURCE_SYSTEM)

        namespace = self._connector._resolve_namespace(parameters)
        label_selector = parameters.get("label_selector")

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(self._connector._list_pods_sync, namespace, label_selector),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="k8s.list_pods",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("k8s.list_pods failed")
            return make_error_result("k8s.list_pods", "K8S_API_ERROR", str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms)


class GetPodTool(BaseTool):
    def __init__(self, connector: KubernetesConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="k8s.get_pod",
            description="Get detailed status of a specific Kubernetes pod.",
            risk_level="read",
            category="kubernetes",
            parameters_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "Pod name."},
                    "namespace": {"type": "string", "description": "Target namespace (defaults to configured namespace)."},
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result("k8s.get_pod", "K8S_NOT_CONFIGURED", "Kubernetes client is not configured.", source_system=SOURCE_SYSTEM)

        name = parameters.get("name")
        if not name:
            return make_error_result("k8s.get_pod", "INVALID_PARAMETERS", "Parameter 'name' is required.", source_system=SOURCE_SYSTEM)

        namespace = self._connector._resolve_namespace(parameters)

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(self._connector._get_pod_sync, name, namespace),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="k8s.get_pod",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("k8s.get_pod failed")
            return make_error_result("k8s.get_pod", "K8S_API_ERROR", str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms)


class GetEventsTool(BaseTool):
    def __init__(self, connector: KubernetesConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="k8s.get_events",
            description="List Kubernetes events in a namespace with optional field selector filtering.",
            risk_level="read",
            category="kubernetes",
            parameters_schema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Target namespace (defaults to configured namespace)."},
                    "field_selector": {"type": "string", "description": "Field selector, e.g. involvedObject.name=my-pod."},
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result("k8s.get_events", "K8S_NOT_CONFIGURED", "Kubernetes client is not configured.", source_system=SOURCE_SYSTEM)

        namespace = self._connector._resolve_namespace(parameters)
        field_selector = parameters.get("field_selector")

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(self._connector._get_events_sync, namespace, field_selector),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="k8s.get_events",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("k8s.get_events failed")
            return make_error_result("k8s.get_events", "K8S_API_ERROR", str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms)


class GetPodLogsTool(BaseTool):
    def __init__(self, connector: KubernetesConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="k8s.get_pod_logs",
            description="Retrieve recent logs from a Kubernetes pod container.",
            risk_level="read",
            category="kubernetes",
            parameters_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "Pod name."},
                    "namespace": {"type": "string", "description": "Target namespace (defaults to configured namespace)."},
                    "container": {"type": "string", "description": "Container name (optional for single-container pods)."},
                    "tail_lines": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TAIL_LINES,
                        "default": DEFAULT_TAIL_LINES,
                        "description": f"Number of recent log lines (default {DEFAULT_TAIL_LINES}, max {MAX_TAIL_LINES}).",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result("k8s.get_pod_logs", "K8S_NOT_CONFIGURED", "Kubernetes client is not configured.", source_system=SOURCE_SYSTEM)

        name = parameters.get("name")
        if not name:
            return make_error_result("k8s.get_pod_logs", "INVALID_PARAMETERS", "Parameter 'name' is required.", source_system=SOURCE_SYSTEM)

        namespace = self._connector._resolve_namespace(parameters)
        container = parameters.get("container")
        tail_lines, tail_lines_error = _coerce_tail_lines(parameters.get("tail_lines"))
        if tail_lines_error:
            return make_error_result("k8s.get_pod_logs", "INVALID_PARAMETERS", tail_lines_error, source_system=SOURCE_SYSTEM)

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(self._connector._get_pod_logs_sync, name, namespace, container, tail_lines),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="k8s.get_pod_logs",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("k8s.get_pod_logs failed")
            return make_error_result("k8s.get_pod_logs", "K8S_API_ERROR", str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms)
