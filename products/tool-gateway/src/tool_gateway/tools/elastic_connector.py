"""Elastic observability connector (SPEC-011 R-3).

Provides three read-only tools backed by the official elasticsearch Python
client:
  - elastic.search_logs
  - elastic.get_service_health
  - elastic.get_active_alerts

The connector uses API-key authentication when available, falling back to
basic auth. When the connector is not enabled or Elastic is unreachable,
tools return a structured error result.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
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

SOURCE_SYSTEM = "elastic"
MAX_TIME_RANGE_MINUTES = 1440
DEFAULT_TIME_RANGE_MINUTES = 15
MAX_RESULTS = 200
DEFAULT_MAX_RESULTS = 50


class ElasticConnector:
    """Manages Elasticsearch client lifecycle and registers read-only tools."""

    def __init__(
        self,
        url: str = "",
        api_key: str = "",
        username: str = "",
        password: str = "",
        verify_tls: bool = True,
        alerts_index: str = ".alerts-*",
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._username = username
        self._password = password
        self._verify_tls = verify_tls
        self._alerts_index = alerts_index
        self._es = None
        self._configured: bool | None = None  # None = not yet attempted

    def _ensure_client(self) -> bool:
        """Lazily initialize the Elasticsearch client. Returns True if configured."""
        if self._configured is not None:
            return self._configured

        if not self._url:
            LOGGER.warning("elastic connector not configured: no URL")
            self._configured = False
            return False

        try:
            from elasticsearch import Elasticsearch

            kwargs: dict = {"hosts": [self._url]}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            elif self._username and self._password:
                kwargs["basic_auth"] = (self._username, self._password)

            if not self._verify_tls:
                kwargs["verify_certs"] = False

            self._es = Elasticsearch(**kwargs)
            # Verify connectivity.
            self._es.info()
            self._configured = True
            LOGGER.info("elastic connector connected to %s", self._url)
            return True
        except ImportError:
            LOGGER.warning("elasticsearch package not installed")
            self._configured = False
            return False
        except Exception as exc:
            LOGGER.warning("elastic connector failed to connect: %s", exc)
            self._configured = False
            return False

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register all Elastic tools with the given registry."""
        registry.register(SearchLogsTool(self))
        registry.register(GetServiceHealthTool(self))
        registry.register(GetActiveAlertsTool(self))

    # --- Sync operations (run in executor) ---

    def _search_logs_sync(
        self,
        query: str,
        index: str,
        time_range_minutes: int,
        max_results: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        body = {
            "size": max_results,
            "query": {
                "bool": {
                    "must": [
                        {"query_string": {"query": query}},
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": (
                                        now - timedelta(minutes=time_range_minutes)
                                    ).isoformat(),
                                    "lte": now.isoformat(),
                                }
                            }
                        },
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        result = self._es.search(index=index, body=body)
        hits = result.get("hits", {})
        documents = []
        for hit in hits.get("hits", []):
            doc = hit.get("_source", {})
            doc["_id"] = hit.get("_id")
            doc["_index"] = hit.get("_index")
            documents.append(doc)
        return {
            "hits": documents,
            "total": hits.get("total", {}).get("value", 0),
            "query": query,
            "index": index,
            "time_range_minutes": time_range_minutes,
        }

    def _get_service_health_sync(
        self,
        service_name: str,
        time_range_minutes: int,
    ) -> dict:
        now = datetime.now(timezone.utc)
        body = {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"service.name": service_name}},
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": (
                                        now - timedelta(minutes=time_range_minutes)
                                    ).isoformat(),
                                    "lte": now.isoformat(),
                                }
                            }
                        },
                    ]
                }
            },
            "aggs": {
                "request_count": {"value_count": {"field": "_id"}},
                "error_count": {
                    "filter": {
                        "bool": {
                            "should": [
                                {"range": {"http.response.status_code": {"gte": 400}}},
                                {"term": {"error.id": "*"}},
                            ]
                        }
                    }
                },
                "avg_latency": {
                    "avg": {"field": "event.duration"}
                },
            },
        }
        result = self._es.search(index="*", body=body)
        aggs = result.get("aggregations", {})
        request_count = aggs.get("request_count", {}).get("value", 0)
        error_count = aggs.get("error_count", {}).get("doc_count", 0)
        avg_latency_ns = aggs.get("avg_latency", {}).get("value")
        avg_latency_ms = (
            round(avg_latency_ns / 1_000_000, 2) if avg_latency_ns is not None else None
        )
        error_rate = (
            round(error_count / request_count, 4) if request_count > 0 else 0.0
        )
        return {
            "service_name": service_name,
            "time_range_minutes": time_range_minutes,
            "request_count": request_count,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency_ms,
        }

    def _get_active_alerts_sync(
        self,
        severity: str | None,
        max_results: int,
    ) -> dict:
        must_clauses: list[dict] = []
        if severity:
            must_clauses.append({"term": {"kibana.alert.severity": severity}})

        body = {
            "size": max_results,
            "query": {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}},
            "sort": [
                {"kibana.alert.severity": {"order": "asc"}},
                {"@timestamp": {"order": "desc"}},
            ],
        }
        result = self._es.search(index=self._alerts_index, body=body)
        hits = result.get("hits", {})
        alerts = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            alerts.append({
                "id": hit.get("_id"),
                "severity": source.get("kibana.alert.severity"),
                "status": source.get("kibana.alert.status"),
                "rule": source.get("kibana.alert.rule", {}).get("name"),
                "message": source.get("message"),
                "timestamp": source.get("@timestamp"),
            })
        return {
            "alerts": alerts,
            "total": hits.get("total", {}).get("value", 0),
            "severity_filter": severity,
        }


def _coerce_time_range(value: object) -> tuple[int, str | None]:
    """Clamp time_range_minutes into [1, MAX_TIME_RANGE_MINUTES]."""
    if value is None:
        return DEFAULT_TIME_RANGE_MINUTES, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIME_RANGE_MINUTES, (
            f"Parameter 'time_range_minutes' must be an integer, got {value!r}."
        )
    if parsed < 1:
        return DEFAULT_TIME_RANGE_MINUTES, (
            f"Parameter 'time_range_minutes' must be at least 1, got {parsed}."
        )
    return min(parsed, MAX_TIME_RANGE_MINUTES), None


def _coerce_max_results(value: object) -> tuple[int, str | None]:
    """Clamp max_results into [1, MAX_RESULTS]."""
    if value is None:
        return DEFAULT_MAX_RESULTS, None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_RESULTS, (
            f"Parameter 'max_results' must be an integer, got {value!r}."
        )
    if parsed < 1:
        return DEFAULT_MAX_RESULTS, (
            f"Parameter 'max_results' must be at least 1, got {parsed}."
        )
    return min(parsed, MAX_RESULTS), None


# --- Tool implementations ---


class SearchLogsTool(BaseTool):
    def __init__(self, connector: ElasticConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="elastic.search_logs",
            description="Search logs in Elastic using Kibana Query Language or simple text.",
            risk_level="read",
            category="observability",
            parameters_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (KQL or simple text).",
                    },
                    "index": {
                        "type": "string",
                        "description": "Elastic index pattern (default: *).",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TIME_RANGE_MINUTES,
                        "default": DEFAULT_TIME_RANGE_MINUTES,
                        "description": f"Look-back window in minutes (default {DEFAULT_TIME_RANGE_MINUTES}, max {MAX_TIME_RANGE_MINUTES}).",
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RESULTS,
                        "default": DEFAULT_MAX_RESULTS,
                        "description": f"Maximum number of results (default {DEFAULT_MAX_RESULTS}, max {MAX_RESULTS}).",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result(
                "elastic.search_logs", "ELASTIC_NOT_CONFIGURED",
                "Elastic connector is not configured.", source_system=SOURCE_SYSTEM,
            )

        query = parameters.get("query")
        if not query:
            return make_error_result(
                "elastic.search_logs", "INVALID_PARAMETERS",
                "Parameter 'query' is required.", source_system=SOURCE_SYSTEM,
            )

        index = parameters.get("index") or "*"
        time_range, tr_error = _coerce_time_range(parameters.get("time_range_minutes"))
        if tr_error:
            return make_error_result(
                "elastic.search_logs", "INVALID_PARAMETERS",
                tr_error, source_system=SOURCE_SYSTEM,
            )
        max_results, mr_error = _coerce_max_results(parameters.get("max_results"))
        if mr_error:
            return make_error_result(
                "elastic.search_logs", "INVALID_PARAMETERS",
                mr_error, source_system=SOURCE_SYSTEM,
            )

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(
                    self._connector._search_logs_sync,
                    query, index, time_range, max_results,
                ),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="elastic.search_logs",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("elastic.search_logs failed")
            return make_error_result(
                "elastic.search_logs", "ELASTIC_CONNECTION_ERROR",
                str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )


class GetServiceHealthTool(BaseTool):
    def __init__(self, connector: ElasticConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="elastic.get_service_health",
            description="Get aggregated health metrics for a service: error rate, avg latency, request count.",
            risk_level="read",
            category="observability",
            parameters_schema={
                "type": "object",
                "required": ["service_name"],
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service name (ECS service.name field).",
                    },
                    "time_range_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TIME_RANGE_MINUTES,
                        "default": DEFAULT_TIME_RANGE_MINUTES,
                        "description": f"Look-back window in minutes (default {DEFAULT_TIME_RANGE_MINUTES}, max {MAX_TIME_RANGE_MINUTES}).",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result(
                "elastic.get_service_health", "ELASTIC_NOT_CONFIGURED",
                "Elastic connector is not configured.", source_system=SOURCE_SYSTEM,
            )

        service_name = parameters.get("service_name")
        if not service_name:
            return make_error_result(
                "elastic.get_service_health", "INVALID_PARAMETERS",
                "Parameter 'service_name' is required.", source_system=SOURCE_SYSTEM,
            )

        time_range, tr_error = _coerce_time_range(parameters.get("time_range_minutes"))
        if tr_error:
            return make_error_result(
                "elastic.get_service_health", "INVALID_PARAMETERS",
                tr_error, source_system=SOURCE_SYSTEM,
            )

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(
                    self._connector._get_service_health_sync,
                    service_name, time_range,
                ),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="elastic.get_service_health",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("elastic.get_service_health failed")
            return make_error_result(
                "elastic.get_service_health", "ELASTIC_CONNECTION_ERROR",
                str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )


class GetActiveAlertsTool(BaseTool):
    def __init__(self, connector: ElasticConnector) -> None:
        self._connector = connector

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="elastic.get_active_alerts",
            description="List active alerts from Elastic, optionally filtered by severity.",
            risk_level="read",
            category="observability",
            parameters_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "warning", "info"],
                        "description": "Filter by alert severity (default: all).",
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RESULTS,
                        "default": DEFAULT_MAX_RESULTS,
                        "description": f"Maximum number of results (default {DEFAULT_MAX_RESULTS}, max {MAX_RESULTS}).",
                    },
                },
            },
        )

    async def execute(self, parameters: dict, identity: dict) -> ToolResult:
        start = time.perf_counter()
        if not self._connector._ensure_client():
            return make_error_result(
                "elastic.get_active_alerts", "ELASTIC_NOT_CONFIGURED",
                "Elastic connector is not configured.", source_system=SOURCE_SYSTEM,
            )

        severity = parameters.get("severity")
        if severity is not None and severity not in {"critical", "warning", "info"}:
            return make_error_result(
                "elastic.get_active_alerts", "INVALID_PARAMETERS",
                f"Parameter 'severity' must be one of: critical, warning, info. Got {severity!r}.",
                source_system=SOURCE_SYSTEM,
            )

        max_results, mr_error = _coerce_max_results(parameters.get("max_results"))
        if mr_error:
            return make_error_result(
                "elastic.get_active_alerts", "INVALID_PARAMETERS",
                mr_error, source_system=SOURCE_SYSTEM,
            )

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                None,
                partial(
                    self._connector._get_active_alerts_sync,
                    severity, max_results,
                ),
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                tool_name="elastic.get_active_alerts",
                status="success",
                data=data,
                evidence=build_evidence("read", SOURCE_SYSTEM, duration_ms),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            LOGGER.exception("elastic.get_active_alerts failed")
            return make_error_result(
                "elastic.get_active_alerts", "ELASTIC_CONNECTION_ERROR",
                str(exc), source_system=SOURCE_SYSTEM, duration_ms=duration_ms,
            )
