# SPEC-070 Tasks: Outbound User-Delegated Execution Identity (Tool-Gateway Substrate)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Provisional — do not implement.** SPEC-070 is `draft`; **OQ-1** (mechanism) and
> **OQ-2** (broker-minting / ADR-0015 scope) block `approved`, and **OQ-3** (what AAP
> accepts) is a Stage-0 live fact that constrains OQ-1. Stage 0 must complete — and
> ADR-0015 must be written — before any R-1..R-6 build task is concrete. No implementation,
> commit/push, deployment, or version bump is authorized by this `draft`.

## Stage 0 — decide the mechanism, then write ADR-0015 (gates everything)

- [ ] **OQ-3 (live fact):** determine what the first production target accepts for
      user-delegated auth — Red Hat AAP's MCP server uses "dual-layer auth inheriting user
      RBAC"; confirm whether it takes a federated user assertion, a token-exchanged token, or
      per-user AAP credentials. Record the evidence (mirrors SPEC-067 OQ-1 / SPEC-069 OQ-1).
- [ ] **OQ-1 (decision):** pick the delegation mechanism — (a) connector-local RFC 8693
      token exchange, (b) on-behalf-of, (c) per-user OAuth authorization-code, or
      (d) shared-IdP SSO/federation — constrained by the OQ-3 fact. Pin the scheme name +
      required fields (R-1) and the grant shape (R-2).
- [ ] **OQ-2 (decision):** determine whether the chosen mechanism requires the
      identity-broker to mint a new outbound-facing token (new audience/claim class →
      `identity-token.schema.json` change) or can stay connector-local reusing the inbound
      delegated token as `subject_token`.
- [ ] **Write ADR-0015** (`docs/adr/0015-<slug>.md`, status `proposed` → `accepted` per the
      ADR conventions): record the outbound user-delegated trust decision, the mechanism, the
      alternatives considered, and the no-elevation / no-downgrade consequences. Add it to
      `docs/adr/README.md`'s index.
- [ ] **OQ-4 (decision, only if OQ-1 = per-user OAuth):** decide where user-scoped refresh
      tokens live and how consent/rotation/revocation are handled — a new user-scoped store
      is its own reviewed capability, not an ad-hoc file.
- [ ] **OQ-5 (decision):** pin the self-contained dev-validation topology (mock IdP
      supporting the grant, vs a self-hosted Keycloak + AWX), tying to SPEC-069 OQ-5.
- [ ] Flip `spec.md` status `draft` → `approved`, pin the target version, and lift the
      `Provisional` banners on `plan.md`/`tasks.md` — **only after** OQ-1/OQ-2 resolve and
      ADR-0015 is accepted (separate operator authorization).

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
