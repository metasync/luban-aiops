---
kind: design
name: Reconcile password-reset demo to a single gate on Confirm reset
source: session
category: adr
---

# Reconcile password-reset demo to a single gate on Confirm reset

_Source: coding plans from commit period 545a4fc → 33e6a7f — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The skill, README, WALKTHROUGH, and demo script declared the admin sign-in click as the single write, but admin-index.html auto-submitted login when both fields were filled and admin-reset-index.html also auto-submitted the reset — a three-way contradiction that caused the model to improvise extra writes and produce multiple approval cards.

## Decision drivers
- single destructive mutation should be gated
- login is read-tier and can stay auto-submitted
- demo must exercise the spec under make verify

## Considered options
- **Gate login (remove auto-submit from admin-index.html)** _(rejected)_ — pros: gates authentication; cons: login is not the destructive mutation; removing auto-submit would degrade UX without security benefit
- **Gate reset confirmation (remove auto-submit from admin-reset-index.html)** — pros: the reset click is the only destructive mutation; matches the page's existing comment; keeps login auto-submit as read-tier

## Decision
Remove the auto-submit block from admin-reset-index.html and keep the URL pre-fill; the single write-tier interaction becomes web.click on Confirm reset. Update the skill, README, WALKTHROUGH, and demo.sh to assert exactly one card whose execution targets that click.

## Consequences
The demo now produces one approval card for the destructive action, matching the intended trust model. The test asserts len(cards) == 1 and verifies a signed receipt, closing the gap that previously tolerated a second card.