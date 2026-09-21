# SPEC-062: Secure Password Generation and Delivery Tools

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-21
- approved: 2026-09-21
- delivered: 2026-09-22 (v0.41.0)
- release slice: R5 — Hardening and External Consumption (twenty-fourth R5
  slice; target release **v0.41.0**, the next minor after the current 0.40.0,
  or bundled if it lands alongside another slice; recorded on the
  `delivery-roadmap.md` exploration backlog)
- related ADRs: **ADR-0012** (one-time secret-delivery handoff) records R-3's
  trust-model decision — a narrow, server-mediated secret-*retrieval* path that
  sits **beside** the SPEC-049 R-5 / SPEC-055 R-7
  no-plaintext-in-any-human-readable-projection posture without excepting it
  (the value never rides a projection at all — see R-3). **ADR-0011**
  (a composition carries no authority) is relevant lineage: a generation or
  delivery step referenced by a composition keeps its own gate, exactly as a
  sub-skill does.
  lineage: extends SPEC-049 (credential sets and the masking posture this
  spec must not weaken), SPEC-055 R-7 (fail-closed masking at the approval
  seam), SPEC-009 (redaction at the gateway choke point), SPEC-007 (tool
  execution framework — `BaseTool`/`ToolRegistry`/`ToolResult`), SPEC-058
  (the most recent tool-gateway connector, and the
  [`adding-a-tool.md`](../../guides/adding-a-tool.md) discipline this follows),
  SPEC-054 (the action card an email delivery parks), SPEC-021 (bounded
  mutating actions), SPEC-014 (the knowledge skill that documents the policy).
- drafting: from the 2026-09-21 design discussion that made the `acme-admin`
  reset walkthroughs conversational (a doc-only change shipped alongside this
  spec). That work surfaced the missing half: an operator who can say "reset
  dave's password" conversationally should also be able to say "…and generate a
  strong one," which the platform can neither do today nor hand back securely.

## Summary

Give the agent two new tool-gateway primitives — **generate** a
cryptographically strong password to a centralized policy, and **deliver** a
generated secret back to a human without ever rendering it as plaintext in a
chat projection. Generation is a read-tier CSPRNG tool (never model-invented);
delivery is a one-time, owner-scoped, server-mediated handoff whose primary
channel renders a **Copy password** button in the portal (value to clipboard,
chat box stays clean) and whose optional second channel emails it through a
gated outbound tool. The delivery mechanism is a small channel interface so
Teams/Slack join later without a redesign.

## Motivation

**A reset requires the operator to invent the password.** Every shipped reset
path — [`password-reset`](../../../samples/acme-admin/password-reset/WALKTHROUGH.md),
the [`composition`](../../../samples/acme-admin/composition/WALKTHROUGH.md)
recovery, and
[`adhoc-password-reset`](../../../samples/acme-admin/adhoc-password-reset/WALKTHROUGH.md)
— takes the new one-time value as a chat-supplied secret. There is no way to
ask the platform to produce a strong one, and no password-strength rule stated
anywhere the agent or a skill author can rely on: each operator types whatever
they remember, and each skill restates its own expectation.

**The platform has no secure way to hand a secret back.** This is the real
reason the feature is a spec and not a connector. The masking posture is
deliberate and load-bearing: a value the operator types is harvested from their
own message and masked in the durable transcript, the live stream, the minted
session title, every confirmation card, and every tool-evidence frame
([`prose_redaction.py`](../../../products/agent-platform/src/agent_service/services/prose_redaction.py),
[`secret_params.py`](../../../products/agent-platform/src/agent_service/services/secret_params.py)).
`prose_redaction` exists *because* a live run once ended with the model writing
"the temporary password `TempPass-2026!` is now in this chat transcript." A
chat-supplied password is safe to mask because the operator already knows it. A
**generated** password inverts that: mask it and the operator can never retrieve
it (the account is unusable); print it and it is the exact leak the redaction
stack was built to prevent — and worse, a tool-generated value is *not* caught by
`prose_redaction`'s literal harvesting, which only mines **user** text, so a
model restating it would land in the transcript unmasked. Retrieval, not
generation, is the hard problem, and R-3 is why.

**Why now.** The conversational reframe just shipped makes "reset dave's
acme-admin password and unlock him" a natural request; the missing half is "…and
give me a strong one I did not have to invent." The generation half is cheap and
self-contained; the delivery half touches the trust model and must be designed
before it is built, which is precisely what a spec is for
([`docs/specs/README.md`](../README.md): a change that "affects the trust model"
or "changes identity, policy, approval, audit, or execution behavior" requires
one).

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: `secrets.generate_password` — a read-tier CSPRNG generation tool

A new tool-gateway connector registers `secrets.generate_password(length?,
policy?)` at `risk_level="read"`, `category="secrets"`, returning the standard
`ToolResult` envelope. The value comes from Python's `secrets` module (a
CSPRNG) — **never** from the model, whose "randomness" is neither seeded nor
uniform and is therefore guessable. Generation mutates nothing, so it parks no
card and needs only `tools:invoke`.

The generated value is a secret from the moment it exists: the result field that
carries it is added to the gateway/kernel secret vocabulary (the
`OPAQUE_VALUE_FIELDS` posture in
[`secret_params.py`](../../../products/agent-platform/src/agent_service/services/secret_params.py))
so it masks in every evidence, transcript, title and card projection. The value
stays real only in the agent's own working context — exactly the posture a
chat-supplied password already holds — so the agent can pass it to the reset
(`web.type.text`, itself masked) or to delivery (R-3).

Acceptance criteria:

- The tool appears in discovery when and only when the connector is configured
  (R-7), requires only `tools:invoke`, and parks no confirmation card.
- A generated value meets the active policy (R-2): the required length and every
  required character class, including a non-alphabetic character.
- Generation draws from `secrets` (asserted by construction/monkeypatch, not by
  eyeballing output); two calls differ.
- The generated value is masked to `***` in the tool-evidence frame, the durable
  transcript, the session title, and any card — asserted, per projection.
- A `length` below the policy floor is refused or raised to the floor (D-4); a
  request the policy cannot satisfy (e.g. length 2 with four required classes)
  fails closed with `INVALID_PARAMETERS`, never a weak value.

### R-2: Password policy as a single source of truth

The strength rules are defined **once** and enforced everywhere. **Home
(resolved — hybrid):** a versioned `password-policy` contract beside
[`policy-default.yaml`](../../../shared/shared-contracts/policies/policy-default.yaml)
is the single source of truth the generation tool reads and the knowledge skill
(R-6) cites by reference; gateway env vars may **only tighten** it (raise the
length, add required classes), never weaken below the contract floor. This
mirrors the policy-bundle pattern (centrally authored, synced, fail-closed)
while keeping per-deployment hardening. A `make verify` leg
(`validate-password-policy`) pins tool and contract in agreement, mirroring
`validate-secret-vocabulary`'s drift guard.

**Shape (resolved):** ship **one `default` policy** for this slice; the tool
accepts caller-*tightening* params (`length` ≥ floor, `exclude_ambiguous`). The
contract is defined so **named policies** (`default`, `strict`) are purely
additive later — a skill can then reference one by name — but none ship until a
real need appears.

**The `default` floor (resolved):**

- `min_length`: **16** (hard floor **12** — a caller may raise it, never drop
  below).
- `required_classes`: uppercase **+** lowercase **+** digit **+**
  **non-alphabetic/symbol** — all four mandatory (the non-alphabetic requirement
  is explicit).
- `entropy_floor_bits`: **64** as a backstop (16 chars over the ~94-char
  printable alphabet is ≈100+ bits, so it is comfortably met).
- `exclude_ambiguous` (I/l/1/O/0): **optional, default off** — the value is
  copied or emailed, not retyped from a screen, so entropy-first wins; a caller
  may enable it.
- **Not in v1:** dictionary/breached-corpus checks (needs a breach list; noted
  as future work).

Acceptance criteria:

- Exactly one authoritative policy definition exists (the contract); the tool
  reads it, env overrides may only tighten it, and the skill cites it rather
  than restating divergent numbers.
- A `validate-password-policy` verify leg fails the build if the tool's enforced
  policy and the contract drift apart (the `validate_secret_vocabulary.py`
  pattern).
- A generated value under `default` is ≥ 16 chars and contains all four required
  classes including a non-alphabetic character; a caller-tightened request
  (longer, `exclude_ambiguous`) is honored; a request below the floor is refused
  or raised (R-1).
- Named policies are additive: introducing `strict` touches only the contract
  and the tool's policy lookup, never the callers (asserted by a test).

### R-3: One-time secure delivery to the operator (primary channel — the Copy-password handoff)

The primary delivery channel hands the generated value to the operator **without
the value ever entering a human-readable projection**. **Mechanism (resolved —
redemption-on-click, D-1):** the agent calls a delivery tool with the value; the
service stashes it in an **ephemeral, single-use, TTL-bounded, owner-scoped**
server-side buffer (never the transcript, evidence, or audit store) and returns
an opaque `delivery_id` — **not the value** — into the stream. The portal renders
a **Copy password** button bound to that id. Clicking it performs an
authenticated, single-use redemption — a one-time
`GET …/secrets/delivery/{id}` scoped to the session owner — that writes the value
to the clipboard and invalidates the handle. The value never rides the stream,
the render tree, or a log, so R-3's no-projection guarantee is **structural**,
not a rendering convention. The chat box never shows the value; the transcript,
title, cards and evidence never carry it.

**Buffer backend (resolved — replica-ready, D-2).** Every dev-k8s deployment is
`replicas: 1` today, so an in-process buffer would work, but agent-platform
already holds per-process state (the `ConfirmationRegistry` pending map) that is
not replica-safe, and this spec must not silently deepen that constraint. The
buffer therefore sits behind a small `Protocol` with two backends, mirroring
[`session_store.py`](../../../products/agent-platform/src/agent_service/services/session_store.py):
an **in-memory** backend (default; dev/CI, `replicas: 1`) and a **Redis** backend
(`replicas > 1`) using the already-deployed Redis (the kernel message bus), whose
`EXPIRE` gives the TTL and atomic `GETDEL` gives single-use redemption. A
**stateless encrypted-handle** variant (the `delivery_id` *is* the sealed value;
single-use via a spent-nonce set) is noted as the most secret-safe alternative
and deferred to `plan.md`.

This is the crux the spec exists to settle: with redemption-on-click the value
rides **no** projection, so the SPEC-049 R-5 / SPEC-055 R-7 posture is preserved,
not excepted. The delivery is recorded as an **event** (`secret_delivered`:
`delivery_id`, `channel`, recipient, acting identity, timestamp — never the
value).

Acceptance criteria:

- The generated value appears in **no** persisted or streamed human-readable
  projection: transcript, session title, live stream text, confirmation card,
  and tool-evidence frame each assert its absence (the value is masked or simply
  never present).
- The portal renders a Copy-password control, never the plaintext; clicking it
  places the value on the clipboard and the control moves to a spent state.
- The handle is single-use (a second redemption fails), TTL-bounded (an expired
  handle renders "delivery expired"), and owner-scoped (a different authenticated
  identity — including the approver — cannot redeem it).
- The buffer backend is pluggable: the in-memory and Redis backends both satisfy
  the single-use / TTL / owner-scope contract, and a test exercises each (D-2).
- A `secret_delivered` audit event fires carrying the channel and recipient but
  **not** the value.
- Reloading the session after delivery shows no value and a spent/expired control
  — nothing plaintext is recoverable from the durable record.

### R-4: Optional email delivery channel (gated outbound)

A second channel emails the generated value to a recipient the operator names in
the request or the skill. It is **off by default** (unconfigured SMTP fails
closed) and, because it sends a secret to a third party, it is a **write-tier,
HITL-gated** outbound action: it parks one `action` card naming the recipient and
channel — never the value — under the existing SPEC-054 change-request machinery.

**Policy action (resolved — D-3):** email delivery requires a **new
`secrets:deliver` action** in addition to `tools:mutate`, so a deployment can
grant "mutate infrastructure" separately from "email a secret externally." The
portal-copy handoff (R-3) needs **no** action — it is owner-scoped retrieval of a
value the operator's own session generated — but it is still audited.

**Recipient exfiltration control (resolved — D-7, both):** a configured allowlist
`GATEWAY_EMAIL_RECIPIENT_ALLOWLIST` (domains and/or exact addresses) **and** a
mandatory action-card confirmation. Because email is always gated (D-5), the
allowlist governs the card's posture: an in-allowlist recipient is a routine
confirm; an out-of-allowlist recipient leads with a prominent "recipient domain
not on the approved list" warning that the approver must explicitly acknowledge.
An optional `GATEWAY_EMAIL_STRICT_ALLOWLIST=true` hard-denies out-of-allowlist
recipients instead of warning (default: warn-and-confirm).

**Tool shape (resolved — D-6):** email is not a separate tool; it is the `email`
channel of the single `secrets.deliver(channel=…)` dispatcher (R-5).

Acceptance criteria:

- Unconfigured SMTP → the tool fails closed with a clear code and sends nothing.
- Configured → the value is sent over TLS, is never logged, and never appears in
  the card, transcript, or evidence (the card names recipient + channel only).
- The send requires `secrets:deliver` (and `tools:mutate`), parks one `action`
  card an approver decides (self-approval blocked per SPEC-030 R-4), and emits
  `secret_delivered` with `channel: email`.
- An in-allowlist recipient shows a routine confirm; an out-of-allowlist
  recipient shows the prominent warning and requires explicit acknowledgment;
  under `GATEWAY_EMAIL_STRICT_ALLOWLIST=true` an out-of-allowlist recipient is
  refused outright.

### R-5: An extensible delivery-channel interface

Delivery is a small interface (`channel` → a sender that takes the ephemeral
handle and a recipient), of which the portal Copy-password handoff (R-3) and
email (R-4) are the first two implementations. Adding Teams, Slack, or another
channel is additive — a new sender plus its config — with no change to generation,
the buffer, the audit event, or the masking posture. The `secret_delivered` event
carries `channel` so every delivery is attributable regardless of transport.

Acceptance criteria:

- A documented channel interface exists; portal-copy and email implement it.
- Adding a hypothetical channel touches only the sender registry and config (a
  test asserts the interface is the only seam).
- Every channel emits `secret_delivered` with its `channel` value and never the
  secret.

### R-6: Skill and policy guidance

A `knowledge`-kind skill documents **when** to generate versus accept a supplied
password, cites the R-2 policy by reference, and names the delivery options. The
`acme-admin` reset runbooks
([`password-reset`](../../../samples/acme-admin/password-reset/skill/ResetAcmePassword.md),
the [`composition`](../../../samples/acme-admin/composition/skill/RecoverAcmeAccount.md))
gain an "if no password is supplied, generate one to policy and deliver it"
branch, so the conversational request "reset dave's password and give me a strong
one" resolves end to end.

Acceptance criteria:

- The skill references the single policy source (no divergent numbers) and is
  discoverable by `skills.search` for a "generate a password" intent.
- At least one reset runbook offers the generate-and-deliver alternative, and a
  `samples/` demo exercises it (R-8).

### R-7: Configuration, wiring, and activation documentation

New environment variables follow the `from_env()` config pattern, are documented
in [`configuration-reference.md`](../../guides/configuration-reference.md) with a
Feature Activation Matrix row, and land in the dev-k8s overlay with email **off**
by default. The generation tool is discoverable only when configured. The
variables span: generation enablement; the policy contract path and any
tightening overrides (R-2); the delivery-buffer backend selection and TTL (R-3,
mirroring `SESSION_STORE_BACKEND`); the `secrets:deliver` policy action wiring
(R-4); and `GATEWAY_EMAIL_*` SMTP plus `GATEWAY_EMAIL_RECIPIENT_ALLOWLIST` and
`GATEWAY_EMAIL_STRICT_ALLOWLIST` (R-4/D-7).

Acceptance criteria:

- Each new variable is parsed/validated in the owning service's config and
  documented with its default and its cross-service chain.
- Email delivery is inert until SMTP is configured; generation and the
  portal-copy channel work with no email config present.
- The buffer backend defaults to in-memory and selects Redis when configured,
  matching the session-store backend convention (R-3/D-2).
- The `secrets:deliver` action is registered in the policy bundle and synced via
  the existing `make sync-policy` workflow (R-4/D-3).

### R-8: Tests and delivery traceability per ADR-0008

Every `R-x` acceptance criterion maps to at least one asserting test, recorded in
this spec's `tasks.md`, and the shipped `samples/` demo is exercised in the
verification path. R-3's trust-model decision is recorded in **ADR-0012**, which
this spec depends on (D-8).

Acceptance criteria:

- Unit tests cover generation (policy conformance, CSPRNG source, floor
  enforcement), the delivery buffer (single-use, TTL, owner-scope, **both the
  in-memory and Redis backends**), the no-plaintext-in-projection guarantee per
  carrier, email (fail-closed, `secrets:deliver`-gated card, audited, allowlist
  warn/strict behavior), and the channel interface seam.
- A `validate-password-policy` verify leg asserts the tool's enforced policy
  equals the contract (R-2), wired into `make verify`.
- A sample demo leg generates a password, delivers it via the Copy-password
  channel, and asserts the value is absent from every projection while the
  delivery event is present.

## Non-Goals

- **Model-side password generation.** Explicitly rejected: an LLM is not a
  CSPRNG. R-1's whole point is that randomness comes from `secrets`, not the
  model.
- **A secret vault or durable secret store.** Generated values live only in an
  ephemeral single-use buffer (R-3) and the agent's transient context; nothing is
  persisted. Long-lived secret management is out of scope.
- **Teams, Slack, SMS, or other channels.** Deferred; R-5's interface
  accommodates them, and email (R-4) is the one optional channel this slice
  proves the abstraction with.
- **Credential rotation or existing-secret retrieval.** `k8s.rotate_secret` and
  the credential-set machinery already exist and are untouched.
- **Changing the chat-supplied password path.** Typing a one-time value into the
  chat stays fully supported; generation is an alternative, not a replacement.
- **A general-purpose secrets-management or notification system.** This is a
  password generation-and-handoff pair, not a secrets platform.

## Impact

- products touched: `products/tool-gateway` (new `tools/secrets_connector.py`,
  `core/config.py`, `app.py`, tests); `products/agent-platform`
  (`services/secret_params.py` — the generated-value field joins the masking
  vocabulary; the delivery stream frame + the ephemeral single-use buffer behind
  a pluggable in-memory/Redis `Protocol`; a curated change-request formatter for
  the email card; tests); `products/operator-portal` (the Copy-password control +
  the one-time authenticated redemption; tests); `products/platform-gateway`
  (proxy the one-time delivery redemption and enforce the `secrets:deliver`
  action).
- shared touched: `shared/shared-contracts` (the stream-event schema for the
  delivery frame — a version bump; the audit-event vocabulary for
  `secret_delivered`; the **new `password-policy` contract** (R-2) plus a
  `validate-password-policy` script under `scripts/`; the `secrets:deliver`
  action added to `policy-default.yaml` and synced via `make sync-policy`);
  `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env` and
  an email-secret sync script; a `shared/platform-ops/skills/` knowledge skill
  (R-6).
- contracts touched: `agent-stream-event.schema.json` (new one-time delivery
  frame; version bump), the shared audit-event vocabulary (new `secret_delivered`
  type), and a new `password-policy` contract (R-2). `tool-result.schema.json`
  is unchanged (generic envelope, free-form `data`).
- identity / policy / audit / execution safety impact: **one new audit event type
  (`secret_delivered`)** and **one new policy action (`secrets:deliver`)** for the
  outbound email channel (D-3). Generation and the portal-copy handoff are
  owner-scoped retrieval of a value the operator's own session generated and need
  no new action (D-3, D-5). Email delivery is a write-tier outbound action:
  HITL-gated, self-approval-blocked, and — because it can exfiltrate a secret to
  an arbitrary address — bounded by the D-7 recipient allowlist plus mandatory
  card confirmation. The new secret surface is the generated value itself, and the
  control is that it rides no projection (R-3) and lives only in an ephemeral
  single-use buffer.
- living state docs to update on delivery:
  [`docs/guides/tool-configuration.md`](../../guides/tool-configuration.md) (tool
  inventory, activation, error codes),
  [`docs/guides/configuration-reference.md`](../../guides/configuration-reference.md)
  (the new variables + Feature Activation Matrix row),
  [`docs/guides/skills-guide.md`](../../guides/skills-guide.md) (the policy skill
  and the generate-and-deliver request shape), the `acme-admin` reset
  walkthroughs, [`docs/specs/README.md`](../README.md) (this row → `delivered`),
  `docs/agentic-aiops-platform/delivery-roadmap.md`, `CHANGELOG.md`, `VERSION`.

## Resolved Decisions

All eight design questions from the 2026-09-21 draft were resolved on
2026-09-21; none remain open, so this spec is `approved`.

- **D-1 — delivery mechanism: redemption-on-click.** The Copy button triggers a
  one-time authenticated `GET …/secrets/delivery/{id}`; the value never enters
  the stream, the render tree, or a log, making R-3's no-projection guarantee
  structural.
- **D-2 — buffer: pluggable, replica-ready.** A `Protocol` with an in-memory
  backend (default; `replicas: 1`) and a Redis backend (`replicas > 1`, TTL via
  `EXPIRE`, single-use via atomic `GETDEL`), mirroring `session_store.py`. A
  stateless encrypted-handle variant is noted and deferred to `plan.md`.
- **D-3 — policy action.** Email requires a new `secrets:deliver` action plus
  `tools:mutate`; the portal-copy handoff needs no action (owner-scoped
  retrieval) but is audited.
- **D-4 — policy home + shape.** Hybrid: a versioned `password-policy` contract
  is the source of truth; env may only tighten. One `default` policy ships
  (min length 16 / floor 12, all four classes including non-alphabetic, entropy
  ≥ 64 bits, `exclude_ambiguous` optional and default off); named policies are
  additive later. A `validate-password-policy` leg guards drift.
- **D-5 — tiers.** Generation is read-tier/no-card; portal-copy is ungated
  owner retrieval; email is write-tier/gated. Generation needs no gate.
- **D-6 — tool shape.** One `secrets.deliver(channel=…)` dispatcher over
  per-channel senders, so channels stay additive.
- **D-7 — email exfiltration control: both.** A recipient allowlist
  (`GATEWAY_EMAIL_RECIPIENT_ALLOWLIST`) plus mandatory card confirmation;
  out-of-allowlist recipients get a prominent warning requiring explicit
  acknowledgment, with an optional `GATEWAY_EMAIL_STRICT_ALLOWLIST=true`
  hard-deny.
- **D-8 — roadmap + ADR.** Twenty-fourth R5 slice; target **v0.41.0**; R-3's
  trust-model decision is recorded in **ADR-0012** (one-time secret-delivery
  handoff), while R-1/R-2 are spec-local and stay in `plan.md`.

## Changelog

- 2026-09-21: created as `draft` from the conversational-reset design discussion;
  generation + delivery split, redemption-on-click recommended, email exfiltration
  control (D-7) flagged as approval-blocking.
- 2026-09-21: all eight open questions (D-1…D-8) resolved; decisions folded into
  R-1…R-8 and the Impact section, Open Questions replaced by Resolved Decisions,
  **ADR-0012** recorded for R-3's one-time secret-delivery handoff, target set to
  v0.41.0 (twenty-fourth R5 slice); status → `approved`.
