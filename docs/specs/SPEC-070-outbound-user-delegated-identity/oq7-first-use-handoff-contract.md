# SPEC-070 OQ-7: First-Use Authorization Handoff — Detailed Cross-Product Contract

> **RATIFIED 2026-10-19; delivery boundary amended 2026-10-23.** This is the OQ-7
> detailed contract named in [spec.md](spec.md#open-questions) and
> [plan.md](plan.md#first-use-handoff--ratified-contract-boundary-oq-7), not a claim that
> the complete authorization workflow has shipped.
> The operator approved provider-independent development acceptance and a separate
> [DI-070 deployment-integration task](tasks.md#post-delivery-deployment-integration-di-070).
> §8/§13 now pin local TTL defaults and retain mandatory S256; OQ-3 verifies the actual
> deployment rather than blocking development or release. R-1 capability behavior is pinned
> in the spec/plan; OAuth runtime implementation and its acceptance tests remain pending.
> The additive contract increment is implemented and verified, and its contract-only
> **v0.50.0** release/local deployment was separately approved on 2026-10-23; see
> [scoped evidence and exclusions](tasks.md#additive-oq-7-contract-increment). Full SPEC-070
> delivery remains open. **AAP compatibility unverified**; live tests, client registration,
> and production delegation enablement are not included in that authorization.

## 1. Purpose and scope

OQ-7 closes the gap ADR-0016 §5 and the spec's Impact section name explicitly: first-use
target OAuth authorization is **not** a connector-only token POST. It needs an
authenticated browser handoff, a callback, owner-scoped status/cancellation, and a safe
way to stop and later continue the originating conversation — across tool-gateway,
platform-gateway, agent-platform, operator-portal, and the shared contracts. The existing
`tool-result.schema.json` error object admits only `code`/`message`; there is no shipped
structured authorization handshake. This document specifies that handshake concretely so
an implementer makes **no** further design decisions.

It pins, per the plan's "Before OQ-7 can close" list:

1. exact route methods/paths and request/response schemas (§5, §6);
2. server-side browser-binding lifetime and single-use semantics (§8);
3. challenge-to-conversation persistence and backend selection (§7);
4. the authenticated internal handoff between products (§6);
5. stream projection and schema versioning (§4);
6. continue semantics against the shipped signed-execution / HITL / durable-claim path (§9).

Outside this handoff contract: R-1 credential-parser and R-6 encrypted-custody internals,
owned by [plan.md](plan.md#design-per-requirement). The 2026-10-23 amendment makes their
configuration/capability and key/rotation design provider-independent; no actual AAP fact
is needed to implement or test them. Live AAP behavior remains unverified under
[DI-070](tasks.md#post-delivery-deployment-integration-di-070), outside development acceptance.

## 2. Design principles (all grounded in shipped precedent)

- **Bounded stop, not a park.** The authorization handoff does **not** reuse the HITL
  `ConfirmationRegistry` park→resume machinery
  ([hitl_confirmations.py](../../../products/agent-platform/src/agent_service/services/hitl_confirmations.py)).
  A first-use authorization can take arbitrarily long (provider login/consent, possibly in
  another tab or device) and the registry is in-memory, per-process, and TTL-bounded — a
  parked reply would not survive the round trip. The tool call instead **fails** with a
  typed authorization-required result, the turn **completes normally**, and continuation is
  a **new user-initiated turn**. This keeps the kernel change minimal and means OAuth
  completion can never be confused with a mutation approval (R-2d).
- **Opaque, owner-scoped, single-use handles.** Every capability that crosses a browser
  boundary (`challenge_id`, `start_token`, `state`) is an unguessable `uuid4`, bound to the
  authenticated owner subject, TTL-bounded, single-use where it authorizes an action, and
  served behind a **no-oracle** posture — mirroring
  [secrets.py](../../../products/tool-gateway/src/tool_gateway/api/routes/secrets.py)
  (`_unavailable()` returns one 404 for not-found / spent / expired / wrong-owner).
- **Secrets never cross the frontend.** No access token, refresh token, authorization code,
  PKCE verifier, client secret, or provider authorization URL is ever returned to portal JS,
  the model, kernel state, a transcript, evidence, audit, or a log line. The browser follows
  a backend **302** to the provider; JS never sees the provider URL or the code (plan §3–4,
  R-5a).
- **Additive contracts only.** Existing tool-result semantics, stream frame types, credential
  schemes, and audit event types are unchanged for every current caller; new fields/types are
  optional and ignored by older clients.
- **Fail closed.** A wrong owner, expired/spent handle, unavailable store, unsupported PKCE,
  or unverifiable target account blocks the flow and grants no execution authority (R-5c/d).

## 3. Shipped patterns this contract mirrors

| Need | Shipped analog | Reuse decision |
| --- | --- | --- |
| Owner-scoped single-use handle + no-oracle 404 | `GET`/`DELETE /api/v2/secrets/delivery/{id}` ([secrets.py](../../../products/tool-gateway/src/tool_gateway/api/routes/secrets.py)) | Same posture for `challenge_id`/`start_token`; status read is non-destructive |
| Replica-safe transient state, Protocol + factory | `SecretDeliveryStore` ([secret_delivery.py](../../../products/tool-gateway/src/tool_gateway/tools/secret_delivery.py)): in-memory (`replicas:1`) / Redis (`replicas>1`, `SET EX` + atomic `GETDEL`) | Same Protocol shape for the authorization-transaction store, but **fail closed** (not open) when no shared backend is configured for `replicas>1` |
| Per-session, TTL-bounded, keyed by chat session | `BrowserSessionPool` / `BrowserSessionEntry` ([browser_sessions.py](../../../products/tool-gateway/src/tool_gateway/tools/browser_sessions.py)) | Lifetime/eviction model for the pending transaction |
| Dedicated self-describing stream frame as a `tool_result` sibling | `secret_delivery` frame, stream v12 ([agent-stream-event.schema.json](../../../shared/shared-contracts/schemas/agent-stream-event.schema.json)) | New `authorization_required` frame at **v13**, same sibling-promotion shape |
| Stream-frame lockstep across 4 surfaces | `_normalize_stream_event` + `_STREAM_EVENT_TYPES` ([routes.py](../../../products/agent-platform/src/agent_service/api/v2/routes.py)), `AgentStreamEvent` (schemas/v2.py), portal decoder/models | Same 4-surface checklist (§4.3) |
| Authenticated portal edge → policy → delegated internal call | `POST /api/v1/chat/confirm` ([chat.py](../../../products/platform-gateway/src/platform_gateway/api/routes/chat.py)) | Same edge shape for initiation/status/cancel |
| Typed tool failure with a reserved code | `make_error_result(name, CODE, msg, …)` in [gateway_service.py](../../../products/tool-gateway/src/tool_gateway/services/gateway_service.py); codes like `CREDENTIAL_SET_NOT_FOUND` | New reserved code `TARGET_AUTHORIZATION_REQUIRED` |
| Audit attribution without touching every connector | `audit_attribution(result)` hook merged into `details` | Delegation mode + authorization outcome ride attribution (§10) |

## 4. The typed authorization-required signal

### 4.1 Tool-result (tool-gateway → agent-platform)

The user-delegated client, on a **missing / expired / revoked** grant, returns a normal
error `ToolResult` **before opening any target session** (R-2b):

- `status: "error"`
- `error.code: "TARGET_AUTHORIZATION_REQUIRED"` (new reserved code; `error` stays
  `code`/`message` only — no `additionalProperties` violation)
- `error.message`: safe human text naming the target by its configured display label, e.g.
  `"This operation needs you to authorize Luban to act as you on <target> first."` Never a
  code, verifier, token, or URL.

Because `tool-result.schema.json` is `additionalProperties: false` at the top level and the
`error`/`evidence` objects are closed, the structured handle **cannot** ride the error
object. Following the `secret_delivery` precedent (a dedicated, self-describing projection
rather than an overloaded field), this contract adds **one optional top-level object**:

```jsonc
// tool-result.schema.json — ADDITIVE (proposed)
"authorization_required": {
  "type": ["object", "null"],
  "description": "SPEC-070 OQ-7: present only when status is 'error' and error.code is TARGET_AUTHORIZATION_REQUIRED. Carries an opaque, owner-scoped challenge handle the portal exchanges to start first-use authorization. Never a code, verifier, token, or provider URL.",
  "additionalProperties": false,
  "required": ["challenge_id", "target"],
  "properties": {
    "challenge_id": { "type": "string", "description": "Opaque uuid4 handle for the pending authorization transaction." },
    "target":       { "type": "string", "description": "Configured target display label (not an endpoint)." },
    "expires_at":   { "type": "string", "format": "date-time", "description": "When the challenge stops being actionable." }
  }
}
```

Rationale for a top-level object rather than riding `data`: `data` is documented as the
success payload and is size-capped/omitted on the stream; overloading it on an error result
would couple the handoff to the data-cap omission — the exact fragility the v12
`secret_delivery` note says a dedicated projection avoids. This is the **only** change to
`tool-result.schema.json`; it is optional and ignored by every current consumer.

### 4.2 Stream projection (agent-platform → portal)

The kernel middleware detects `authorization_required` on a `tool_result` and emits a
**dedicated sibling frame**, exactly as `ToolEvidenceMiddleware` emits `secret_delivery`:

- New `type: "authorization_required"` on `agent-stream-event.schema.json` → **version bump
  v12 → v13** (title + description ledger entry, following the existing per-version prose).
- Frame fields (flat, optional, `additionalProperties:false` at the frame root already):
  `auth_challenge_id` (string), `target` (string), `expires_at` (date-time), plus the
  mandatory `type`/`session_id`/`request_id`. **Never** a code/state/verifier/token/URL.
- The accompanying `tool_result` frame keeps `status:"error"` and the safe
  `error.code`/`message`; the model sees only that safe message, so it can narrate "please
  authorize <target>" without any secret and without looping (R-2c: cancellation/expiry is
  visible and does not repeatedly redirect).

The turn then ends with a normal `message_end`. **No park, no `confirmation_request`, no
signed-execution interaction** (§2, §9).

### 4.3 Lockstep surfaces (mandatory checklist)

Adding the frame type requires all four, or the frame is silently dropped in transit:

1. `shared/shared-contracts/schemas/agent-stream-event.schema.json` — v13, type enum, flat
   optional properties documented per frame type.
2. `products/agent-platform/src/agent_service/schemas/v2.py` — `AgentStreamEvent` fields.
3. `products/agent-platform/src/agent_service/api/v2/routes.py` — `_STREAM_EVENT_TYPES` +
   `_normalize_stream_event` coercion (mirror the `delivery_id`/`expires_at` handling).
4. operator-portal `stream/decoder.ts` + `stream/models.ts` — decode the new type; older
   builds ignore it (additive).

## 5. Portal-facing routes (platform-gateway)

All portal-facing routes are **bearer-authenticated** (existing `resolve_request_identity` +
`enforce_policy`) and **owner-scoped** except the two browser-navigation edges (§5.2, §5.3),
which authenticate by consuming a single-use capability instead of a header (a top-level
navigation cannot set an `Authorization` header). New policy action: **`targets:authorize`**
(added to `policy-default.yaml`, synced by `make sync-policy`; bundle `version` stays `1` —
it is a format version, not a content revision).

### 5.1 Start initiation — `POST /api/v1/targets/authorizations/{challenge_id}/start`

- Auth: bearer; `enforce_policy(targets:authorize)`; owner-scoped (challenge must belong to
  the caller's subject). Verifies **target entitlement** and current platform policy.
- Request body: none (the `challenge_id` is the path capability).
- Effect: consumes nothing yet; mints a short-lived, single-use **`start_token`** bound to
  `{owner_sub, challenge_id}`.
- Response `200`:
  ```jsonc
  { "start_url": "/api/v1/targets/authorizations/start/{start_token}", "expires_at": "<iso8601>" }
  ```
  `start_url` is a **backend** path only; the provider URL is never returned to JS.
- Errors: wrong owner / unknown / expired challenge → **404 no-oracle**; missing entitlement
  or policy denial → **403**; a challenge already `authorized`/`canceled` → **409**.

The portal then performs a **top-level navigation**: `window.location.href = start_url`.

### 5.2 Provider redirect — `GET /api/v1/targets/authorizations/start/{start_token}`

- Auth: **no bearer**; authenticates by **atomically consuming** the single-use
  `start_token` (owner-bound, configured TTL default 60 seconds, capped by transaction expiry).
  Spent/expired/wrong → **404 no-oracle** with `Cache-Control: no-store`.
- Effect: platform-gateway calls the tool-gateway internal handoff (§6.1) to build the
  provider authorization URL. **Tool-gateway alone** selects endpoint, scope, exact
  registered callback, PKCE S256 verifier, and `state` (R-3a; plan §3). The verifier and
  `state` binding are persisted server-side (§7); the local return path is chosen only from
  an allowlist bound at initiation.
- Response: **`302`** to the provider authorization endpoint, headers
  `Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`. JS never
  sees the provider URL or the code.

### 5.3 Callback — `GET /api/v1/targets/authorizations/callback`

- The **exact registered callback URI** (R-3a). Unauthenticated by nature (top-level
  redirect from the provider); identity comes **only** from server-side `state` →
  transaction binding, **never** from a query/body subject parameter (plan §3, R-3a).
- Query: `code`, `state` (and provider error params `error`/`error_description`, which map
  to a `canceled`/`failed` status without exposing provider internals).
- Effect: platform-gateway forwards `code`+`state` to tool-gateway over the authenticated
  internal handoff (§6.2). Tool-gateway validates `state` (single-use, unexpired,
  owner-bound, config-generation match), redeems the code with the PKCE verifier, verifies
  the target account identity against trusted linkage (R-3b), commits encrypted custody
  (R-6), and flips the challenge to `authorized`. **The callback dispatches no tool** (R-2d).
- Response: **`302`** back to the backend-selected conversation return URL with query
  material stripped, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` so the code
  never leaks to a referrer or access log (R-5a). **Uniform bare 302 for every outcome**
  (resolved 2026-10-19, §13.5): no backend-rendered interstitial HTML, so there is no page
  that could echo `code`/`state`; the portal renders the `canceled`/`failed`/`expired` reason
  from the §5.4 status poll.
- `code`/`state` are never logged (request middleware records method/path/status only) and
  never persisted in conversation data.

### 5.4 Status — `GET /api/v1/targets/authorizations/{challenge_id}`

- Auth: bearer; owner-scoped; **non-destructive** (readable until TTL, unlike a secret
  redemption). Wrong owner / unknown → **404 no-oracle**.
- Response `200`:
  ```jsonc
  {
    "challenge_id": "<uuid>",
    "status": "pending | authorized | canceled | expired | failed",
    "target": "<display label>",
    "session_id": "<originating conversation>",
    "updated_at": "<iso8601>",
    "expires_at": "<iso8601>"
  }
  ```
  Never a token/code/verifier/URL. The portal polls this after return and renders the five
  states distinctly (plan §5).

### 5.5 Cancel — `POST /api/v1/targets/authorizations/{challenge_id}/cancel`

- Auth: bearer; owner-scoped. Idempotent, no-oracle (mirrors `DELETE …/delivery/{id}`):
  found / spent / expired / wrong-owner all answer **204**. Flips status to `canceled` and
  burns the pending transaction + verifier. Cancellation leaves existing approvals,
  executions, and credentials unchanged (plan §6).

## 6. Authenticated internal handoff

Platform-gateway ↔ tool-gateway uses the existing service-to-service internal auth and owner
subject threading (`x_user_id` header + delegated token), the same shape the agent-platform
v2 confirm route uses. These routes are **internal only** (not portal-reachable):

### 6.1 `POST /api/v2/targets/authorizations/{challenge_id}/provider-url` (tool-gateway)

- Caller: platform-gateway (§5.2), presenting the consumed `start_token`'s owner binding.
- Effect: creates/finalizes the pending transaction, generates `state` + PKCE S256 verifier,
  persists them encrypted/single-use (§7), and returns `{ provider_url, state, expires_at }`
  to platform-gateway **only** for the 302. The verifier never leaves tool-gateway storage
  except to redeem the code.

### 6.2 `POST /api/v2/targets/authorizations/callback` (tool-gateway)

- Caller: platform-gateway (§5.3), body `{ code, state }`.
- Effect: validate `state`, redeem code (PKCE), verify target account, commit encrypted
  custody, flip challenge `authorized`. Returns `{ status, return_url }`. On any failure
  returns a safe `{ status: failed|canceled|expired }` with no provider internals.

### 6.3 `GET /api/v2/targets/authorizations/{challenge_id}` (tool-gateway)

- Caller: platform-gateway (§5.4/§5.5), owner-scoped; returns the status projection.

The originating agent-platform turn needs **no** callback: it already completed (§2). The
portal, on return, reads status via §5.4 and offers "Continue" (§9).

## 7. Authorization-transaction persistence

A dedicated **`AuthorizationTransactionStore`** in tool-gateway, shaped as a
`@runtime_checkable` Protocol + factory mirroring `SecretDeliveryStore`:

- **Record fields (transient workflow state):** `challenge_id` (uuid4), `owner_namespace`,
  `owner_sub`, `target`/`credential_set_id`, `config_generation`, `session_id`, `call_id`
  (the failed call), `return_url` (allowlisted), `status`, `created_at`, `expires_at`,
  `consumed` (single-use flag for `start_token`/`state`). **No** access token, refresh
  token, authorization code, provider URL. The PKCE verifier lives in the **separate**
  encrypted R-6 custody/transaction state, never in this routing record (R-6: "Persist
  short-lived authorization transaction state server-side, with single-use claims and
  encrypted PKCE verifiers if durable. Do not persist authorization codes.").
- **Backends:** in-memory (default; `replicas:1`, dev/CI; monotonic-clock TTL + eviction,
  modeled on `browser_sessions`) and — **resolved 2026-10-19, §13.3** — the shared backend
  for `replicas>1` is the **R-6 gateway-owned Postgres** (not Redis), so the secret-bearing
  PKCE verifier reuses the existing authenticated-encryption + versioned key mounts and the
  callback's redeem→verify→commit is transactionally adjacent to the custody write.
  Single-use consumption uses the execution-ledger advisory/row-lock pattern
  (`SELECT … FOR UPDATE SKIP LOCKED`); Postgres has no native TTL, so an expiry sweep bounds
  the transaction lifetime.
- **Fail-closed selection (differs from secret delivery):** `SecretDeliveryStore` fails
  *open* to in-memory. An authorization transaction **must** be visible to whichever replica
  receives the callback, so for `replicas>1` with no shared backend configured, delegated
  authorization is **disabled** (fail closed), consistent with "delegated mode stays
  disabled until configured" (R-6c).
- **Challenge-to-conversation binding:** the record carries `session_id` + `call_id` so the
  portal returns to the **same owned conversation** (R-2d) and the continue turn can
  reference the original intent — but continuation is a **new** turn, never a resume of
  stored kernel state (§9).
- **Durable credential custody is separate:** the refresh-token record (R-6, gateway-owned
  Postgres, authenticated encryption, owner/target/config-generation bound) is **not** the
  transaction record. A lost transaction never exposes a credential; a lost credential
  forces reauthorization, never stale-token resurrection (R-6b).

## 8. Browser-session binding and lifetimes

- **`start_token`** — opaque uuid4, single-use, configured TTL default **60 seconds**, bound to
  `{owner_sub, challenge_id}`; consumed atomically at §5.2. Solves top-level-navigation auth
  without a bearer header and without a cookie session the platform does not use.
- **`state`** — opaque, unguessable, single-use, server-side bound to `{challenge_id,
  owner_sub, config_generation, return_url}`. Rejects login CSRF, replay, issuer mix-up,
  wrong-session callbacks, arbitrary return URLs, and verifier mismatch (R-3a).
- **Transaction/state TTL** — bounds the whole provider login/consent round trip; configured
  default **600 seconds (10 minutes)**. State and browser binding expire no later than the
  transaction; issuing a start handle cannot extend it. On breach, status → `expired`;
  re-initiation is required. Consumption checks expiry atomically; a late callback fails
  closed even if an expiry sweep has not removed the row. Provider authorization-session/code
  limits may end the flow earlier; local TTL never extends provider validity.
- **Binding is to the authenticated owner captured at §5.1**, never to anything the browser
  sends on callback. A wrong user/tab-session, stale config generation, duplicate callback,
  or lost provider response cannot overwrite another user's credential or resurrect a revoked
  one (plan §5).

Local defaults are pinned by the 2026-10-23 amendment. Configuration must use positive
integer seconds with start TTL no greater than transaction TTL; invalid or unbounded values
fail closed. DI-070 reconciles these bounds with the actual provider's authorization-session,
code, and consent behavior before target enablement. OAuth `state` is client-owned; no
separate provider-owned `state` lifetime is assumed.

## 9. Continue semantics vs the shipped signed-execution path

This is the safety-critical boundary (R-2d; ADR-0016 §4):

- **Authorization completion restores context only.** A successful callback flips the
  challenge to `authorized`; it dispatches **no** tool and grants **no** execution authority.
- **Continue is a new user-initiated turn.** After return, the portal shows `authorized` and
  offers "Continue"; the user re-issues the operation. There is **no** auto-resume, **no**
  parked reply, and **no** reuse of a consumed claim.
- **The re-issued turn passes every existing gate fresh:** current platform policy
  (`tools:invoke`/`tools:mutate`), risk-tier gating, HITL confirmation for writes
  (`ConfirmationRegistry` park→resume), the signed execution envelope, and the SPEC-063
  durable dispatch claim. None is bypassed or pre-satisfied by the authorization.
- **No write replay / no uncertain-outcome laundering.** If the original operation was a
  write that had already been dispatched and was uncertain, the authorization flow does not
  resurrect or retry it; the durable ledger's uncertain-outcome handling stays
  authoritative. An unknown outcome is never converted to not-dispatched (plan §6).
- **OAuth consent ≠ mutation approval.** The `authorization_required` frame is a distinct
  typed signal, not a `confirmation_request`; `approval_kind`/`flow_summary` are never set
  on it, and the confirm bridge never treats it as a decision.
- **Cancellation is inert.** `canceled`/`expired`/`failed` leave existing approvals,
  executions, and any previously committed credentials unchanged.

Because the design is a bounded stop with a failing tool result, the **kernel is touched only
to emit one new frame type** (§4.2–4.3); the park/resume, signed-execution, and durable-claim
machinery is unchanged. This is the analysis the spec required before claiming the kernel is
unaffected.

## 10. Audit attribution and queryability (R-4)

- **Delegation mode as a top-level audit field** (placement resolved 2026-10-19, §13.4).
  Following the shipped precedent that requester (`sub`), actor (`act`), and `roles` are
  **top-level** audit fields — not `details` — add an optional top-level **`delegation_mode`**
  (`user_delegated` | `acting_service` | `none`) to `audit-event.schema.json`, the audit-service
  `AuditEvent` model, and a durable query filter, so R-4b's asserting round-trip/filter test
  can select delegated invocations. Derived from **verified acquisition**, never a config
  label (R-4a).
- **Authorization lifecycle.** Per-connector `audit_attribution(result)` merges a safe
  `details.authorization_outcome` (`authorized` | `canceled` | `expired` | `failed` |
  `reauthorization_required`) into the existing central `tool_invoked` emission — no per-connector
  audit code, and `details.additionalProperties:true` needs no enum change. Failed enrollment
  is never recorded as a successful delegated call (R-4a).
- **No secrets in audit.** Codes, state, verifiers, tokens, and provider URLs are excluded;
  only opaque ids, the target display label, outcome, and the human `sub`/`act` ride the
  event (R-5b).

## 11. Enumerated contract surfaces (for approval)

Exactly these surfaces change; everything else is untouched:

**Shared contracts**
- `shared/shared-contracts/schemas/tool-result.schema.json` — add optional top-level
  `authorization_required` (§4.1).
- `shared/shared-contracts/schemas/agent-stream-event.schema.json` — v12 → **v13**, add
  `authorization_required` type + `auth_challenge_id`/`target`/`expires_at` (§4.2).
- `shared/shared-contracts/schemas/audit-event.schema.json` — add optional top-level
  `delegation_mode` (§10).
- `shared/shared-contracts/policies/policy-default.yaml` — add `targets:authorize` action +
  rule; `make sync-policy`; bundle `version` stays `1`.

**tool-gateway**
- New reserved error code `TARGET_AUTHORIZATION_REQUIRED`; user-delegated client returns it
  pre-session (R-2b).
- New `AuthorizationTransactionStore` Protocol + factory (§7); internal routes §6.1–6.3;
  provider-URL builder (endpoint/scope/callback/PKCE/state selection); code redemption +
  account verification + custody commit hook (R-6 foundation dependency).
- `audit_attribution` extension for `authorization_outcome` (§10).

**platform-gateway**
- Portal routes §5.1–5.5; `enforce_policy(targets:authorize)`; internal client to §6;
  302/no-store/no-referrer handling; access-log scrubbing for callback query material.

**agent-platform**
- Kernel middleware emits the `authorization_required` sibling frame; `_normalize_stream_event`
  + `_STREAM_EVENT_TYPES` + `AgentStreamEvent` (§4.3). No park/resume change (§9).

**operator-portal**
- `stream/decoder.ts` + `stream/models.ts` decode the frame; an inline "Authorize <target>"
  control bound to `auth_challenge_id` (distinct from the confirmation card); top-level
  navigation to `start_url`; post-return status polling + "Continue"; cancel control. No
  credential-settings UI, no token in JS/storage (R-2c).

**audit-service**
- `AuditEvent` model + query filter for `delegation_mode`; `tests/test_contracts.py`
  top-level-name parity with the schema (§10).

## 12. Security invariants and negative tests (map to R-3 / R-5)

Written failure-first (R-5):

- Wrong owner / second tab / spent `start_token` on §5.2 → 404 no-oracle, no provider URL.
- Callback with forged/replayed/mismatched `state`, wrong-session, or arbitrary `return_url`
  → rejected; no custody write; no tool dispatch (R-3a).
- Code redemption with wrong/absent PKCE verifier → fail closed; **no** unsupported-PKCE or
  service-credential fallback (R-3a; plan R-3 gate).
- Target account that does not match trusted linkage (username/email-only, wrong account) →
  rejected (R-3b).
- Duplicate callback, lost provider response, expired transaction → `expired`/`failed`, never
  a double credential write, never a resurrection (plan §5, R-6b).
- Opaque-secret injection into code/state/verifier/token/URL/error/log/referrer/access-log →
  assert exclusion from portal JS/storage, kernel, transcript, evidence, audit, traces
  (R-5b); `make validate-secret-vocabulary` stays green.
- Any delegated failure → assert **zero** calls to Basic/bearer/machine-grant/
  unauthenticated/alternate-transport fallbacks, including MCP diagnostics/stdio (R-5c).
- Continue turn → assert it re-passes policy + HITL + signed execution + durable claim, and
  that no consumed claim is reused and no uncertain write is replayed (§9, R-2d).

## 13. Sub-decisions and deployment checks

Items 3–5 were resolved 2026-10-19. The 2026-10-23 amendment pins item 1's development
defaults and separates item 2's fixed security policy from actual provider verification.
Neither requires an available AAP instance to implement; deployment reconciliation remains
mandatory under DI-070.

1. **[RESOLVED 2026-10-23] Local numeric defaults:** `start_token` 60 seconds;
   transaction/`state` 600 seconds. Configurable positive integer lifetimes, start bounded
   by transaction expiry, atomic expiry checks, and no extension of a provider's code or
   authorization-session validity (§8). DI-070 verifies suitability against real consent
   dwell and provider limits; no provider-owned OAuth `state` lifetime is assumed.
2. **[POLICY FIXED; DI-070 EVIDENCE PENDING] PKCE S256 is mandatory.** Development tests
   prove S256 requests/verifiers and no downgrade. Actual app support/enforcement is still
   unknown: an unsupported, disabled, or unverified profile blocks production target
   enablement. AAP version alone is not proof. No exception or fallback is authorized here.
3. **[RESOLVED 2026-10-19] Transaction-store backend → Postgres.** The replica-safe
   authorization-transaction store (holding `state` + the encrypted PKCE verifier from
   initiation to callback) uses the **R-6 gateway-owned Postgres**, not Redis, so the
   secret-bearing verifier reuses the existing authenticated-encryption + versioned key
   mounts rather than adding a second secret-bearing datastore, and the callback's
   redeem→verify→commit sits transactionally adjacent to the custody write. Single-use
   consumption uses the execution-ledger advisory/row-lock pattern (`SELECT … FOR UPDATE SKIP
   LOCKED`); no native TTL, so an expiry sweep is required. The **fail-closed** rule (§7)
   stands: `replicas>1` with no shared backend configured disables delegated authorization.
4. **[RESOLVED 2026-10-19] `delegation_mode` → top-level audit field.** Added alongside
   `sub`/`act`/`roles` per the identity-like-data precedent (§10), giving R-4b a cleanly
   indexable/filterable field. Accepted cost: `audit-event.schema.json` + audit-service
   `AuditEvent` model + `test_contracts.py` parity + six-product schema re-sync + query
   filter. The safe `details.authorization_outcome` via the attribution hook is unchanged.
5. **[RESOLVED 2026-10-19] Callback response → uniform bare 302.** All outcomes 302 back to
   the owned conversation with query material stripped and `no-store`/`no-referrer`; the
   portal renders every state (`pending`/`authorized`/`canceled`/`expired`/`failed`) from the
   §5.4 status poll it already needs for "Continue". No backend-rendered interstitial HTML,
   so there is no page that could echo `code`/`state`.

## 14. What this document does not authorize

OQ-7 ratification and the 2026-10-23 amendment permit provider-independent implementation,
not claims about unverified AAP behavior. This documentation amendment is committed separately
for operator review before code. Development delivery still requires all R-1–R-6d tests and
root verification; it does not wait for DI-070. Production target enablement still requires
DI-070. Live target/token tests, client registration, push, deployment, and version changes
remain separate authorization boundaries (spec Status; ADR-0016 deciders).

## Revision history

- 2026-10-23: operator approved the development/integration boundary amendment. R-1/R-6
  internals no longer await AAP facts; local TTL defaults fixed at 60/600 seconds, S256
  mandatory, actual deployment verification retained under DI-070. Corrected the lifetime
  wording: OAuth state is client-owned; provider session/code limits are separate. No API,
  stream, audit, or continue semantics changed; no runtime or AAP proof claimed. Earlier
  ratification records below remain unchanged.
- 2026-10-19 (ratification): the operator **ratified** the OQ-7 contract, closing the
  pre-runtime design gate — banner flipped PROPOSED → RATIFIED, and §13/§14 updated to
  record that R-1..R-6 implementation may now begin against this contract. Items §13.1–13.2
  (numeric TTLs, PKCE support fact) stay **[OQ-3]-gated** value/fact pins, not open design
  decisions; OQ-3 remains the pre-live gate. Ratification authorizes no runtime code that
  depends on OQ-3, no live target test, deployment, commit/push, or version bump.
- 2026-10-19: operator resolved the three now-decidable sub-decisions (§13.3–13.5) —
  transaction-store backend = **Postgres**, `delegation_mode` = **top-level audit field**,
  callback response = **uniform bare 302** — and the resolutions were folded into §5.3, §7,
  and §10. Items §13.1–13.2 (numeric TTLs, PKCE support fact) remain **OQ-3-gated**.
  Documentation only — no runtime change, no commit/push, deployment, or version bump.
- 2026-10-18: initial OQ-7 proposed contract drafted from the shipped call chain
  (secret-delivery single-use handles, HITL registry, stream v12, tool-result error, gateway
  confirm routing, audit attribution). Marked **proposed / pre-runtime gate**; no runtime
  change; OQ-3-dependent values left unpinned.
