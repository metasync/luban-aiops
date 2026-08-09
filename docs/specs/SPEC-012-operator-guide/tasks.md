# SPEC-012 Tasks: Operator Guide and Deployment Documentation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Getting Started Guide

- [ ] Create `docs/guides/` directory and `README.md` index
- [ ] Write prerequisites section (Kubernetes, kubectl, make, Docker/Podman)
- [ ] Write build and deploy walkthrough (`make build`, `make deploy`, image loading)
- [ ] Write secrets provisioning section: LLM API key (`sync-runtime-secret.sh`), token delegation (`sync-delegation-secrets.sh`), OIDC client secret
- [ ] Write end-to-end verification checklist (portal login → session → agent reply → tool invocation → evidence panel)
- [ ] Include the token delegation troubleshooting tip (check `delegation_exchange_total` metric)

## R-2: Configuration Reference

- [ ] Write feature activation matrix: table mapping capabilities to required env vars and secrets
- [ ] Document cross-service dependency chains (token delegation, tool relay, identity flow)
- [ ] Compile per-service env var tables from `runtime-config.env` files and source code defaults
- [ ] Document secret contracts from `runtime-secrets.example.env` files

## R-3: Troubleshooting Guide

- [ ] Write symptom: "agent says access not granted" (delegation secrets missing)
- [ ] Write symptom: "agent has no tools available" (`TOOL_GATEWAY_URL` unset or delegation failure)
- [ ] Write symptom: "portal login fails" (OIDC misconfiguration, Keycloak unreachable)
- [ ] Write symptom: "stream never completes" (agent-service unconfigured, no API key)
- [ ] Write symptom: "tool returns denied by policy" (user role lacks `tools:invoke`)
- [ ] Write symptom: "tool returns ELASTIC_NOT_CONFIGURED" (Elastic connector not enabled)
- [ ] Include diagnostic command patterns (kubectl logs, curl health/metrics, port-forward)

## R-4: Tool and Connector Guide

- [ ] Write tool inventory table (tool name, description, parameters, risk level)
- [ ] Write K8s connector activation checklist (`GATEWAY_K8S_ENABLED`, namespace, RBAC)
- [ ] Write Elastic connector activation checklist (all 7 env vars, auth options, network)
- [ ] Write "adding a new connector" section (brief, pointing to SPEC-007/SPEC-011 pattern)

## R-5: Architecture Overview

- [ ] Write service topology section (6 services with roles and ownership boundaries)
- [ ] Create Mermaid service topology diagram
- [ ] Write request flow section (portal → platform-gateway → agent-service → tool-gateway → connector)
- [ ] Create Mermaid request flow diagram
- [ ] Write trust chain section (OIDC → platform JWT → delegated token → tool invocation)
- [ ] Write RBAC model section (roles, actions, policy bundle)

## Delivery Gate

- [ ] living state docs updated:
  - [ ] `docs/specs/README.md` — spec index updated with SPEC-012
  - [ ] `CHANGELOG.md` — Unreleased entry referencing SPEC-012
- [ ] `make verify` green (all product tests + all overlay renders)
- [ ] spec status set to `delivered`
