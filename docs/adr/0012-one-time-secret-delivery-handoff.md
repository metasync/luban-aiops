# ADR-0012: A Generated Secret Is Redeemed on Click and Rides No Projection

## Status

`accepted`

- date: 2026-09-21
- accepted: 2026-09-21
- amended: 2026-09-23 (reveal-on-commit timing + deny-path discard, v0.42.0 — see
  Decision 6)
- deciders: workspace maintainers
- related specs: SPEC-062 (secure password generation and delivery — R-3 blocks
  its approval on this decision), SPEC-049 (credential sets and the
  no-plaintext-in-any-human-readable-projection posture this preserves, R-5),
  SPEC-055 (fail-closed masking at the approval seam, R-7), SPEC-054 (the
  `action` card an external delivery channel parks), SPEC-009 (redaction at the
  gateway choke point); **extends the SPEC-049 R-5 / SPEC-055 R-7 posture without
  excepting it**
- lineage: ADR-0011 (a composition carries no authority) — a generation or
  delivery step referenced by a composition keeps its own gate, exactly as a
  sub-skill does

## Context

The platform masks a secret in every human-readable projection: the durable
transcript, the live stream, the minted session title, every confirmation card,
and every tool-evidence frame (`prose_redaction.py`, `secret_params.py`). That
posture is deliberate and load-bearing — a live run once ended with the model
writing "the temporary password `TempPass-2026!` is now in this chat transcript."

A **chat-supplied** password is safe to mask because the operator already knows
it. A **generated** password inverts the problem:

- mask it and the operator can never retrieve it, so the account is unusable;
- print it and it is the exact leak the redaction stack was built to prevent;
- and worse, `prose_redaction`'s literal harvesting mines **user** text only, so
  a tool-generated value the model restates would land in the transcript
  **unmasked**.

SPEC-062 splits the capability into a CSPRNG generation tool (randomness from
Python's `secrets`, never the model) and a delivery step. Generation is
spec-local. **Delivery is the trust-model decision**: how a generated secret
reaches a human without ever becoming a projection. This ADR records it.

## Decision

1. **Redemption-on-click.** The generated value never rides any projection. The
   delivery step stashes it in an **ephemeral, single-use, TTL-bounded,
   owner-scoped** server-side buffer and returns an opaque `delivery_id` — not
   the value — into the stream. The portal renders a **Copy password** button
   bound to that id; clicking it performs a one-time authenticated
   `GET …/secrets/delivery/{id}` scoped to the session owner, writes the value to
   the clipboard, and invalidates the handle. The no-projection guarantee is
   therefore **structural**, not a rendering convention.
2. **The buffer is replica-ready, not process-pinned.** It sits behind a small
   `Protocol` with an in-memory backend (default; dev/CI, `replicas: 1`) and a
   Redis backend (`replicas > 1`) using the already-deployed Redis, whose
   `EXPIRE` supplies the TTL and atomic `GETDEL` supplies single-use redemption —
   mirroring `session_store.py`'s pluggable-backend pattern.
3. **Delivery is audited as an event, never a value.** A `secret_delivered` event
   carries `delivery_id`, `channel`, recipient, acting identity and timestamp —
   never the secret.
4. **Channels are additive behind one dispatcher.** A single
   `secrets.deliver(channel=…)` fronts per-channel senders. The portal-copy
   handoff is ungated owner-scoped retrieval (still audited); an **external**
   channel (email) is write-tier, requires a distinct `secrets:deliver` action,
   and is bounded by a recipient allowlist plus mandatory action-card
   confirmation.
5. **The posture is preserved, not excepted.** Because the value rides no
   projection at all, there is nothing to mask; the SPEC-049 R-5 / SPEC-055 R-7
   invariant holds unchanged for generated secrets.
6. **Reveal-on-commit timing (amendment, v0.42.0).** The `delivery_id` frame is
   emitted when the value is redeemable *in context*, not the instant generation
   returns. When a generation is followed in the same turn by a gated mutation, the
   frame is **withheld at generation** and released only once that gate is approved
   **and** its gated call executes successfully; a **standalone** generation reveals
   at that turn's end; a **deny, gated-call failure, or expiry** burns the held value
   silently (no frame). The frame shape is unchanged — its presence still means
   "redeemable" — and it is persisted under the original `turn_index`, so it replays
   to an operator who reloads after the commit. To span the approval wait, the buffer
   stashes a portal-copy delivery under a longer hold TTL
   (`GATEWAY_SECRET_DELIVERY_HOLD_TTL_SECONDS`, default 900 = the 600s HITL approval
   timeout plus the 300s redemption margin) rather than the standalone redemption
   TTL; the held delivery rides the parked card ephemerally and is never persisted to
   the durable record. The burn is **active**, not merely passive: on deny, gated-call
   failure, or expiry the kernel calls an owner-scoped `discard(delivery_id)`
   (`DELETE …/secrets/delivery/{id}`, the value-less counterpart to `redeem`) that
   destroys the handle at once, so it is not redeemable — even by a direct owner-scoped
   fetch — during the hold TTL. The discard is idempotent, oracle-free (an
   indistinguishable `204` for found / already-spent / expired / wrong-owner /
   malformed alike, mirroring the redeem route's single-`404` posture), best-effort (a
   missing gateway/token or transport failure degrades to the expiry burn, the value
   being inert once the gated reset never commits), and adds **no** audit vocabulary
   or policy action — the deny is already `confirmation_decided`, and the discard logs
   a structured INFO line, never the value. A re-park drains the hold onto the new
   card and returns early, so it never discards.

## Alternatives Considered

- **Value-in-SSE-frame** (the value rides the stream into browser memory and is
  masked in the durable record) — rejected: the plaintext then exists in the live
  stream, the browser render tree, and any stream log; masking degrades to a
  rendering convention; and because `prose_redaction` harvests user text only, a
  model restatement of a tool-generated value could leak unmasked.
- **Process-local in-memory buffer only** (the `ConfirmationRegistry` posture) —
  rejected as the sole design: it silently deepens agent-platform's existing
  single-replica constraint; the `Protocol` + Redis backend keeps delivery
  replica-ready at negligible cost.
- **A durable secret store or vault** — rejected: a one-time generated password
  needs an ephemeral single-use handoff, not long-lived storage; a vault is a far
  larger commitment and out of scope.
- **Model-side generation** — rejected: an LLM is not a CSPRNG (neither seeded
  nor uniform, so guessable); randomness must come from `secrets`.
- **Stateless encrypted-handle** (the `delivery_id` *is* the sealed value, with
  single-use enforced by a spent-nonce set) — **not rejected**: it is the most
  secret-safe option (no plaintext at rest even ephemerally) and is recorded as an
  implementation alternative for SPEC-062's `plan.md`; it trades buffer simplicity
  for envelope key management.

## Consequences

- The no-plaintext-projection invariant is preserved **structurally** for
  generated secrets: no projection carries the value, so masking is never relied
  upon for it.
- A narrow secret-*retrieval* primitive joins the platform — one-time,
  TTL-bounded, owner-scoped, audited — distinct from the credential-set machinery
  (which stores operator-supplied secrets server-side) and from `k8s.rotate_secret`.
- New surface: one audit event type (`secret_delivered`) and one policy action
  (`secrets:deliver`) for external channels.
- Multi-replica deployments take a Redis dependency for the buffer (Redis is
  already present as the kernel message bus); the in-memory default keeps dev/CI
  simple.
- **Accepted trade-off — an extra click.** The operator must click to retrieve the
  value; that is the price of it never being projected.
- **Reveal-on-commit (amendment, v0.42.0)** tightens *when* the Copy-password
  button appears for a gated reset — on the committed turn, never while the
  approval card is pending — without changing the frame, the redemption path, or
  the no-projection guarantee. Because the held delivery is ephemeral park state
  (never persisted), a mid-approval agent-service restart drops it and the value
  expires unreleased: fail-safe, with no leaked secret and no orphaned button.
- **Accepted trade-off — email is an exfiltration vector.** Sending a secret to an
  operator/model-named address is inherently risky; it is bounded by the
  allowlist, mandatory confirmation, an optional strict-deny mode, and the
  `secrets:deliver` action, but the risk is not eliminated — only gated and
  auditable.
- Follow-up work (SPEC-062 `plan.md`): choose the buffer-backend default and
  settle the encrypted-handle question; author the `password-policy` contract and
  its `validate-password-policy` verify leg; implement the `secrets.deliver`
  dispatcher and the portal-copy + email senders; build the portal Copy-password
  control and the one-time redemption endpoint.
