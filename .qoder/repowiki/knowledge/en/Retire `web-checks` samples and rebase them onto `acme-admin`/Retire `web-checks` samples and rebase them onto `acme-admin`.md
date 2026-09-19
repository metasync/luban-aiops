---
kind: design
name: Retire `web-checks` samples and rebase them onto `acme-admin`
source: session
category: adr
---

# Retire `web-checks` samples and rebase them onto `acme-admin`

_Source: coding plans from commit period d808173 → 9360da4 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The `samples/web-checks/` samples (`password-reset`, `adhoc-password-reset`, `skill-graduation`) were built against a static mock target that could not teach verification. SPEC-059 had already rebuilt `acme-admin` with R-2 compatibility (same six URL shapes, same 28 element ids) specifically so these samples could be retargeted without a rewrite. This period executes that follow-up.

## Decision drivers
- teach verification against real store state rather than static HTML
- consolidate samples under the single shipped admin target
- preserve existing skill ids to avoid breaking downstream references

## Considered options
- **Keep `web-checks` samples on the static `browser-check-target`** _(rejected)_ — pros: minimal churn; cons: cannot assert mutations; teaches false confidence in page greps alone
- **Migrate all three samples onto `acme-admin` while keeping `web-checks/password-reset` as a duplicate** _(rejected)_ — pros: backward compat for old paths; cons: duplicates bound-flow reset coverage already provided by `acme-admin/password-reset`; adds maintenance burden
- **Migrate `adhoc-password-reset` + `skill-graduation` onto `acme-admin` and retire `web-checks/password-reset`** — pros: single source of truth for password-reset demos; enables store-backed verification; keeps `browser-check-target` alive for InventoryHealth/platform e2e consumers

## Decision
Move `adhoc-password-reset` and `skill-graduation` into `samples/acme-admin/`, retire `samples/web-checks/password-reset`, and upgrade both demos to verify changes against the real `/api/users/{u}` store (revision bump + `password_changed_at`). Keep `browser-check-target` shipped and untouched since it is still consumed by platform runbooks and e2e scripts.

## Consequences
The `samples/web-checks/` category disappears from the catalog; `acme-admin/password-reset` becomes the sole bound-flow reset sample. Skill ids remain stable because leaf directory names are preserved. The migrated demos now depend on `acme-admin` being deployed and require store access for their post-approval legs, raising the bar for demo reliability at the cost of slightly more setup.