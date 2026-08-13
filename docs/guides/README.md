# Operator Guides

Operator-facing documentation for deploying, configuring, verifying, and troubleshooting the
Luban AIOps platform.

## Guides

| Guide | Description |
|---|---|
| [Getting Started](getting-started.md) | From cluster to working portal in 7 steps |
| [Configuration Reference](configuration-reference.md) | Environment variables, secrets, and cross-service dependencies |
| [Tool and Connector Guide](tool-configuration.md) | Tool inventory, K8s/Elastic activation checklists, audit-service activation, adding new connectors |
| [Architecture Overview](architecture-overview.md) | Service topology, request flow, trust chain, RBAC model |
| [Troubleshooting](troubleshooting.md) | Symptom-based diagnostics for common deployment and runtime issues |

## Quick Start

1. Follow the [Getting Started](getting-started.md) walkthrough
2. Use the [Configuration Reference](configuration-reference.md) to tune settings
3. Enable additional connectors via the [Tool and Connector Guide](tool-configuration.md)
4. Consult [Troubleshooting](troubleshooting.md) when something breaks

## Related Documentation

- [Delivery Roadmap](../agentic-aiops-platform/delivery-roadmap.md) — release sequence and themes
- [Policy Specification](../agentic-aiops-platform/policy-specification.md) — full policy model
- [Authorization Matrix](../agentic-aiops-platform/authorization-matrix.md) — role-to-action mapping
- [Spec Index](../specs/README.md) — implementation specs (SPEC-001 through SPEC-013)
- [Dev K8s Overlay](../../shared/platform-ops/gitops/dev-k8s/README.md) — deployer's reference
