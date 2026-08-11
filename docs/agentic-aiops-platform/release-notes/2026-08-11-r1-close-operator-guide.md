# Release Notes: 2026-08-11 — R1 Close (Operator Guide and Deployment Documentation)

## Summary

SPEC-012 closes Release 1 with operator-facing documentation that bridges the
gap between developer specs (SPEC-001–011) and the operational knowledge
required to deploy, configure, verify, and troubleshoot the platform in a
local or staging Kubernetes cluster.

With this delivery, **all 12 Release 1 specs are delivered** (SPEC-001
through SPEC-012). The release completion signal — "operators say the platform
is useful for real status and diagnostic questions" — can now be validated
with real users using these guides.

`make verify` is green: all product tests (agent-platform 122, tool-gateway
109, platform-gateway 77, identity-broker 49), all four Kustomize overlays
render cleanly, and the new policy validation target confirms the four-rule
deny-by-default bundle.

## Change Set 1: Operator Guide Suite (SPEC-012)

### Highlights

- `docs/guides/getting-started.md` (R-1): seven-step walkthrough from
  prerequisites (Kubernetes, kubectl, make, Docker, uv, jq) through clone,
  profile selection, API key provisioning, build, deploy, pod verification,
  and portal access. Includes an end-to-end verification checklist and
  secrets summary table
- `docs/guides/configuration-reference.md` (R-2): feature activation matrix
  (10 capabilities mapped to env vars and services), three cross-service
  dependency chains (token delegation, identity verification, tool relay)
  with ASCII diagrams, per-service environment variable tables (60+ variables
  across 4 Python services), secret contracts, runtime profiles, and the
  policy management workflow
- `docs/guides/troubleshooting.md` (R-3): nine symptom-based diagnostics
  covering access-not-granted, no-tools, login failures, stream stalls,
  policy denial, Elastic not configured, ErrImagePull, policy load failure,
  and token expiry — each with likely cause, diagnostic commands, and
  resolution steps
- `docs/guides/tool-configuration.md` (R-4): tool inventory (7 read-only
  tools: 4 Kubernetes + 3 Elastic), per-connector activation checklists
  with RBAC YAML examples, redaction engine reference, and a seven-step
  extension guide for adding new connectors
- `docs/guides/architecture-overview.md` (R-5): service topology table,
  Mermaid diagrams for service topology graph and request flow sequence,
  trust chain (OIDC → platform JWT → delegated token → tool invocation),
  token delegation flow with env var matching, workload identity upgrade
  path, and RBAC model (5 roles, 5 protected actions, 4 default allow rules)
- `docs/guides/README.md`: guide index and navigation page

### Why It Matters

- the knowledge that was scattered across 5 product READMEs, 11 spec
  documents, the dev-k8s overlay, and the CHANGELOG is now consolidated in
  task-oriented operator guides
- the token delegation chain — the most common silent-failure path — is
  documented with an ASCII diagram showing the exact env var pairs that must
  match across platform-gateway and identity-service

## Change Set 2: Policy Management Tooling

### Highlights

- `make sync-policy`: copies the canonical `policy-default.yaml` from
  `shared/shared-contracts/policies/` to all three consumer locations
  (tool-gateway, platform-gateway, dev-k8s ConfigMap) — prevents drift
  across the four byte-identical copies
- `make validate-policy`: validates the canonical bundle against
  `policy-rule.schema.json` using JSON Schema Draft 2020-12; checks
  version, non-empty rules list, and duplicate rule IDs
- `validate-policy` is wired into `make verify` as a quality gate —
  every pre-commit/pre-push run confirms the policy bundle is well-formed

### Why It Matters

- policy drift between the four copies was a latent risk; `sync-policy`
  makes the canonical-to-consumer relationship explicit and mechanical
- the validation gate catches schema violations before deployment rather
  than at service startup

## Known Limitations

- the guides target the dev-k8s overlay (kind/local cluster); production
  hardening (network policies, ingress, HA Redis, cloud-specific guides)
  is deferred to a future spec
- the operator guide describes the current read-only tool surface; new
  connectors added in future releases will need corresponding updates to
  `tool-configuration.md` and `configuration-reference.md`
- the authoritative audit trail remains in pod logs only; a durable
  queryable audit API is a future spec (SPEC-013+)

## Related Documents

- `../../specs/SPEC-012-operator-guide/spec.md`
- `../../guides/README.md`
- `../../specs/README.md` (spec index, all 12 specs delivered)
- `../../../CHANGELOG.md`
