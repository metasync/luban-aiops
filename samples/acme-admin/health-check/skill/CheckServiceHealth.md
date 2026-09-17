---
title: Check ACME Admin Service Health
description: >
  Verify that the acme-admin user-administration console is up and
  answering, over its JSON API. Use this skill when someone asks
  whether the acme-admin service is healthy, what version it is
  running, how long it has been up, or whether its user store is
  seeded. Performs two unauthenticated http.get calls — /healthz for
  the service facts and /api/hello for a round-trip probe — and reports
  what they returned. Read-only: it changes nothing and parks no
  confirmation card.
tags: [acme-admin, health, healthz, http, service-check, read-only, api, uptime, monitoring]
version: "1.0"
---

## Purpose

Answer "is the acme-admin console actually working?" from its own API
rather than from a rendered page. This is the API-level complement a
browser health check cannot be: no browser, no login, no session, and
therefore no HITL gate.

Common requests this skill handles:

- "Is the acme-admin service healthy?"
- "What version is acme-admin running, and how long has it been up?"
- "Check the acme-admin health endpoint and tell me what it reports"
- "Is the acme-admin user store seeded?"

This skill is a **tutorial example** — the repository's first genuinely
read-only skill. It demonstrates:

- A skill with **no `web_target` and no `risk_class`**. Those keys
  describe a browser flow; a skill that never opens a browser must not
  declare them. Declaring `risk_class: read` anyway would be harmless
  today and misleading tomorrow, because it would imply a flow exists
  to bind.
- That **zero confirmation cards** is a property of *effect*, not of
  tooling. `http.get` is read tier, so the gateway executes it and
  reports the result; nothing parks for an operator.
- Reading a **projected** response rather than a raw one: the tool
  returns a fixed key set (`url`, `status`, `elapsed_ms`, `headers`,
  `content_type`, `content_length`, `truncated`, `body`) and only six
  safe response headers. `set-cookie` and `authorization` are never
  projected, so a health check cannot become a credential leak.
- Treating an upstream **4xx/5xx as the finding**, not as a failure. If
  `/healthz` answers 503, the honest report is "the service answered
  503" — the tool result still carries `status: success`, because the
  check ran.

## Preconditions

- The `http.get` tool is registered on the tool-gateway, which needs
  **both** `GATEWAY_HTTP_ENABLED=true` and a non-empty
  `GATEWAY_HTTP_ALLOW_ORIGINS`. The dev cluster's `browser-dev` runtime
  profile sets both; the committed base sets neither, so out of the box
  this skill reports `TOOL_NOT_FOUND`.
- The target origin `http://acme-admin:8080` is listed in
  `GATEWAY_HTTP_ALLOW_ORIGINS`. The allowlist is deny-by-default: an
  unlisted origin is refused **before any socket is opened**.
- The app is deployed (`make deploy-sample-app`). This skill needs no
  credential: both endpoints it calls are unauthenticated.

## Procedure

Two `http.get` calls, both read tier, both unauthenticated. There is no
write-tier step anywhere in this skill, which is why it parks nothing.

1. **Read the health payload.** `http.get` with
   `url: http://acme-admin:8080/healthz`. No `credential_set` — this
   endpoint requires none, and supplying one would send a credential to
   an endpoint that does not ask for it.

2. **Report the eight facts.** The body is JSON carrying `status`,
   `service`, `version`, `hostname`, `uptime_seconds`, `started_at`,
   `users_seeded` and `store_revision`. Report the ones the caller asked
   about and say which pod answered (`hostname` is the pod name, so two
   runs landing on different pods is visible rather than mysterious).
   `users_seeded` should be `4` and `store_revision` should be `0` on a
   freshly started pod; a higher revision means something has already
   mutated the in-memory store since the last restart.

3. **Probe the round trip.** `http.get` with
   `url: http://acme-admin:8080/api/hello?name=luban`. Assert the body
   is `{"message": "hello, luban!"}`. This is not a health check in the
   narrow sense — it proves the service parses a query parameter and
   echoes it back correctly, so a routing or proxy misconfiguration that
   still serves `/healthz` cannot pass as healthy.

4. **Summarise honestly.** State the upstream status codes as facts.
   If `/healthz` returned 200 and `/api/hello` returned 500, say so —
   do not average them into "mostly healthy". Include `elapsed_ms` when
   the caller is asking about latency, and say so explicitly if
   `truncated` is `true`, because that means the body was cut at
   `GATEWAY_HTTP_MAX_RESPONSE_BYTES` and what you read is incomplete.

## Interpretation

- `TOOL_NOT_FOUND` — `http.get` is not registered. `GATEWAY_HTTP_ENABLED`
  is false in the live runtime config. Report the configuration gap; do
  not fall back to a browser tool and do not retry.
- `HTTP_ORIGIN_NOT_ALLOWED` — the origin is not in
  `GATEWAY_HTTP_ALLOW_ORIGINS`. The request was refused before any
  socket was opened, so nothing reached the app. Report the missing
  allowlist entry.
- `HTTP_SCHEME_NOT_ALLOWED` — only `http` and `https` are accepted. A
  URL userinfo (`user:password@host`) is refused as
  `INVALID_PARAMETERS`; this skill needs no credentials at all.
- `HTTP_TIMEOUT` — the origin is allowlisted but did not answer within
  `timeout_ms`. Check that the app is deployed and its readiness probe
  is passing before blaming the network.
- `UPSTREAM_ERROR` — the gateway could not complete the request. This is
  distinct from an upstream 4xx/5xx, which arrives as a **successful**
  tool result carrying that status.
- `CREDENTIAL_SET_NOT_FOUND` — you supplied a `credential_set` that is
  not configured. Neither step of this skill should supply one.
- A body that is a string where JSON was expected means the response was
  truncated or was not `application/json`; check `content_type` and
  `truncated` before interpreting it.

## Tutorial notes (skill authoring guidance)

**Why does this skill declare no `risk_class`?**
`risk_class` declares the effect of a *browser flow's* interactive steps,
and `web_target` is the URL the gateway binds that flow to. A skill that
never calls a `web.*` tool has no flow to bind and no interactive steps
to classify, so both keys are noise. Tier is enforced per **tool**, not
per skill: `http.get` is read tier in the gateway's registry, and that is
what keeps this skill card-free. Declaring `risk_class: read` would not
make it safer — it would only suggest to the next author that a skill
needs the key to be read-only, which is not how the gate works.

**Why is a card a property of effect and not of tooling?**
Compare this skill with `CheckUserStatus`, which reads a *rendered page*
through a browser and also parks zero cards. Neither reads anything the
other can: this one gets JSON straight from the service, that one gets
the HTML a human would see. Both are read-only, so both are card-free —
the surface differs and the approval posture does not. The pair is the
suite's main teaching point, and it is why `InventoryHealth`'s claim to
"complement the API-level checks" finally has an API-level check to point
at.

**Why two calls and not one?**
`/healthz` can be served by a load balancer or a cached probe path while
the application behind it is broken. `/api/hello?name=luban` forces the
service to parse a parameter and echo it, which is the cheapest possible
proof that requests reach the application and come back intact. A health
check that only reads a health endpoint reports the endpoint, not the
service.

**Why is the `name` parameter bounded?**
The app validates `name` against `^[A-Za-z0-9 _.-]{1,64}$` and answers
422 outside it. That bound exists because the value is echoed: an
unbounded echo into a rendered page is a markup-injection primitive. This
skill only ever sends `luban`, but a skill that echoes caller-supplied
text into a URL should assume the target validates it and should report a
422 as a bad parameter, not as a broken service.
