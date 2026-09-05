---
kind: design
name: Gate the password-reset demo on 'Confirm reset' rather than admin sign-in
source: session
category: adr
---

# Gate the password-reset demo on 'Confirm reset' rather than admin sign-in

_Source: coding plans from commit period c66ad9a → 7eee39a — records intent at planning time; the implementation may lag or differ._

**Status:** accepted

## Context
The password-reset skill/README/WALKTHROUGH declared the admin sign-in click as the single write, but `admin-index.html` auto-submitted login when both fields filled, `admin-reset-index.html` auto-submitted the reset too, and the pages' own comment said the gate should be on 'Confirm reset.' This three-way contradiction caused the model to improvise extra writes → multiple cards, and `demo.sh` was patched to tolerate a second card instead of fixing the cause.

## Decision drivers
- align skill, pages, README, WALKTHROUGH, and demo script to one destructive gate
- keep authentication read-tier (auto-submit is harmless)
- make the demo deterministic so `demo.sh` asserts exactly one card

## Considered options
- **Keep the gate on admin sign-in click** _(rejected)_ — pros: minimal page changes; cons: login auto-submit races/stales the click; contradicts the pages' own comment; leaves the destructive reset un-gated
- **Remove all auto-submit JS from both pages** _(rejected)_ — pros: fully explicit user actions; cons: unnecessary friction for read-only login; breaks expected UX
- **Remove auto-submit only from the reset page; keep login auto-submit as read-tier** — pros: gates the destructive mutation ('Confirm reset'); login stays frictionless; matches the pages' documented intent; makes `demo.sh` assert exactly one `web.click` card; cons: requires updating skill, README, WALKTHROUGH, and demo assertions

## Decision
Remove the auto-submit block from `admin-reset-index.html` while keeping the URL auto-fill and the login auto-submit in `admin-index.html`. The gate moves to the final 'Confirm reset' click, which is the sole write-tier interaction. Update `ResetUserPassword.md`, `README.md`, `WALKTHROUGH.md`, and `demo.sh` to assert exactly one card whose `executions[0].tool_name == 'web.click'`.

## Consequences
The demo now deterministically produces one approval card on the destructive action; `demo.sh` no longer tolerates a second card. Authentication remains frictionless via auto-submit. The skill documentation now correctly describes the gate location.