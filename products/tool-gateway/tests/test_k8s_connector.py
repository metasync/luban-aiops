"""Kubernetes connector unit tests with mocked client (SPEC-007 R-3)."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from api_gateway.tools.k8s_connector import KubernetesConnector
from api_gateway.tools.registry import ToolRegistry


def _run(coro):
    return asyncio.run(coro)


class K8sConnectorNotConfiguredTests(unittest.TestCase):
    """When K8s is not reachable, tools return K8S_NOT_CONFIGURED."""

    def setUp(self) -> None:
        self.connector = KubernetesConnector(default_namespace="test-ns")
        # Force configured = False
        self.connector._configured = False

    def test_list_pods_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.list_pods", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "K8S_NOT_CONFIGURED")

    def test_get_pod_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod", {"name": "my-pod"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "K8S_NOT_CONFIGURED")

    def test_get_events_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_events", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "K8S_NOT_CONFIGURED")

    def test_get_pod_logs_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod_logs", {"name": "my-pod"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "K8S_NOT_CONFIGURED")


class K8sConnectorRegistrationTests(unittest.TestCase):
    """Verify tool registration and metadata."""

    def test_registers_four_tools(self) -> None:
        connector = KubernetesConnector()
        registry = ToolRegistry()
        connector.register_tools(registry)
        definitions = registry.list_definitions()
        self.assertEqual(len(definitions), 4)
        names = {d.name for d in definitions}
        self.assertEqual(names, {"k8s.list_pods", "k8s.get_pod", "k8s.get_events", "k8s.get_pod_logs"})

    def test_all_tools_are_read_level(self) -> None:
        connector = KubernetesConnector()
        registry = ToolRegistry()
        connector.register_tools(registry)
        for defn in registry.list_definitions():
            self.assertEqual(defn.risk_level, "read")
            self.assertEqual(defn.category, "kubernetes")


class K8sConnectorExecutionTests(unittest.TestCase):
    """Test execution with a mocked K8s CoreV1Api."""

    def setUp(self) -> None:
        self.connector = KubernetesConnector(default_namespace="test-ns")
        self.connector._configured = True
        self.mock_api = MagicMock()
        self.connector._core_v1 = self.mock_api

    def test_list_pods_success(self) -> None:
        pod = MagicMock()
        pod.metadata.name = "web-1"
        pod.metadata.namespace = "test-ns"
        pod.metadata.labels = {"app": "web"}
        pod.status.phase = "Running"
        pod.spec.node_name = "node-1"
        pod.status.start_time = None
        pod.status.container_statuses = []

        pod_list = MagicMock()
        pod_list.items = [pod]
        self.mock_api.list_namespaced_pod.return_value = pod_list

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.list_pods", {}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["pods"][0]["name"], "web-1")
        self.mock_api.list_namespaced_pod.assert_called_once_with(namespace="test-ns")

    def test_list_pods_with_label_selector(self) -> None:
        pod_list = MagicMock()
        pod_list.items = []
        self.mock_api.list_namespaced_pod.return_value = pod_list

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.list_pods", {"label_selector": "app=web"}, {}))

        self.assertEqual(result.status, "success")
        self.mock_api.list_namespaced_pod.assert_called_once_with(
            namespace="test-ns", label_selector="app=web"
        )

    def test_get_pod_success(self) -> None:
        pod = MagicMock()
        pod.metadata.name = "web-1"
        pod.metadata.namespace = "test-ns"
        pod.metadata.labels = {}
        pod.status.phase = "Running"
        pod.spec.node_name = "node-1"
        pod.status.start_time = None
        pod.status.container_statuses = []
        pod.status.conditions = []
        self.mock_api.read_namespaced_pod.return_value = pod

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod", {"name": "web-1"}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["name"], "web-1")
        self.mock_api.read_namespaced_pod.assert_called_once_with(name="web-1", namespace="test-ns")

    def test_get_pod_missing_name(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_get_events_success(self) -> None:
        event = MagicMock()
        event.reason = "Pulled"
        event.message = "Successfully pulled image"
        event.type = "Normal"
        event.count = 1
        event.first_timestamp = None
        event.last_timestamp = None
        event.involved_object.kind = "Pod"
        event.involved_object.name = "web-1"

        event_list = MagicMock()
        event_list.items = [event]
        self.mock_api.list_namespaced_event.return_value = event_list

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_events", {}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["events"][0]["reason"], "Pulled")

    def test_get_pod_logs_success(self) -> None:
        self.mock_api.read_namespaced_pod_log.return_value = "line1\nline2\n"

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod_logs", {"name": "web-1", "tail_lines": 50}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["logs"], "line1\nline2\n")
        self.assertEqual(result.data["tail_lines"], 50)
        self.mock_api.read_namespaced_pod_log.assert_called_once_with(
            name="web-1", namespace="test-ns", tail_lines=50
        )

    def test_get_pod_logs_tail_capped(self) -> None:
        self.mock_api.read_namespaced_pod_log.return_value = ""

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.get_pod_logs", {"name": "web-1", "tail_lines": 9999}, {}))

        self.assertEqual(result.status, "success")
        # Should be capped at 1000
        self.mock_api.read_namespaced_pod_log.assert_called_once_with(
            name="web-1", namespace="test-ns", tail_lines=1000
        )

    def test_get_pod_logs_rejects_non_integer_tail_lines(self) -> None:
        """Untrusted LLM-supplied parameters must not raise out of the tool."""
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(
            registry.invoke("k8s.get_pod_logs", {"name": "web-1", "tail_lines": "many"}, {})
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.mock_api.read_namespaced_pod_log.assert_not_called()

    def test_get_pod_logs_rejects_non_positive_tail_lines(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(
            registry.invoke("k8s.get_pod_logs", {"name": "web-1", "tail_lines": 0}, {})
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")
        self.mock_api.read_namespaced_pod_log.assert_not_called()

    def test_k8s_api_error_returns_structured_error(self) -> None:
        self.mock_api.list_namespaced_pod.side_effect = Exception("connection refused")

        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("k8s.list_pods", {}, {}))

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "K8S_API_ERROR")
        self.assertIn("connection refused", result.error["message"])
