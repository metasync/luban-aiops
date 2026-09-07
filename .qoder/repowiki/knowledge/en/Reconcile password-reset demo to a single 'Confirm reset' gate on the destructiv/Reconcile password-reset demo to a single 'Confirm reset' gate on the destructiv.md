---
kind: design
name: Reconcile password-reset demo to a single 'Confirm reset' gate on the destructive mutation
source: session
category: adr
---

# Reconcile password-reset demo to a single 'Confirm reset' gate on the destructive mutation

_Source: coding plans from commit period e252f12 → 6359eeb — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The skill, README, WALKTHROUGH, and pages disagreed about which action was the single write: docs said admin sign-in click, but both `admin-index.html` and `admin-reset-index.html` auto-submitted their forms, causing races and extra writes. The demo script had been patched to tolerate two cards instead of fixing the root cause.

## Decision drivers
- single destructive gate per flow
- login stays read-tier
- deterministic demo assertion (exactly one card)

## Considered options
- **Gate on login click (as docs originally stated)** _(rejected)_ — pros: minimal page changes; cons: login is not the destructive mutation; pages auto-submit it anyway
- **Gate on 'Confirm reset' click (pages comment already describes this)** — pros: gates the actual mutation; login remains read-tier auto-submit; matches page comments; cons: requires removing auto-submit from reset page and updating skill/docs/demo

## Decision
Remove the auto-submit block from `admin-reset-index.html`, keep login auto-submit as read-tier, and make `web.click 'Confirm reset'` the sole write-tier interaction. Update the skill frontmatter, procedure, README/WALKTHROUGH narrative, and `demo.sh` to assert exactly one card whose execution is a signed `web.click` receipt.

## Consequences
Demo now deterministically produces one approval card on the destructive action; skill/docs/pages are aligned. The change is isolated to the sample and its supporting pages — no platform behavior change beyond what the flow-unlock enables.