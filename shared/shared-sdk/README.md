# Shared SDK

## Purpose

`shared-sdk` contains shared libraries that help product projects consume common contracts and platform services consistently.

Typical contents include:

- service clients
- auth helpers
- tracing helpers
- typed event producers and consumers

## Ownership

Recommended owner:

- platform architecture or core platform team

## Current Scope

This module currently provides the workspace placeholder and boundary definition for:

- shared service clients
- reusable auth and tracing helpers
- typed event producer and consumer utilities
- integration helpers built on stable shared contracts

## Current Status (2026-11-15)

**No library code ships here yet — that is a deliberate, recorded decision, not an oversight.** The cross-cutting helpers this README describes (tracing/telemetry, auth, service clients) live today as *intentional per-product copies* under each `products/<name>/src/<package>/`, pinned in lockstep by the AST-normalized drift guard [`test_module_parity.py`](../../products/tool-gateway/tests/test_module_parity.py) (live in `make verify`):

- `core/telemetry.py` — byte-identical across all eight Python services
- `core/observability.py` — identical except per-service docstrings
- `services/token_verifier.py` — identical except the package / settings class names (platform-gateway / tool-gateway)
- `services/audit_emitter.py` — identical except docstrings and package / settings names (six services; incident-service's triage connector is a different design and is excluded)
- `services/ingest_auth.py` (audit-service) / `services/query_auth.py` (incident-service) — identical except names

Extracting these into a packaged `shared-sdk` was spiked and **deferred** in [`shared-sdk-extraction-spike.md`](../../docs/workspace/shared-sdk-extraction-spike.md) (2026-08-25): a packaging skeleton, an eight-lockfile ripple, and widened Docker build contexts are not yet earned against a small (~400 unique-line), slow-churning, already-drift-guarded surface. The memo's **revisit trigger #1 fired 2026-11-15** (the audit-emitter family reached six copies as the eighth product enrolled); the deferral was **re-confirmed** on the [Exploration Backlog row](../../docs/agentic-aiops-platform/delivery-roadmap.md#exploration-backlog). Practical rule: to change one of these modules, edit **every** copy in the same commit (the parity suite fails otherwise) — never seed the first file here piecemeal.

## Expected Integration Points

- `shared/shared-contracts` for canonical schemas
- `products/` modules that consume common service clients or helpers
- `shared/platform-ops` when deployment or runtime conventions require shared client behavior

## Boundary

This module should support reuse, but should not become a catch-all layer for unrelated platform logic.
