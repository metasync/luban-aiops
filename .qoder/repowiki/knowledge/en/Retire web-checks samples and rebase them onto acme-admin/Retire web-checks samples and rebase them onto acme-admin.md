---
kind: design
name: Retire web-checks samples and rebase them onto acme-admin
source: session
category: adr
---

# Retire web-checks samples and rebase them onto acme-admin

_Source: coding plans from commit period 9360da4 → 6bbe5cd — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The `web-checks` sample suite used a static mock target that could not teach verification against real state. SPEC-059 had already built `acme-admin` with R-2 compatibility (same six URL shapes, same 28 element ids) specifically so the three `web-checks` samples could be retargeted without rewriting them.

## Decision drivers
- teach verification against real store state
- avoid duplicate admin UIs
- zero rewrite migration via R-2 contract

## Considered options
- **Keep web-checks as-is alongside acme-admin** _(rejected)_ — pros: no migration cost; cons: static targets cannot demonstrate real verification; two overlapping admin portals to maintain
- **Migrate adhoc-password-reset + skill-graduation to acme-admin and retire web-checks/password-reset** — pros: single admin target, real-store verification, consolidates samples under one umbrella; cons: retires a shipped sample id (`samples/password-reset-resetuserpassword`); requires updating demos, docs, and catalog

## Decision
Move `adhoc-password-reset` and `skill-graduation` into `samples/acme-admin/`, retire `samples/web-checks/password-reset/` (superseded by `acme-admin/password-reset`), and keep `browser-check-target` only for platform consumers (InventoryHealth runbook, e2e script, allowlist, credential sets). Leaf directory names are preserved so skill ids stay stable.

## Consequences
`acme-admin/password-reset` becomes the sole bound-flow reset sample; both migrated demos now source `demo-lib.sh` from `samples/acme-admin/` and verify resets against `/api/users/{u}` revision bumps and `password_changed_at`. The `samples/web-checks/` category is retired, reducing the shipped sample count from six to five distinct ids. Platform consumers of `browser-check-target` remain unaffected.