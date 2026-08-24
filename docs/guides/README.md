# Operator Guides

Operator-facing documentation for deploying, configuring, verifying, and troubleshooting the
Luban AIOps platform.

## Guides

| Guide | Description |
|---|---|
| [Getting Started](getting-started.md) | From cluster to working portal in 7 steps |
| [Portal User Guide](portal-user-guide.md) | Day-2 portal usage: chat, voice, model selection, sessions, evidence, approvals, Control and Workspace views |
| [User and Role Administration](user-and-role-administration.md) | Adding users, assigning roles in Keycloak, and mapping roles to permissions |
| [Configuration Reference](configuration-reference.md) | Environment variables, secrets, and cross-service dependencies |
| [Approval and HITL Governance](approval-and-hitl.md) | Four-layer approval model, auto-allow management, policy bundle workflow, HITL configuration knobs |
| [Tool and Connector Guide](tool-configuration.md) | Tool inventory, K8s/Elastic/skills activation checklists, audit-service activation, adding new connectors |
| [Adding a Tool to the Tool Gateway](adding-a-tool.md) | Contributor walkthrough: connector class, tool definition, error envelope, wiring, authorization, tests |
| [Skills and Guidance Guide](skills-guide.md) | Managing skill content: add, revise, remove skills and sources; verification and troubleshooting |
| [Incident Triage and Collaboration Guide](incident-guide.md) | Alertmanager wiring, incident lifecycle, running and interpreting triage, collaboration semantics |
| [Luban-Hosted Small Model Guide](luban-llm-guide.md) | Self-hosting a small LLM (Ollama/vLLM/llama.cpp) with token auth, platform wiring, K8s hosting |
| [Architecture Overview](architecture-overview.md) | Service topology, request flow, trust chain, RBAC model |
| [Troubleshooting](troubleshooting.md) | Symptom-based diagnostics for common deployment and runtime issues |

## Quick Start

1. Follow the [Getting Started](getting-started.md) walkthrough
2. Learn the portal itself with the [Portal User Guide](portal-user-guide.md)
3. Use the [Configuration Reference](configuration-reference.md) to tune settings
4. Enable additional connectors via the [Tool and Connector Guide](tool-configuration.md)
5. Govern tool auto-allow and approvals via the [Approval and HITL Governance Guide](approval-and-hitl.md)
6. Consult [Troubleshooting](troubleshooting.md) when something breaks

## Related Documentation

- [Delivery Roadmap](../agentic-aiops-platform/delivery-roadmap.md) — release sequence and themes
- [Policy Specification](../agentic-aiops-platform/policy-specification.md) — full policy model
- [Authorization Matrix](../agentic-aiops-platform/authorization-matrix.md) — role-to-action mapping
- [Spec Index](../specs/README.md) — implementation specs and their delivery status
- [Dev K8s Overlay](../../shared/platform-ops/gitops/dev-k8s/README.md) — deployer's reference
