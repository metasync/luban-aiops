---
kind: design
name: Reconcile password-reset demo to a single gate on 'Confirm reset'
source: session
category: adr
---

# Reconcile password-reset demo to a single gate on 'Confirm reset'

_Source: coding plans from commit period 33e6a7f → 123c4b6 — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The skill/README/WALKTHROUGH declared the admin sign-in click as the single write, but both `admin-index.html` and `admin-reset-index.html` auto-submitted their forms, creating a three-way contradiction that drove the model to issue extra writes and produce multiple cards.

## Decision drivers
- align pages, skill, docs, and demo script around one destructive mutation
- keep authentication read-tier
- make the demo deterministic under `make verify`

## Considered options
- **Gate on login click** _(rejected)_ — pros: matches original intent; cons: login auto-submit races/stales; not the destructive action
- **Gate on Confirm reset click** — pros: gates the actual mutation; pages already comment this is the intended gate; login stays read-tier via auto-submit; cons: requires removing the reset form's auto-submit JS

## Decision
Remove the auto-submit block from `admin-reset-index.html`, keep login auto-submit as read-tier, and update the skill, README, WALKTHROUGH, and `demo.sh` to assert exactly one card on the final `web.click` of 'Confirm reset'.

## Consequences
The demo exercises exactly one HITL gate and produces a signed receipt, satisfying SPEC-051 R-4 and the delivery traceability gate. Any future changes must keep login read-tier and the reset click as the sole write.