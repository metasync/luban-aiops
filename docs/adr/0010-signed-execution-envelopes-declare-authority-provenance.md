# ADR-0010: Signed Execution Envelopes Declare Their Authority Provenance

## Status

`accepted`

- date: 2026-09-07
- accepted: 2026-09-07
- deciders: workspace maintainers
- related specs: SPEC-054 (action-level HITL approval — R-2 requires this
  decision before the `BROWSER_FLOW_NOT_BOUND` relaxation can ship), SPEC-055
  (develop-as-you-go skill graduation — replay and trace capture consume the
  distinction), SPEC-051 (one HITL gate per mutating browser flow — the flow
  authority this labels), SPEC-037/038 (signed execution requests + isolated
  worker — the envelope this extends); **extends ADR-0007, which stays
  `accepted` and unedited**

## Context

Two builders produce SPEC-037 execution-request envelopes: `build_requests`
(one per parked tool call the operator just approved) and `build_flow_request`
(one per `web.*` write auto-signed under an already-approved flow authority,
ADR-0007 / SPEC-051 R-3). They emit **byte-identical envelope shapes** — same
ten fields, same HMAC-SHA256-over-canonical-JSON scheme — differing only in
values (`confirm_id` reused from the approving card versus the current card).
Nothing on the wire states which authority produced a given request.

Consequently the gateway's browser write path can only distinguish the two
*indirectly*, by checking whether a flow happens to be bound. The
`BROWSER_FLOW_NOT_BOUND` denial in `gate_interaction` has been doing that job
implicitly.

That implicit check is the only thing keeping a known divergence fail-closed:

- The tool-gateway clears `entry.flow` in three places — a redirect that lands
  off the allowlist, `gate_capture`'s off-allowlist halt, and a just-bound flow
  whose navigate failed.
- The kernel's `FLOW_CONTEXTS` is **never cleared**: `_record_flow_context`
  records only on a *successful* `web.navigate` carrying a `flow` dict, and a
  plain navigate carries none.
- Within `AGENT_BROWSER_FLOW_APPROVAL_TTL` (900s default), the flow-signer's
  identity guard still matches the stale context, so the next `web.*` write is
  auto-signed and ALLOWed **with no confirmation card at all**.

Today that write is refused, because the flow no longer exists at the gateway.
It is refused *by accident of a flow-centric guard*, and the guards that would
otherwise bound it — origin match, `risk_class`, step budget — all live inside
`gate_interaction` **after** the flow-existence check, so none of them apply to
a session with no bound flow.

SPEC-054 R-2 must relax that denial: five of the six write-tier browser tools
hard-deny unbound while `web.evaluate`, guarded by the flow-optional
`gate_capture`, already parks a per-action card and executes. Deleting the deny
without replacing it converts an accidental backstop into a fail-open path.
SPEC-055 needs the same distinction independently — its authoring trace records
whether a step was "approved per-action" or "admitted under a flow authority,"
and a graduated replay must know which authority it is spending.

## Decision

Every signed execution-request envelope declares its **authority provenance** —
`approval_kind: action | flow` — stamped by the builder that signs it
(`build_requests` → `action`, `build_flow_request` → `flow`) and therefore
covered by the existing HMAC signature. Enforcement points consume it as a
signed fact, not an unsigned hint: a `flow`-provenance envelope is valid only
where a matching flow is bound, and is refused with a structured
`BROWSER_FLOW_AUTHORITY_STALE` otherwise; an `action`-provenance envelope never
satisfies a bound-flow-only guard. The field is optional on
`execution-request.schema.json` — which declares `additionalProperties: false`,
so it must be added explicitly — and stays out of `required`, so envelopes
predating it remain valid and verification logic is unchanged because the
signature already covers every field present.

## Alternatives Considered

- **Keep relying on `BROWSER_FLOW_NOT_BOUND` as the implicit discriminator** —
  rejected: it is precisely the guard SPEC-054 R-2 must relax, and it answers
  "is a flow bound now?" rather than "what authorized this request?", so it
  cannot separate a legitimately per-action-approved unbound write from a stale
  auto-signed one.
- **Kernel-side clearing of `FLOW_CONTEXTS` / `FLOW_APPROVALS` alone, with no
  envelope change** — rejected as *sufficient*: it removes the known divergence
  trigger and SPEC-054 R-2 requires it, but it is a single-writer fix in one
  product. Any future path that drops or fails to propagate a flow binding
  reintroduces the same fail-open, and the enforcement boundary still cannot
  tell the two authorities apart. Adopted **in addition**, not instead.
- **A separate envelope type or endpoint for flow-auto-signed requests** —
  rejected: duplicates the SPEC-037/038 verification path (token, required
  fields, HMAC, `args_digest`, single-flight on `execution_id`) across two
  shapes and forces the worker to accept both; a labeled field on one shape is
  strictly smaller.
- **An unsigned hint (header, query flag, or result metadata)** — rejected:
  provenance that can be altered without invalidating the signature is not a
  security property. It must ride the signed canonical JSON.
- **Record provenance only in the audit trail** — rejected: audit is a record,
  not an enforcement boundary; this would let the write execute and explain it
  afterwards.
- **One ADR spanning action-approval (SPEC-054) and this rule** — rejected per
  `docs/adr/README.md` (one decision per ADR; no ADR for decisions local to a
  single spec). SPEC-054's relaxation reuses the existing approval mechanism and
  needs no ADR of its own; the provenance rule constrains agent-platform,
  tool-gateway, and SPEC-055's replay path, so it is recorded here.

## Consequences

- The fail-open path is closed by construction: a stale flow authority cannot
  be spent where no flow exists, and SPEC-054 R-2's relaxation no longer depends
  on a guard it removes.
- The card's declared kind (SPEC-054 R-1) and the authority that actually
  authorized execution share one vocabulary, so rendering and enforcement cannot
  silently disagree — the property the v0.34.1 headline-leak patch established
  within the kernel, now extended across the service boundary.
- SPEC-055 reads provenance instead of inferring it, for both trace capture and
  replay binding.
- ADR-0007 stays `accepted` and unedited; it is extended in scope by SPEC-054
  and labeled by this decision, not reversed.
- Trade-off: one more field on a security-critical contract, and both builders
  plus every verification point must agree on it. A `flow`-provenance envelope
  refused as stale surfaces as a **denied tool result rather than a re-parked
  card** — fail-closed, consistent with SPEC-051's step-budget-exhaustion
  posture, but a visible behavior change in the stale case: the operator sees a
  refusal and must re-initiate.
- Trade-off: `BROWSER_FLOW_AUTHORITY_STALE` joins the browser error vocabulary
  and needs the same portal rendering and audit treatment as the existing denial
  codes.
- follow-up: SPEC-054 R-2 implements stamping, gateway enforcement, and
  kernel-side clearing with per-criterion tests (ADR-0008); SPEC-055 must state
  which provenance its replay path emits (a graduated flow replaying under one
  gate emits `flow`) and which its authoring trace captures. No cross-product
  Python import is introduced by this decision.
