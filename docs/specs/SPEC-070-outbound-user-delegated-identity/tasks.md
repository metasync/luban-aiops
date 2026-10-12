# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved — implementation authorized (2026-10-12).** SPEC-070 is `approved`: **OQ-1**
> resolved to **(c) per-user OAuth 2.x authorization-code, connector-local**, **OQ-2** to
> **no identity-broker mint**, and **OQ-3** answered by research (Red Hat AAP's MCP server
> takes per-user OAuth auth-code / PATs and inherits user RBAC). ADR-0015 is **accepted**
> and indexed. Stage 0 is therefore **complete**; the R-1..R-6 build tasks below are
> concrete against the pinned mechanism. Commit/push, deployment, and any version bump
> remain **separate** authorization boundaries **not** granted by approval.

## Stage 0 — decide the mechanism, then write ADR-0015 (COMPLETE 2026-10-12)

- [x] **OQ-3 (live fact) — RESOLVED:** Red Hat AAP's MCP server takes **per-user OAuth 2.x
      authorization-code / PATs** against AAP Gateway's own authorization server and
      **inherits the requesting user's RBAC**; 2.6 has **no OIDC discovery** and documents
      authorization-code + password grants — **not** token-exchange or OBO. Evidence recorded
      in ADR-0015 (researched 2026-10-12).
- [x] **OQ-1 (decision) — RESOLVED to (c) per-user OAuth authorization-code** (operator,
      2026-10-12), constrained by the OQ-3 fact. Scheme provisionally named
      `oauth2_authorization_code`; R-1 fields and the R-2 grant shape are pinned in
      `spec.md`/`plan.md`. (a)/(b) rejected, (d) deferred — see ADR-0015.
- [x] **OQ-2 (decision) — RESOLVED to no identity-broker mint.** The mechanism stays
      **connector-local**; the target issues the user-bound token. `identity-token.schema.json`
      is **unchanged**; the broker's inbound `sub` is only read to look up the user's refresh
      token. See ADR-0015.
- [x] **Write ADR-0015** — done:
      `docs/adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md`, status
      **`accepted`** (2026-10-12), recording the trust decision, mechanism, alternatives, and
      the no-elevation / no-downgrade consequences; indexed in `docs/adr/README.md`.
- [x] **OQ-4 (decision) — IN SCOPE (OQ-1 = c forces it):** a **new user-scoped credential
      store** holds per-user refresh tokens — encrypted at rest, in-memory on use, rotatable,
      revocable, redaction-covered (ADR-0015). The direction is decided; the concrete backend
      + consent/rotation/revocation flow is an R-6 implementation task, its own reviewed
      capability (not an ad-hoc file).
- [x] **OQ-5 (decision) — RESOLVED in direction:** with authorization-code (not token
      exchange), dev validation uses a mock OAuth authorization server — a **self-hosted
      Keycloak** fronting **AWX** as the in-cluster stand-in (ties to SPEC-069 OQ-5); unit /
      integration tests use `httpx.MockTransport`. The concrete harness is pinned in the R-2
      test tasks.
- [x] Flip `spec.md` status `draft` → **`approved`**, target version pinned to **v0.49.0**,
      and the `Provisional` banners on `plan.md`/`tasks.md` lifted — done 2026-10-12 after
      OQ-1/OQ-2/OQ-3 resolved and ADR-0015 was accepted (operator authorization).

## R-1: User-delegated outbound credential scheme (additive over SPEC-068)

- [ ] Add the user-delegated scheme (name + required fields per Stage 0) to
      `_SCHEME_REQUIRED_FIELDS` in
      `products/tool-gateway/src/tool_gateway/tools/credential_sets.py`, retaining its fields
      in `_parse_set` exactly as SPEC-068 generalized the parser.
- [ ] Fail closed on an unknown scheme or a set missing its required fields
      (`LOGGER.warning`, never admitted half-formed); leave the mtime-refresh +
      keep-last-good-on-unreadable logic unchanged.
- [ ] Tests: a `basic`/`bearer`/`oauth2_client_credentials` set (and one with no `scheme`)
      parses byte-identically to post-SPEC-068 (regression on the `acme-admin` sample set);
      the user-delegated scheme requires its Stage-0 fields; unknown/incomplete sets are
      ignored with a warning (`products/tool-gateway/tests/`).

## R-2: User-subject threading + the user-delegated grant

- [ ] Extend `products/tool-gateway/src/tool_gateway/tools/auth_resolution.py` to thread the
      requesting user's subject (from the inbound ADR-0004 delegated token) into outbound
      resolution for a user-delegated set.
- [ ] Implement the Stage-0 grant in `tools/oauth_client.py` (extended) or a new
      `tools/user_delegated_client.py`: obtain a **target-issued, user-bound** token; cache in
      memory keyed by (set name, user subject) with near-expiry refresh + single-flight,
      mirroring `oauth_client`'s `_CachedToken`/lock discipline and **never** shared across
      users.
- [ ] Enforce no-elevation: the outbound token carries at most the user's target-side
      authority; the platform does not translate or synthesize roles (mirror
      `exchange_service.exchange_token`'s verbatim-roles invariant).
- [ ] Fail closed with a structured gateway error when the user subject cannot be resolved —
      never substitute a service/machine credential (see R-5).
- [ ] Tests: cache miss → user-bound fetch → cache hit; per-(set,user) keying with no
      cross-user reuse; near-expiry refresh; single-flight under concurrency; unresolved
      subject fails closed; no token in logs/results/evidence (`products/tool-gateway/tests/`).

## R-3: Trust-boundary / federation contract

- [ ] Make the trust prerequisite (federated issuer the target trusts / per-user consent /
      shared IdP, per Stage 0) **explicit per-set config**, never auto-negotiated.
- [ ] Fail closed with a structured gateway error on a missing/broken federation; never assert
      a user identity to a target not configured to trust it.
- [ ] *(Only if OQ-2 = broker-minted)* add the new outbound exchange audience/path in
      `products/identity-broker` and the matching `identity-token.schema.json` claim class.
- [ ] Tests: a configured-trust path succeeds; a missing/broken federation fails closed; the
      platform never emits a user assertion to an untrusted target
      (`products/tool-gateway/tests/`, plus `products/identity-broker/tests/` iff OQ-2).

## R-4: End-to-end attribution fidelity

- [ ] Record the human subject **and** the delegation mode (user-delegated vs SPEC-068
      service-account) on the outbound tool-call audit trail, so a target-side action is
      attributable end to end (identity Principles 2/3/5; ADR-0004 `sub`/`act`).
- [ ] Confirm no token/secret/credential value surfaces in audit, evidence, a tool result, or
      a log line (reuse SPEC-068 R-4 + SPEC-009 R-1 redaction); add no new HITL surface and
      change no risk tier.
- [ ] Tests: a user-delegated call's audit links the platform subject to the target identity
      and is distinguishable from a service-account call; no secret in the trail
      (`products/tool-gateway/tests/`).

## R-5: Secret-handling, fail-closed, no-fabrication, **no-downgrade**

- [ ] Assert the existing redaction vocabulary covers a user-delegated token: drive it through
      a URL projection, a tool result, an evidence field, and audit; confirm masking
      (`url_redaction.SECRET_QUERY_PARAMS` + `redaction._VALUE_PATTERNS` already cover
      `token`/`secret`/`authorization`).
- [ ] Confirm `make validate-secret-vocabulary` stays green **without** a new canonical field
      set (it pins redaction vocabularies, not credential field names).
- [ ] Confirm `_PROJECTED_HEADERS` still omits `authorization`/`set-cookie`; hold the token in
      memory only (never disk/result/evidence/audit/log).
- [ ] **No-downgrade (governance crux):** assert there is **no** code path that retries a
      failed user-delegated acquisition with `oauth2_client_credentials`/`bearer`/`basic` — a
      silent service-account fallback would violate the OQ-4 directive, so its absence is a
      first-class tested invariant (`products/tool-gateway/tests/`).

## R-6: Provisioning + (OQ-dependent) per-user storage

- [ ] Document the extended `credential-sets.json` shape and confirm an operator supplies the
      user-delegated target/client config through the existing `sync-browser-credentials.sh`
      `BROWSER_CREDENTIAL_SETS_FILE` override — no new platform-config secret, never inline
      env, never committed (`shared/platform-ops/gitops/sync-browser-credentials.sh`).
- [ ] Render the dev-k8s overlay green (`make overlays`); leave the extension inert until a
      user-delegated set is provisioned (`shared/platform-ops/gitops/dev-k8s/`).
- [ ] *(Only if OQ-1 = per-user OAuth, per OQ-4)* implement the user-scoped credential store
      with consent/rotation/revocation as its own reviewed capability — not an ad-hoc file.

## Delivery Gate

- [ ] All acceptance criteria in `spec.md` verified; `make verify` green (incl.
      `validate-secret-vocabulary` asserted unchanged, `overlays`, `portal-test`).
- [ ] A SPEC-068-scheme regression proves `basic`/`bearer`/`oauth2_client_credentials`
      resolution is byte-identical; the **no-downgrade** test passes.
- [ ] ADR-0015 accepted and indexed in `docs/adr/README.md`.
- [ ] Living state docs updated (see spec `Impact`):
      `docs/agentic-aiops-platform/identity-and-authorization-design.md` §Service Identity
      Model / §External Execution Identity, `products/tool-gateway/README.md`,
      `docs/guides/architecture-overview.md`, and the delivery-roadmap (substrate delivered;
      SPEC-069's production path now depends on it).
- [ ] `CHANGELOG.md` entry referencing SPEC-070; `VERSION` bumped in lockstep (separate
      authorization). Spec index in `docs/specs/README.md` updated; status set to `delivered`.

> **Forward path.** SPEC-070 is the production-identity dependency SPEC-069 R-1 names; the
> Layer-2 runbook-typed-tools fast-follow (number assigned at its own drafting) also relies
> on it for user-delegated action attribution. SPEC-069's read-only **dev** slice does not
> block on SPEC-070 — it validates against a self-hosted server's own auth.
