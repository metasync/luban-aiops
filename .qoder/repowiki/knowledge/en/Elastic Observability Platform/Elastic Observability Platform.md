---
kind: external_dependency
name: Elastic Observability Platform
slug: elastic-stack
category: external_dependency
category_hints:
    - vendor_identity
    - auth_protocol
scope:
    - '**'
source_files:
    - shared/shared-contracts/observability-conventions.md
---

Elastic Stack serves as the observability backend for the platform, accepting OTLP-native telemetry (traces, metrics, logs) from all three Python services. The platform uses OpenTelemetry SDKs to push data to Elastic APM Server or OTel Collector endpoints configured via OTEL_EXPORTER_OTLP_ENDPOINT environment variable. The observability pipeline is opt-in via OTEL_ENABLED switch, failing open when the collector is unreachable, while maintaining a separate Prometheus /metrics surface for zero-dependency debugging.