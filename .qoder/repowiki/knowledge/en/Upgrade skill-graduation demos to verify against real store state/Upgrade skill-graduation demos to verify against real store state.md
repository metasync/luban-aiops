---
kind: design
name: Upgrade skill-graduation demos to verify against real store state
source: session
category: adr
---

# Upgrade skill-graduation demos to verify against real store state

_Source: coding plans from commit period 9360da4 → 6bbe5cd — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The original `skill-graduation` demo validated behavior by grepping static pages on the mock target, which does not prove that writes actually persisted. After rebasing onto `acme-admin`, the demo can call the real API.

## Decision drivers
- demonstrate real persistence verification
- mirror the pattern in `ResetAcmePassword` step 9
- keep deterministic legs intact

## Considered options
- **Continue page-grep verification against the mock target** _(rejected)_ — pros: minimal change; cons: does not prove data landed; contradicts the lesson that static mocks are not verification
- **Add store-verification legs querying `/api/users/{alice,bob}` for revision bump and `password_changed_at`** — pros: proves writes persisted; aligns with the password-reset sample's approach; cons: adds API calls to the demo but keeps all deterministic legs unchanged

## Decision
Call `reseed_demo` before act 1 and add post-act verification legs that assert both resets landed in the store via the users API, while preserving the existing deterministic legs 1–6 and signed-receipt assertions.

## Consequences
The demo now exercises real write paths end-to-end, making it a stronger teaching example for approval-model authoring. It depends on `acme-admin` being deployed with its user store reachable during tests.