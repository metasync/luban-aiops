# SPEC-062 Plan: Secure Password Generation and Delivery Tools

## Approach

One new connector module in tool-gateway holding both tools plus the delivery
buffer, one new shared `password-policy` contract with a drift-guard validator,
two targeted kernel-side redaction fixes, one curated approval-card formatter,
one new stream frame, one redemption proxy route, and one portal control. The
generated value is a secret from the moment it exists, so the spine of this plan
is not the generation algorithm (that is `secrets` + a policy) but **every
projection the value could ride, and the structural control that keeps it out of
each**.

The implementation groups into six stages, ordered so each leaves `make verify`
green on its own:

1. **Contracts first.** The `password-policy` contract, its `validate-password-policy`
   drift guard (wired into `make verify`), the `secrets:deliver` action in
   `policy-default.yaml` (format version stays 1), the `secret_delivered` audit-event enum
   member, and the `secret_delivery` stream frame (schema v12). These are pure
   additions — no product reads them yet — so they land whole and keep the gate
   green before any code depends on them.
2. **Configuration.** `GATEWAY_SECRETS_*`, `GATEWAY_PASSWORD_*`,
   `GATEWAY_SECRET_DELIVERY_*` and `GATEWAY_EMAIL_*` settings on `GatewaySettings`,
   all defaulting to the closed position (secrets disabled, email unconfigured,
   buffer in-memory).
3. **The connector + buffer.** `tools/secrets_connector.py` (generation + the
   external-channel `secrets.deliver` dispatcher) and `tools/secret_delivery.py`
   (the pluggable single-use buffer). Gated wiring in `app.py`; the redemption
   route in `api/routes/`.
4. **The two kernel redaction fixes.** `redact_result_data` in `secret_params.py`
   applied to the `tool_result` frame in `kernel_middleware.py`; the generated
   literal harvested into the prose-redaction set so a model restatement masks.
   Then the `secret_delivery` frame emission and the email card formatter.
5. **Gateway + portal.** platform-gateway's `ACTION_SECRETS_DELIVER`, the
   per-tool extra-action admission hook, and the redemption proxy; the portal
   Copy-password control and its one-time authenticated redemption fetch.
6. **Skill, samples, docs, GitOps, tests, e2e.**

The single decision that shapes the code is **where the value is allowed to
exist**. It stays real in generation, the ephemeral buffer, and the kernel/model
working context so a reset or explicitly approved external delivery can use it.
The authenticated one-time handoff carries it through the gateway proxy directly
to the requester's clipboard; approved email carries it through TLS to SMTP.
These intentional transports are distinct from human-readable projections:
the tool-evidence frame, durable agent snapshot/transcript, session title, live
stream text, confirmation card, and audit trail mask or omit the value. The
projection gaps described below are the pre-implementation baseline, closed by
stage 4 and verified by the acceptance evidence in `tasks.md`.

## Resolved At Plan Time

These are the "how" decisions the approved spec deferred here (R-3 names the
buffer mechanism explicitly; D-8 leaves R-1/R-2 spec-local). Two refine the
spec's `Impact` sketch and are flagged for the record.

- **Delivery tool surface — portal-copy folded into generation (user-decided).**
  The gateway derives required policy actions from a tool's single static
  `risk_level` (`gateway_service.py`: `tools:invoke` for every tool, plus
  `tools:mutate` when `risk_level != "read"`; no per-argument hook), so one
  registered tool cannot be read-tier for portal-copy and write-tier for email as
  D-5 requires. Resolution: **`secrets.generate_password(handoff=…)`** (read-tier)
  owns the portal-copy handoff — it generates *and* stashes, returning the
  `delivery_id` — and **`secrets.deliver(channel=…)`** (write-tier) is the single
  dispatcher for channels that send a secret *outside* the session (email now;
  Teams/Slack additive). This keeps R-4's "email is the `email` channel of the
  single `secrets.deliver(channel=…)` dispatcher" literally true, honors D-5's
  per-channel tiers with static gating, and introduces no argument-dependent
  security decision. It refines R-3's "the agent calls a delivery tool" (for
  portal-copy the stash rides generation) and R-5's framing (portal-copy is the
  intrinsic *local* handoff; the `DeliveryChannel` interface governs the
  *external* senders). Both still implement one `DeliveryChannel` seam.
- **Buffer home — tool-gateway, not agent-platform (refines the `Impact`
  sketch).** Every tool executes in tool-gateway (`gateway_tools.py` →
  `POST /api/v2/tools/invoke`), so the value is already there during the call;
  stashing locally avoids inverting the call graph with a new
  tool-gateway→agent-platform dependency that does not exist today. tool-gateway
  also already holds per-pod, TTL-bounded, session-keyed state (the
  `browser_sessions.py` pool), which is the exact shape and the exact
  `replicas: 1` constraint the buffer inherits. The redemption endpoint is a
  tool-gateway route proxied by platform-gateway (which already proxies
  `tools:list`/`tools:invoke`). agent-platform's role narrows to what it uniquely
  owns: the masking vocabulary, the `tool_result`-frame redaction, the
  `secret_delivery` stream frame, and the email card formatter.
- **Buffer replica-readiness (D-2).** The buffer sits behind a small
  `SecretDeliveryBuffer` `Protocol` mirroring `session_store.py`: an in-memory
  backend (default; dev/CI, `replicas: 1`, modeled on the browser pool's TTL +
  eviction) and a Redis backend (`replicas > 1`) using `SET … EX` for the TTL and
  atomic `GETDEL` for single-use redemption. Redis is a **new, additive**
  tool-gateway dependency (it has none today); the backend is selected by
  `GATEWAY_SECRET_DELIVERY_BACKEND` exactly as `SESSION_STORE_BACKEND` selects the
  session store, and fails open to in-memory with a recorded fallback. The
  stateless encrypted-handle variant (ADR-0012) stays deferred — it is the most
  secret-safe option and the natural successor if the buffer ever needs to leave
  the process entirely, but it is not required for `replicas > 1` correctness.
- **The two projection gaps this spec must close (the crux).**
  1. `ToolEvidenceMiddleware` redacts the `tool_call` frame's *parameters*
     (`redact_evidence_parameters`) but builds the `tool_result` frame's
     `data`/`data_summary` with **no redaction at all** (`_make_data_summary` /
     `_make_full_data` only serialize and size-guard). A generated value returned
     in `data` would therefore stream into the evidence panel and the evidence
     store in plaintext. Fix: a new `redact_result_data(tool_name, data)` in
     `secret_params.py`, applied to a **copy** at this seam so the frame masks
     while the model's `ToolChunk` content (built earlier, from the same raw
     result) still carries the real value into the working context.
  2. `prose_redaction.credential_literals` harvests secret literals from **user
     text only**, so a model that restates a tool-*generated* value in its
     assistant prose would land unmasked in the transcript, the title and the live
     stream — the exact leak the spec's Motivation names. Fix: the kernel
     harvests the generated literal from the `secrets.generate_password` result
     into the session's known-credential set that `redact_assistant_text` /
     `redact_transcript` match, so a restatement masks structurally rather than
     relying on the model obeying the skill's "never write it out" guidance
     (which is defense-in-depth, not the control).
  The durable transcript is already safe against the raw tool result: it extracts
  only `user`/`assistant` **text** blocks and skips tool blocks
  (`session_transcript._TRANSCRIPT_ROLES`, `_extract_text`), so the value in the
  tool-result content never rides it. Fix 2 covers the residual prose-restatement
  path.
- **`secrets:deliver` enforcement — a per-tool extra-action hook.** The gateway's
  tier check is static, so requiring `secrets:deliver` *in addition to*
  `tools:mutate` for one specific write-tier tool needs a small general
  extension: `ToolDefinition` gains `extra_required_actions: tuple[str, ...] = ()`
  and `gateway_service.invoke` evaluates each after the tier check (deny →
  `make_denied_result`, audited). `secrets.deliver` declares
  `("secrets:deliver",)`. This is general (a future tool can require its own
  action) and keeps enforcement at admission, not inside a connector.
  `ACTION_SECRETS_DELIVER` joins tool-gateway's `PROTECTED_ACTIONS` and
  platform-gateway's action constants (for the matrix surface).
- **Recipient allowlist lives in two services on purpose (D-7).** The card's
  posture (routine confirm vs. prominent "recipient domain not on the approved
  list" warning) is decided kernel-side at *park* time, before the tool runs, so
  agent-platform needs the allowlist (`AGENT_EMAIL_RECIPIENT_ALLOWLIST`) to render
  it. The authoritative enforcement — `GATEWAY_EMAIL_STRICT_ALLOWLIST=true`
  hard-denying an out-of-allowlist send — runs in tool-gateway at send time
  (`GATEWAY_EMAIL_RECIPIENT_ALLOWLIST`). The two are documented as paired config;
  there is no automatic cross-service configuration drift guard. The send-time
  strict check is authoritative. Warning acknowledgment must be a strict boolean
  and is checked before the pending confirmation is claimed, in both UI paths.
- **`secret_delivered` fires at retrieval or transport acceptance**, not when a
  handle is minted: at redemption for portal-copy, at SMTP accept for email.
  SMTP acceptance does not prove inbox delivery. An expired
  unredeemed handle fires nothing (no delivery happened). The event carries
  `delivery_id`, `channel`, `recipient`, acting identity and timestamp — never the
  value.

## Design Per Requirement

### R-1: `secrets.generate_password` — a read-tier CSPRNG generation tool

- affected files: `products/tool-gateway/src/tool_gateway/tools/secrets_connector.py`
  (new), `tools/base.py` (the `extra_required_actions` field),
  `products/agent-platform/src/agent_service/services/secret_params.py`,
  `services/kernel_middleware.py`
- chosen approach: `SecretsConnector.register_tools` registers
  `GeneratePasswordTool(BaseTool)` at `risk_level="read"`, `category="secrets"`,
  `SOURCE_SYSTEM = "secrets"`. `execute()` follows the standard error ladder
  (`adding-a-tool.md`): coerce/validate `length`/`policy`/`handoff` →
  `INVALID_PARAMETERS`; generate; optionally stash; return
  `ToolResult(data={…}, evidence=build_evidence("read", "secrets", ms))`. The
  value comes from `secrets.choice` over a class-built alphabet — never the model.
  `data` carries `generated_password` (the value), `length`, `policy`, and, when
  `handoff="portal_copy"`, `delivery_id` / `channel` / `expires_at`.
- **the value field is named `generated_password`, not `password` — corrected at
  build time.** The gateway's own redaction choke point (`redaction.py`,
  `redact_result` in `invoke_tool`) masks a `data` key on an **exact**
  case-insensitive match against `_SENSITIVE_KEYS`, which contains `password`. A
  field literally named `password` would therefore be replaced with `[REDACTED]`
  *before the result ever reaches the kernel*, breaking R-1's requirement that
  the value stay real in the kernel's working context so the agent can pass it to
  a reset or a delivery. `generated_password` survives that exact-match gate, and
  the kernel's **substring** vocabulary (`secret_params.SECRET_PARAM_SUBSTRINGS`
  contains `password`, so `is_secret_param("generated_password")` is true) still
  masks it in every projection. R-1's tool-evidence-frame guarantee additionally
  needs the new `redact_result_data` (Resolved At Plan Time, fix 1) because the
  `tool_result` `data` path applies no redaction today.
- `handoff` defaults to `portal_copy` and may explicitly be `none` (no Copy
  button). Stashing uses the R-3 buffer; the returned `delivery_id` is opaque
  (`uuid4`) and scoped to the verified requester `sub`. The forwarded session ID
  is context, never authority. On approval resume generation alone retains the
  requester's captured token; approved writes use the approver's token. Explicitly
  missing requester authority cannot fall back to the approver.
- alternatives rejected: returning the value in a generically-named field
  (`value`) — invisible to name-based masking and would rely entirely on the new
  result-redaction set; and a reference-only design where the model never sees
  the value (like `web.fill_credential`) — explicitly rejected by the spec, which
  wants parity with the chat-supplied-password posture so the agent can pass the
  value to a reset or a delivery.

### R-2: Password policy as a single source of truth

- affected files: `shared/shared-contracts/policies/password-policy.yaml` (new),
  `shared/shared-contracts/scripts/validate_password_policy.py` (new),
  `products/tool-gateway/src/tool_gateway/tools/password_policy.py` (new loader),
  `core/config.py`, root `Makefile`, the `sync-policy` target
- chosen approach: a versioned YAML contract beside `policy-default.yaml`:
  `version: 1` and a `policies:` map whose only v1 entry is `default`
  (`min_length: 16`, `hard_floor: 12`, `required_classes: [upper, lower, digit,
  symbol]`, `entropy_floor_bits: 64`, `exclude_ambiguous: false`). It is synced
  into tool-gateway and mounted in dev-k8s exactly like the policy bundle, and
  read by a `PasswordPolicyStore` that mirrors `credential_sets.py`
  (mtime-refreshed, fail-closed on an unreadable/invalid file, never logs
  contents). Named policies (`strict`) are additive: a new key in the map plus a
  `policy` lookup, touching no caller — asserted by a test.
- env overrides may **only tighten**: `from_env()` compares each
  `GATEWAY_PASSWORD_*` override against the contract and raises in
  `__post_init__` if any would weaken it (a lower `min_length` than the contract,
  a dropped required class, `hard_floor` violated) — the fail-fast convention the
  config knowledge card documents. `GATEWAY_PASSWORD_EXCLUDE_AMBIGUOUS=true` may
  only *add* the exclusion.
- generation guarantees every required class is present (seed one char per class,
  fill the remainder from the full alphabet, shuffle with `secrets`) and that
  the conservative pre-shuffle entropy meets the floor:
  `(length - class_count) * log2(full_alphabet_size) + sum(log2(class_size))`.
  A request the policy cannot satisfy (length below the class count) fails closed with
  `INVALID_PARAMETERS`, never a weak value. A `length` below `min_length` is
  raised to it; below `hard_floor` after tightening is a refusal.
- drift guard: `validate_password_policy.py` extracts the floor the connector
  enforces (a module constant tuple, mirroring `validate_secret_vocabulary.py`'s
  cross-file extraction) and fails the build if it diverges from the contract,
  if the consumer is missing, or if the packaged YAML differs from canonical.
  Wired into `make verify` as `validate-password-policy`.
- **Not in v1:** dictionary/breached-corpus checks (Non-Goal; needs a breach
  list).
- alternatives rejected: env-only policy (no single source of truth for the skill
  to cite, R-6) and contract-only (no per-deployment hardening). The hybrid is
  D-4's resolution.

### R-3: One-time secure delivery — the Copy-password handoff (redemption-on-click)

- affected files: `tools/secret_delivery.py` (new buffer), `tools/secrets_connector.py`,
  `api/routes/secrets.py` (new redemption route), `app.py`,
  `products/agent-platform/src/agent_service/services/kernel_middleware.py`
  (the `secret_delivery` frame), `shared/shared-contracts/schemas/agent-stream-event.schema.json`
- chosen approach: `SecretDeliveryBuffer` is a `@runtime_checkable` `Protocol`
  with `stash(value, owner_sub, session_id, ttl) -> delivery_id` and
  `redeem(delivery_id, owner_sub) -> str | None` (single-use, owner-scoped,
  TTL-bounded), plus `backend_name` — mirroring `SessionStore`. Two backends and a
  `build_secret_delivery_buffer()` factory reading
  `GATEWAY_SECRET_DELIVERY_BACKEND` (`memory`|`redis`, default `memory`, unknown
  fails startup), exactly the `build_session_store()` shape.
  - `InMemorySecretDeliveryBuffer`: a dict `delivery_id → (value, owner_sub,
    session_id, expires_at)` with monotonic-clock TTL purge and a max-entry cap,
    modeled on `browser_sessions.py`; `redeem` pops (single-use) and compares
    `owner_sub`.
  - `RedisSecretDeliveryBuffer`: `SET secret_delivery:{id} <json> EX <ttl>`;
    `redeem` uses atomic `GETDEL` then compares `owner_sub` (a mismatch is treated
    as not-found and the value is already gone — fail-safe). A wrong identity
    (including the approver) cannot redeem; the `delivery_id` is an unguessable
    `uuid4`, so owner-scope is defense-in-depth over it.
- the redemption endpoint `GET /api/v2/secrets/delivery/{delivery_id}` is a
  tool-gateway route: it verifies the delegated token (`token_verifier`), calls
  `redeem(id, sub)`, and returns `{value}` on success or a structured
  `404`/`410`-style body on not-found/spent/expired (never distinguishing them to
  the caller beyond a single "unavailable" posture, to avoid an oracle). On
  success it emits `secret_delivered` (`channel: portal_copy`, recipient = the
  operator). The value is returned **only** on this one-time authenticated call —
  it rides no stream frame, no render tree, no log.
- the kernel emits a dedicated `secret_delivery` frame (schema v12) when a
  `secrets.generate_password` result carries a `delivery_id`, as a sibling of the
  `tool_result` frame in `ToolEvidenceMiddleware`. It carries `delivery_id`,
  `channel`, `expires_at` (and `recipient` for external channels) — never the
  value. The portal renders the Copy-password control from it. A dedicated frame
  (rather than riding `tool_result.data`) is a stable contract independent of the
  `data` size-cap omission and is self-describing to the portal.
- alternatives rejected: value-in-frame (the leak the spec exists to prevent);
  process-local-only with no `Protocol` (deepens the `replicas: 1` constraint the
  spec refuses to worsen); a durable vault (Non-Goal). The stateless
  encrypted-handle variant is recorded in ADR-0012 and deferred.

### R-4: Optional email delivery channel (gated outbound)

- affected files: `tools/secrets_connector.py` (the `secrets.deliver` dispatcher +
  `EmailChannel`), `core/config.py`, `products/agent-platform/src/agent_service/services/hitl_confirmations.py`
  (the card formatter), `services/secret_params.py`,
  `shared/shared-contracts/policies/policy-default.yaml`
- chosen approach: `DeliverSecretTool(BaseTool)` at `risk_level="write"`,
  `extra_required_actions=("secrets:deliver",)`, `category="secrets"`. It is the
  `secrets.deliver(channel, password, recipient?)` dispatcher: it looks up the
  channel sender and delegates. It parks one HITL card (write-tier → the kernel
  ASKs; tier_2 via `require-approval-tools-mutate`, self-approval blocked). On
  approval the execution worker invokes it and `EmailChannel` sends over TLS via
  `GATEWAY_EMAIL_*` (stdlib `smtplib`/`aiosmtplib`), never logging the value or
  the body. The `password` input masks in the `tool_call` frame via the existing
  name-based `redact_evidence_parameters`.
- fail-closed: unconfigured SMTP → a structured `EMAIL_NOT_CONFIGURED` result,
  nothing sent. `GATEWAY_EMAIL_STRICT_ALLOWLIST=true` + an out-of-allowlist
  recipient → `EMAIL_RECIPIENT_NOT_ALLOWED`, nothing sent.
- the card formatter `_cr_secrets_deliver(parameters, display_hint)` sits beside
  `_cr_http_post` in `hitl_confirmations.py`, registered in
  `_CHANGE_REQUEST_FORMATTERS`. Its summary names recipient + channel only
  ("Email a generated secret to <recipient>"); the `password` field renders
  `masked=True`. When the recipient is out-of-allowlist (per
  `AGENT_EMAIL_RECIPIENT_ALLOWLIST`) the summary leads with the prominent warning
  the approver must acknowledge (D-7). `secret_delivered` (`channel: email`) fires
  at SMTP accept.
- `policy-default.yaml` gains an `allow-operators-secrets-deliver` rule granting
  `secrets:deliver` to `["platform-admin", "approver", "operator"]` (mirroring
  `allow-operators-tools-mutate`: the approver carries it so a tier_2-approved
  send executes on the confirmer's delegated token). The bundle `version` stays
  `1` — **corrected at build time**: `validate_policy.py` hard-fails on any
  `version != 1`, and the field is a *bundle-format* version, not a content
  revision (git shows it has been `1` since creation while ~15 rules were added
  across SPEC-021/030/039/044/045/055). The header's "bump on every rule change"
  comment (SPEC-048 R-1) is review discipline that the validator actively
  contradicts, so the new rule follows the living pattern and lands at `version:
  1`. Synced via `make sync-policy`.
- alternatives rejected: a separate `secrets.deliver_email` tool (rejected by the
  user in favor of the single dispatcher); email at read tier (it sends a secret
  to a third party — it must gate).

### R-5: An extensible delivery-channel interface

- affected files: `tools/secret_delivery.py` (the `DeliveryChannel` interface +
  registry), `tools/secrets_connector.py`
- chosen approach: a `DeliveryChannel` `Protocol` — `name`, and
  `send(value, recipient, context) -> DeliveryOutcome` — held in a connector-owned
  `_channels` registry with `register_channel` as the sole extension seam
  (`register_channel` refuses to replace the generation-only `portal_copy`).
  `PortalCopyChannel` (stash → `delivery_id`, invoked from generation) and
  `EmailChannel` (SMTP, invoked from `secrets.deliver`) are the first two.
  Adding Teams/Slack is a new sender class + a registry entry + its config; a test
  asserts the registry is the only seam (no change to generation, the buffer, the
  audit event or the masking). Every channel's outcome carries `channel` so
  `secret_delivered` is attributable regardless of transport.
- alternatives rejected: a per-channel `if/elif` in the tool (not additive).

### R-6: Skill and policy guidance

- affected files: `shared/platform-ops/skills/` (a new `knowledge` skill),
  `samples/acme-admin/password-reset/skill/ResetAcmePassword.md`,
  `samples/acme-admin/composition/skill/RecoverAcmeAccount.md`
- chosen approach: a `knowledge`-kind skill documents when to generate vs. accept
  a supplied password, cites the R-2 contract **by reference** (no divergent
  numbers), names the delivery options, and instructs the model never to restate a
  generated value in prose (defense-in-depth over the R-1 fix 2 harvest). The two
  reset runbooks gain an "if no password is supplied, generate one to policy and
  hand it over via the Copy-password control" branch. Discoverable by
  `skills.search` for a "generate a password" intent.

### R-7: Configuration, wiring, and activation documentation

- affected files: `products/tool-gateway/src/tool_gateway/core/config.py`, `app.py`,
  `products/agent-platform/src/agent_service/runtime_settings.py`,
  `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env` +
  `runtime-secrets.example.env`, a `sync-email-secrets.sh` script,
  `docs/guides/configuration-reference.md`, `docs/guides/tool-configuration.md`
- chosen approach: `GATEWAY_*` settings on `GatewaySettings.from_env()` following
  the frozen-dataclass convention, all deny-by-default: `GATEWAY_SECRETS_ENABLED`
  (discovery gate), `GATEWAY_PASSWORD_POLICY_PATH` + tightening overrides,
  `GATEWAY_SECRET_DELIVERY_BACKEND`/`_TTL_SECONDS`/`_REDIS_*`,
  `GATEWAY_EMAIL_HOST`/`_PORT`/`_USER`/`_PASSWORD`/`_FROM`/`_USE_TLS`,
  `GATEWAY_EMAIL_RECIPIENT_ALLOWLIST`, `GATEWAY_EMAIL_STRICT_ALLOWLIST`.
  agent-platform gains `AGENT_EMAIL_RECIPIENT_ALLOWLIST` (card posture). The
  connector is gated in `app.py` on `GATEWAY_SECRETS_ENABLED` with the lazy-import
  pattern; the buffer is built once and held beside the browser pool. Secrets
  (SMTP password) go in `runtime-secrets.example.env` provisioned by a new
  `sync-email-secrets.sh`, never in the ConfigMap. Each variable is documented
  with its default and cross-service chain, plus a Feature Activation Matrix row;
  email is **off** in the base overlay.
- alternatives rejected: gating on policy-path presence alone — the boolean is the
  honest switch (the `GATEWAY_HTTP_ENABLED` precedent), and an operator who sets
  the path but not the flag should get a clear startup log, not a silently
  unregistered tool.

### R-8: Tests and delivery traceability per ADR-0008

- affected files: `products/tool-gateway/tests/test_secrets_connector.py` (new),
  `test_secret_delivery.py` (new), `products/agent-platform/tests/test_kernel_middleware.py`,
  `tests/test_prose_redaction.py`, `tests/test_hitl_confirmations.py`,
  `tests/test_secret_delivery_integration.py`, `shared/shared-contracts/scripts/`
  (the validator), `shared/platform-ops/e2e/secret-delivery-demo.sh` (new), root
  `Makefile`, this spec's `tasks.md`
- chosen approach: every R-x acceptance criterion maps to at least one asserting
  test recorded in `tasks.md`. The buffer is tested through **both** backends
  (in-memory directly; Redis against a fake/`fakeredis` or a skipped-if-absent
  live client) for single-use, TTL expiry, and owner-scope. The no-plaintext
  guarantee is asserted **per projection**: the `tool_result` frame, the
  transcript, the title, the live stream text and the card each assert the value's
  absence (masked or never present). Generation asserts the CSPRNG source by
  monkeypatching `secrets`, policy conformance, floor enforcement and fail-closed
  refusal. Email asserts fail-closed, the `secrets:deliver` gate, the allowlist
  warn/strict behavior, and that the value is never logged. The channel-interface
  seam and the named-policy additivity each get a structural test. The e2e script
  generates a password, redeems it via the Copy-password path, and asserts the
  value is absent from every projection while `secret_delivered` is present; it is
  added to the `e2e` target's list.

## Sequencing And Dependencies

1. Contracts (stage 1) — depend on nothing; must land whole so `make verify`
   stays green before code reads them.
2. Configuration (stage 2) — depends on nothing.
3. Buffer + connector + redemption route (stage 3) — depends on stages 1–2
   (the contract loader, the settings).
4. Kernel redaction fixes + `secret_delivery` frame + email card (stage 4) —
   depends on stage 3's real tool names; `redact_result_data` and the harvest are
   independent of the gateway and can land in parallel with stage 3.
5. platform-gateway extra-action hook + `ACTION_SECRETS_DELIVER` + redemption
   proxy; portal Copy-password control (stage 5) — depends on stages 3–4 (the
   redemption endpoint, the `secret_delivery` frame contract).
6. Skill, samples, docs, GitOps, e2e (stage 6) — depend on stages 2–5 being
   settled, since the docs name final error codes and env vars.
7. Tests (stage 6) — written alongside each stage, run as one suite at the end.

## Test Strategy

- unit tests: `test_secrets_connector.py` covers generation (policy conformance,
  all four classes incl. non-alphabetic, CSPRNG source by monkeypatch, floor
  raise, fail-closed refusal, two calls differ), the handoff stash, and the
  `secrets.deliver` dispatcher (channel lookup, email fail-closed, allowlist
  warn/strict, `secrets:deliver` denial). `test_secret_delivery.py` covers both
  buffer backends for single-use / TTL / owner-scope and the channel-interface
  seam. Kernel-side: `redact_result_data` masks the generated field while the raw
  result is untouched; the harvest makes a model restatement mask in prose/title/
  transcript; the `secret_delivery` frame carries `delivery_id` and never the
  value; `_cr_secrets_deliver` names recipient + channel and masks the password,
  with the digest-invariance assertion the other formatters carry.
- mutation spot-checks on the security-critical behaviors: deliberately un-mask
  the `tool_result` data, drop the harvest, and weaken the owner-scope check — the
  suite must fail for each.
- contract tests: the `secret_delivery` frame validates against
  `agent-stream-event.schema.json` v12; `secret_delivered` validates against the
  audit-event enum; `validate_password-policy` pins the tool floor to the
  contract; `validate-policy` stays green against the extended version-1 bundle;
  the stream schema title advances to v12 with its stable `$id` unchanged;
  `tool-result.schema.json` is unchanged (generic envelope, free-form `data`).
- integration / overlay validation: `make verify` includes the new
  `validate-password-policy` and local `secret-delivery-demo` legs, alongside
  `validate-secret-vocabulary` and all overlays. The sample entry point runs a
  real connector/kernel/persistence/redemption roundtrip plus platform proxy and
  portal DOM/clipboard tests; installed portal npm dependencies are required.
  `make e2e` also defaults this script to local mode. Actual live generation and
  redemption require explicitly invoking `secret-delivery-demo.sh --live` with
  operator/audit credentials and cluster log access. Mocked-I/O tests compile
  and exercise that script's success and sanitized-failure paths without a cluster.

## Rollout And Migration

- deployment/configuration changes required: none to activate by default.
  `GATEWAY_SECRETS_ENABLED` ships `false` and email is unconfigured in the base
  overlay, so an existing cluster gains nothing and loses nothing on upgrade.
  Activation is a Feature Activation Matrix checklist (enable secrets, mount the
  policy contract, optionally configure SMTP + allowlist, optionally select the
  Redis buffer backend for `replicas > 1`).
- backward compatibility notes: the connector registers no tool until enabled, so
  discovery output is unchanged for every existing deployment. The contract
  changes are additive: a new audit enum member, a new stream frame type (v12,
  `additionalProperties` already governs older clients which simply ignore the new
  frame), and a new policy action + rule (the bundle `version` stays `1` — see
  R-4; the validator pins the format version). The
  `extra_required_actions` field defaults to `()`, so every existing tool's
  admission path is byte-identical. `redact_result_data` masks only secret-named
  result fields, so no existing tool's result projection changes (none return a
  `password` field today).
- rollback approach: set `GATEWAY_SECRETS_ENABLED=false` and the tools disappear
  from discovery on the next gateway start. The in-memory buffer is ephemeral, so
  an in-flight handle is unredeemable after a restart; a Redis-backed buffer
  survives the restart but each handle still expires at its TTL and redeems only
  once, so nothing lingers indefinitely. `sync-email-secrets.sh` provisions the
  optional SMTP Secret via stdin and has no removal counterpart — retract email by
  deleting that Secret out-of-band (or leaving it unset) and keeping
  `GATEWAY_SECRETS_ENABLED=false`; the connector fails closed without SMTP config.
  Reverting the code is safe — the new stream frame and audit enum are additive,
  and no projection stores a shape a rollback could not read.
