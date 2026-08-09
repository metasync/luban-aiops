# SPEC-012 Technical Plan

## Approach

The operator guide is a set of 5 task-oriented documents plus an index, living under `docs/guides/`. Each document targets a specific operator persona and task:

| Document | Persona | Task |
|---|---|---|
| `getting-started.md` | New deployer | First deployment and verification |
| `configuration-reference.md` | Platform engineer | Understand and tune settings |
| `troubleshooting.md` | On-call operator | Diagnose and fix issues |
| `tool-configuration.md` | Platform engineer | Enable and configure connectors |
| `architecture-overview.md` | New team member | Understand the platform topology |

## Sequencing

Two parallel tracks:

1. **Foundation** (R-5 → R-2): architecture overview first (informs all other docs), then configuration reference (extracts from existing READMEs and source code)
2. **Task guides** (R-1 → R-3 → R-4): getting started (most impactful), troubleshooting, then tool configuration

## Content Sourcing

Each document draws from existing sources:

| Source | Content extracted |
|---|---|
| Product READMEs (×5) | Per-service env vars, purpose, boundaries |
| `dev-k8s/README.md` | Build/deploy/verify commands, secrets workflow, runtime wiring |
| SPEC-007..011 `spec.md` files | Feature descriptions, design decisions, acceptance criteria |
| `runtime-config.env` files (×5) | Actual deployed env vars and defaults |
| `runtime-secrets.example.env` files | Secret contracts |
| `policy.yaml` | RBAC actions and role mappings |
| Source code (`config.py`, `runtime_settings.py`) | Default values, validation rules |

## Key Decisions

- **Q-1**: Use Mermaid diagrams for architecture and flow. GitHub renders them natively; the text-only fallback is the prose description that accompanies each diagram.
- **Q-2**: The `sync-delegation-secrets.sh` script is a standalone fix (already shipped). R-1 documents its usage but does not claim ownership of the script.

## File Layout

```
docs/guides/
  README.md                       # index (R-1 delivery)
  getting-started.md              # R-1
  configuration-reference.md      # R-2
  troubleshooting.md              # R-3
  tool-configuration.md           # R-4
  architecture-overview.md        # R-5
```

## Verification

- `make verify` green (existing gate; docs do not affect test suites)
- Manual review: each guide is cross-checked against the actual dev-k8s overlay configuration and source code defaults
- Spec index updated, CHANGELOG entry added, spec status set to `delivered`
