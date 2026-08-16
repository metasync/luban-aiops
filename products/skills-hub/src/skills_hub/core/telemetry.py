"""Opt-in OpenTelemetry push pipeline (SPEC-005 R-3/R-4).

Gated by OTEL_ENABLED (default false): when disabled nothing is initialized
and the /metrics surface is unaffected. Fail-open: setup errors are logged,
never raised into the request path. Conventions:
shared/shared-contracts/observability-conventions.md.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

LOGGER = logging.getLogger(__name__)

_providers_initialized = False


def _flag_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    """True when the OTel push pipeline is switched on via OTEL_ENABLED."""
    return _flag_enabled(os.getenv("OTEL_ENABLED"))


def setup_telemetry(app: FastAPI, service_name: str) -> None:
    """Initialize traces + metrics push to the configured OTLP endpoint."""
    global _providers_initialized
    if not is_enabled():
        return
    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        if not _providers_initialized:
            resource = Resource.create(
                {"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)}
            )
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            trace.set_tracer_provider(tracer_provider)

            reader = PeriodicExportingMetricReader(OTLPMetricExporter())
            otel_metrics.set_meter_provider(
                MeterProvider(resource=resource, metric_readers=[reader])
            )
            HTTPXClientInstrumentor().instrument()
            _providers_initialized = True

        FastAPIInstrumentor.instrument_app(app)
        LOGGER.info(
            "otel telemetry enabled",
            extra={
                "service_name": service_name,
                "endpoint": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            },
        )
    except Exception:
        LOGGER.exception("otel telemetry setup failed; continuing without push")


def current_trace_id() -> str | None:
    """Return the active span's W3C trace_id (32 hex chars), if tracing is on."""
    if not is_enabled():
        return None
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            return format(context.trace_id, "032x")
    except Exception:
        return None
    return None
