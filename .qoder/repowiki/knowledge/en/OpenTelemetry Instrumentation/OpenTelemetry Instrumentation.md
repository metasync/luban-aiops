---
kind: external_dependency
name: OpenTelemetry Instrumentation
slug: opentelemetry
category: external_dependency
category_hints:
    - sdk_real_api
    - framework_behavior
scope:
    - '**'
source_files:
    - products/agent-platform/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/identity-broker/pyproject.toml
---

All three Python services use OpenTelemetry SDKs for distributed tracing and metrics collection. The implementation includes opentelemetry-exporter-otlp for OTLP export, opentelemetry-instrumentation-fastapi for automatic FastAPI instrumentation, and opentelemetry-instrumentation-httpx for HTTP client tracing. The OTel pipeline is gated by OTEL_ENABLED environment variable and fails open when the collector endpoint is unavailable, maintaining backward compatibility with the existing Prometheus /metrics surface.