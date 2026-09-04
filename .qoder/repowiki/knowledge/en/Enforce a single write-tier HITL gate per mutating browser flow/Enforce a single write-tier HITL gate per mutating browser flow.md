---
kind: design
name: Enforce a single write-tier HITL gate per mutating browser flow
source: session
category: adr
---

# Enforce a single write-tier HITL gate per mutating browser flow

_Source: coding plans from commit period b4f66c1 → c66ad9a — records intent at planning time; the implementation may lag or differ._

## Context
The password-reset tutorial must demonstrate a multi-step mutating workflow while keeping the operator experience simple. The existing agent model treats `web.click` as write-tier and would park a confirmation card for every click, which would force multiple approvals in a single flow.

## Decision drivers
- single human-in-the-loop approval per mutation
- tutorial clarity
- minimal operator friction

## Considered options
- **Multiple write-tier clicks (multiple HITL cards)** _(rejected)_ — pros: Each step is explicitly approved; cons: Violates the one-gate invariant; burdens operators with repeated approvals for a single logical mutation
- **URL-based or auto-submit login to avoid clicks before the mutation** — pros: Keeps only the final 'Confirm reset' click as write-tier; realistic for legacy admin panels that use query-string or cookie-based SSO; cons: Requires the demo pages to behave like legacy tools rather than standard form submissions

## Decision
Design the password-reset skill so that all steps up to the final confirmation are read-tier (`web.navigate`, `web.snapshot`, `web.fill_credential`, `web.type`) and place the sole `web.click` on the 'Reset password' submit button. The admin login uses an auto-redirect pattern so no click is needed to authenticate, preserving exactly one HITL gate per flow.

## Consequences
Skills authoring must consciously separate authentication/navigation from the actual mutation point. Demo pages must support credential pre-fill + auto-submit patterns typical of legacy internal tools. This keeps operator approvals minimal while still capturing evidence via screenshot after the confirmed mutation.