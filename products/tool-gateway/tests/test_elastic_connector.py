"""Elastic connector unit tests with mocked client (SPEC-011 R-3)."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from tool_gateway.tools.elastic_connector import ElasticConnector
from tool_gateway.tools.registry import ToolRegistry


def _run(coro):
    return asyncio.run(coro)


class ElasticConnectorNotConfiguredTests(unittest.TestCase):
    """When Elastic is not reachable, tools return ELASTIC_NOT_CONFIGURED."""

    def setUp(self) -> None:
        self.connector = ElasticConnector()
        self.connector._configured = False

    def test_search_logs_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.search_logs", {"query": "error"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ELASTIC_NOT_CONFIGURED")

    def test_get_service_health_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.get_service_health", {"service_name": "web"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ELASTIC_NOT_CONFIGURED")

    def test_get_active_alerts_not_configured(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.get_active_alerts", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ELASTIC_NOT_CONFIGURED")


class ElasticConnectorRegistrationTests(unittest.TestCase):
    """Verify tool registration and metadata."""

    def test_registers_three_tools(self) -> None:
        connector = ElasticConnector(url="http://elastic:9200")
        registry = ToolRegistry()
        connector.register_tools(registry)
        definitions = registry.list_definitions()
        self.assertEqual(len(definitions), 3)
        names = {d.name for d in definitions}
        self.assertEqual(
            names,
            {"elastic.search_logs", "elastic.get_service_health", "elastic.get_active_alerts"},
        )

    def test_all_tools_are_read_level(self) -> None:
        connector = ElasticConnector(url="http://elastic:9200")
        registry = ToolRegistry()
        connector.register_tools(registry)
        for defn in registry.list_definitions():
            self.assertEqual(defn.risk_level, "read")
            self.assertEqual(defn.category, "observability")


class ElasticConnectorExecutionTests(unittest.TestCase):
    """Test execution with a mocked Elasticsearch client."""

    def setUp(self) -> None:
        self.connector = ElasticConnector(
            url="http://elastic:9200",
            api_key="test-key",
        )
        self.connector._configured = True
        self.mock_es = MagicMock()
        self.connector._es = self.mock_es

    def test_search_logs_success(self) -> None:
        self.mock_es.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {"_id": "1", "_index": "logs", "_source": {"message": "error occurred", "@timestamp": "2026-08-05T00:00:00Z"}},
                    {"_id": "2", "_index": "logs", "_source": {"message": "warning", "@timestamp": "2026-08-05T00:01:00Z"}},
                ],
            }
        }
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.search_logs", {"query": "error"}, {}))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["total"], 2)
        self.assertEqual(len(result.data["hits"]), 2)
        self.assertEqual(result.evidence["source_system"], "elastic")

    def test_search_logs_missing_query(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.search_logs", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_search_logs_time_range_clamping(self) -> None:
        self.mock_es.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.search_logs",
            {"query": "*", "time_range_minutes": 9999},
            {},
        ))
        self.assertEqual(result.status, "success")
        # time_range should be clamped to 1440.
        self.assertEqual(result.data["time_range_minutes"], 1440)

    def test_search_logs_max_results_clamping(self) -> None:
        self.mock_es.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.search_logs",
            {"query": "*", "max_results": 999},
            {},
        ))
        self.assertEqual(result.status, "success")
        self.mock_es.search.assert_called_once()
        call_body = self.mock_es.search.call_args[1]["body"]
        self.assertEqual(call_body["size"], 200)

    def test_get_service_health_success(self) -> None:
        self.mock_es.search.return_value = {
            "aggregations": {
                "request_count": {"value": 1000},
                "error_count": {"doc_count": 50},
                "avg_latency": {"value": 150_000_000},  # 150ms in nanoseconds
            }
        }
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.get_service_health",
            {"service_name": "web-api"},
            {},
        ))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["request_count"], 1000)
        self.assertEqual(result.data["error_count"], 50)
        self.assertAlmostEqual(result.data["error_rate"], 0.05)
        self.assertEqual(result.data["avg_latency_ms"], 150.0)

    def test_get_service_health_missing_service_name(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.get_service_health", {}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_get_service_health_zero_requests(self) -> None:
        self.mock_es.search.return_value = {
            "aggregations": {
                "request_count": {"value": 0},
                "error_count": {"doc_count": 0},
                "avg_latency": {"value": None},
            }
        }
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.get_service_health",
            {"service_name": "idle-service"},
            {},
        ))
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data["error_rate"], 0.0)
        self.assertIsNone(result.data["avg_latency_ms"])

    def test_get_active_alerts_success(self) -> None:
        self.mock_es.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_id": "alert-1",
                        "_source": {
                            "kibana.alert.severity": "critical",
                            "kibana.alert.status": "active",
                            "kibana.alert.rule": {"name": "High CPU"},
                            "message": "CPU usage above 90%",
                            "@timestamp": "2026-08-05T00:00:00Z",
                        },
                    }
                ],
            }
        }
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.get_active_alerts", {}, {}))
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.data["alerts"]), 1)
        self.assertEqual(result.data["alerts"][0]["severity"], "critical")

    def test_get_active_alerts_with_severity_filter(self) -> None:
        self.mock_es.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.get_active_alerts",
            {"severity": "warning"},
            {},
        ))
        self.assertEqual(result.status, "success")
        self.mock_es.search.assert_called_once()

    def test_get_active_alerts_invalid_severity(self) -> None:
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke(
            "elastic.get_active_alerts",
            {"severity": "unknown"},
            {},
        ))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "INVALID_PARAMETERS")

    def test_connection_error_returns_structured_error(self) -> None:
        self.mock_es.search.side_effect = ConnectionError("connection refused")
        registry = ToolRegistry()
        self.connector.register_tools(registry)
        result = _run(registry.invoke("elastic.search_logs", {"query": "*"}, {}))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error["code"], "ELASTIC_CONNECTION_ERROR")


class ElasticConnectorLazyInitTests(unittest.TestCase):
    """Test lazy client initialization."""

    def test_no_url_means_not_configured(self) -> None:
        connector = ElasticConnector()
        self.assertFalse(connector._ensure_client())
        self.assertFalse(connector._configured)

    def test_import_error_means_not_configured(self) -> None:
        connector = ElasticConnector(url="http://elastic:9200")
        with patch.dict("sys.modules", {"elasticsearch": None}):
            result = connector._ensure_client()
        self.assertFalse(result)

    def test_api_key_auth_used_when_set(self) -> None:
        connector = ElasticConnector(url="http://elastic:9200", api_key="my-key")
        with patch("elasticsearch.Elasticsearch") as MockES:
            mock_instance = MagicMock()
            MockES.return_value = mock_instance
            result = connector._ensure_client()
        self.assertTrue(result)
        MockES.assert_called_once_with(hosts=["http://elastic:9200"], api_key="my-key")

    def test_basic_auth_fallback(self) -> None:
        connector = ElasticConnector(
            url="http://elastic:9200",
            username="user",
            password="pass",
        )
        with patch("elasticsearch.Elasticsearch") as MockES:
            mock_instance = MagicMock()
            MockES.return_value = mock_instance
            result = connector._ensure_client()
        self.assertTrue(result)
        MockES.assert_called_once_with(
            hosts=["http://elastic:9200"],
            basic_auth=("user", "pass"),
        )

    def test_tls_verification_disabled(self) -> None:
        connector = ElasticConnector(
            url="https://elastic:9200",
            api_key="key",
            verify_tls=False,
        )
        with patch("elasticsearch.Elasticsearch") as MockES:
            mock_instance = MagicMock()
            MockES.return_value = mock_instance
            connector._ensure_client()
        MockES.assert_called_once_with(
            hosts=["https://elastic:9200"],
            api_key="key",
            verify_certs=False,
        )


class ElasticSettingsTests(unittest.TestCase):
    """Test GatewaySettings Elastic fields."""

    def test_elastic_defaults(self) -> None:
        from tool_gateway.core.config import GatewaySettings
        settings = GatewaySettings()
        self.assertFalse(settings.elastic_enabled)
        self.assertEqual(settings.elastic_url, "")
        self.assertTrue(settings.elastic_verify_tls)
        self.assertEqual(settings.elastic_alerts_index, ".alerts-*")

    def test_elastic_from_env(self) -> None:
        from tool_gateway.core.config import GatewaySettings
        with patch.dict("os.environ", {
            "GATEWAY_ELASTIC_ENABLED": "true",
            "GATEWAY_ELASTIC_URL": "https://elastic:9200",
            "GATEWAY_ELASTIC_API_KEY": "my-key",
        }):
            settings = GatewaySettings.from_env()
        self.assertTrue(settings.elastic_enabled)
        self.assertEqual(settings.elastic_url, "https://elastic:9200")
        self.assertEqual(settings.elastic_api_key, "my-key")
