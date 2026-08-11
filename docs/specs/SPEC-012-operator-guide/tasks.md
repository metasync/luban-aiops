# SPEC-012 Tasks: Operator Guide and Deployment Documentation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Getting Started Guide

- [x] Create `docs/guides/` directory and `README.md` index
- [x] Write prerequisites section (Kubernetes, kubectl, make, Docker/Podman)
- [x] Write build and deploy walkthrough (`make build`, `make deploy`, image loading)
- [x] Write secrets provisioning section: LLM API key (`sync-runtime-secret.sh`), token delegation (`sync-delegation-secrets.sh`), OIDC client secret
- [x] Write end-to-end verification checklist (portal login → session → agent reply → tool invocation → evidence panel)
- [x] Include the token delegation troubleshooting tip (check `delegation_exchange_total` metric)

## R-2: Configuration Reference

- [x] Write feature activation matrix: table mapping capabilities to required env vars and secrets
- [x] Document cross-service dependency chains (token delegation, tool relay, identity flow)
- [x] Compile per-service env var tables from `runtime-config.env` files and source code defaults
- [x] Document secret contracts from `runtime-secrets.example.env` files
- [x] Document policy management workflow: canonical source → `make sync-policy` → ConfigMap deploy; reference `make validate-policy` for schema validation

## R-3: Troubleshooting Guide

- [x] Write symptom: "agent says access not granted" (delegation secrets missing)
- [x] Write symptom: "agent has no tools available" (`TOOL_GATEWAY_URL` unset or delegation failure)
- [x] Write symptom: "portal login fails" (OIDC misconfiguration, Keycloak unreachable)
- [x] Write symptom: "stream never completes" (agent-service unconfigured, no API key)
- [x] Write symptom: "tool returns denied by policy" (user role lacks `tools:invoke`)
- [x] Write symptom: "tool returns ELASTIC_NOT_CONFIGURED" (Elastic connector not enabled)
- [x] Include diagnostic command patterns (kubectl logs, curl health/metrics, port-forward)

## R-4: Tool and Connector Guide

- [x] Write tool inventory table (tool name, description, parameters, risk level)
- [x] Write K8s connector activation checklist (`GATEWAY_K8S_ENABLED`, namespace, RBAC)
- [x] Write Elastic connector activation checklist (all 7 env vars, auth options, network)
- [x] Write "adding a new connector" section (brief, pointing to SPEC-007/SPEC-011 pattern)

## R-5: Architecture Overview

- [x] Write service topology section (6 services with roles and ownership boundaries)
- [x] Create Mermaid service topology diagram
- [x] Write request flow section (portal → platform-gateway → agent-service → tool-gateway → connector)
- [x] Create Mermaid request flow diagram
- [x] Write trust chain section (OIDC → platform JWT → delegated token → tool invocation)
- [x] Write RBAC model section (roles, actions, policy bundle)

## Delivery Gate

- [x] living state docs updated:
  - [x] `docs/specs/README.md` — spec index updated with SPEC-012
  - [x] `CHANGELOG.md` — Unreleased entry referencing SPEC-012
- [x] `make sync-policy` target: copy canonical `policy-default.yaml` to all consumer locations
- [x] `make validate-policy` target: validate canonical bundle against `policy-rule.schema.json`, wired into `make verify`
- [x] `make verify` green (all product tests + all overlay renders + policy validation)
- [x] spec status set to `delivered`
