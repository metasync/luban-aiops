---
title: Inventory Health Web Check
description: Sign in to the inventory portal with the platform credential set and verify the status page reports every component operational.
tags: [browser, web-check, inventory, login, status]
version: "1.0"
web_target: http://browser-check-target:8080/
risk_class: write
---

## Purpose

End-to-end user-perspective health check of the inventory portal:
authenticate through the real login form and confirm the status page
reports every component operational. Complements the API-level checks
by exercising the rendered UI.

## Preconditions

- The `browser-check-target` credential set is configured on the
  tool-gateway (`GATEWAY_BROWSER_CREDENTIAL_SETS`). The password is
  platform-managed; never paste credentials into the chat.
- The target origin is on the gateway allowlist
  (`GATEWAY_BROWSER_ALLOW_ORIGINS`).

## Procedure

1. Bind and open the flow: `web.navigate` with this skill's id and the
   `web_target` URL. This `write`-class flow parks exactly one
   confirmation card — at its single write-tier interaction, the sign-in
   click in step 4; the read-tier steps around it run without a gate.
2. Take a `web.snapshot` and locate the username and password fields.
3. Fill both login fields with `web.fill_credential` (read tier) from
   set `browser-check-target`: field `username` into the username
   element, then field `password` into the password element. Never use
   `web.type` here — filling a field submits nothing, so keeping both
   fills read-tier leaves the sign-in click as the flow's only
   write-tier interaction (the one HITL gate, D-3).
4. Click the sign-in button (`web.click`) — the flow's single write-tier
   interaction, so this is where the one confirmation card parks — then
   snapshot again: the page must read "Signed in as svc-check". This is
   the flow's last `web.click`/`web.type`; every later step is read-tier
   and parks no card.
5. Reach the status page with `web.navigate` to `/status` on the same
   origin — a read-tier step, never a click (the portal exposes no
   status link, and a second `web.click` would park a needless card and
   break the one-gate invariant) — then snapshot it: `api`, `database`,
   and `queue` must all read `operational`.
6. Optionally capture a `web.screenshot` as final evidence.

## Interpretation

- Any denial (`BROWSER_ORIGIN_NOT_ALLOWED`, `BROWSER_FLOW_DENIED`)
  means the flow was refused by policy or the operator — stop and
  report the denial, never retry around it.
- A snapshot that does not show all components `operational` is a
  degraded inventory portal; escalate with the snapshot evidence.
- The step budget is bounded by `GATEWAY_BROWSER_FLOW_MAX_STEPS`;
  exhaustion (`BROWSER_FLOW_EXHAUSTED`) means the check deviated and
  must be restarted with a fresh confirmation.
