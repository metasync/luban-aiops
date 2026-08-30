# SPEC-044 Tasks

## R-2: Validation leg on skills-hub's own code path (W-1, W-3)

- [x] skills-hub: `POST /api/v1/skills/validate` in
      `api/routes/skills.py` calling the ingestion validation
      functions verbatim (no re-implementation); behind the Basic
      query-credential registry; read-only (no store/sync/audit
      side effects)
- [x] Fixture-parity test: route and `python -m skills_hub.validate`
      answer identically on a shared valid/invalid fixture set
- [x] agent-platform: new `skills_client.py` (Basic query credential,
      bounded timeout, `x-request-id` forwarding, structured error
      mapping) + the three `AGENT_SKILLS_*` settings knobs
      (empty default = not configured → 503 at the generation route)
- [x] dev-k8s wiring: agent-platform credential in the skills-hub
      query-auth registry Secret (`sync-skills-secrets.sh`
      conventions) + URL knob in the agent-platform runtime-config
      ConfigMap; `docs/guides/configuration-reference.md` rows

## R-1: Skill-draft generation in agent-platform (W-2)

- [x] New `services/skill_draft.py`: digest-bundle assembly (reuse
      the shift-summary session-fact assembly; validated triage
      report leg through the SPEC-043 incident client when the
      session is incident-linked)
- [x] `build_skill_draft_prompt`: digest bundle only; fenced
      `skill-frontmatter` contract; facts-only + no
      secrets/hostnames/customer-data prohibitions; regression test
      asserts nothing outside the digest bundle reaches the builder
- [x] Fenced-block parser (Pydantic frontmatter within Skill Format
      caps), deterministic post-processing (cap enforcement, redaction
      vocabulary), facts-only skeleton builder (always format-valid),
      provenance comment block
- [x] Route `POST /api/v2/sessions/{session_id}/skill-draft` in
      `api/v2/routes.py`: server-side ownership check (foreign →
      structural 404), validation via W-3 client, one bounded
      regeneration with the rejection reason, response
      `{markdown, mode, validation, suggested_filename}`; validation
      unavailable → 503/502, never an unvalidated draft
- [x] Degradation tests: parse failure → skeleton; second validation
      failure → skeleton; skeleton validates; generation never 500s

## R-3: Policy gate and audit (W-4)

- [x] `policy-default.yaml`: rule `allow-operators-skill-draft`
      (`platform-admin`/`approver`/`operator`, action
      `session:skill_draft`, documents-create grant comment pattern);
      `make validate-policy` + `make sync-policy` to both gateway
      copies
- [x] audit-service: `skill_draft_generated` in the event enum
      (`schemas/audit.py`) with the SPEC-029 parity-guard members
      updated
- [x] agent-platform: emit `skill_draft_generated` on the canonical
      emitter (requester, session id, incident id when present, mode,
      validation outcome, forwarded `x-request-id`); blocked requests
      ride the gateway's blocked-attempt audit

## R-4: Gateway pass-through (W-4)

- [x] `POST /api/v1/sessions/{session_id}/skill-draft` in
      `api/routes/sessions.py`: `enforce_policy` gate on
      `session:skill_draft`, delegated-identity + `x-request-id`
      forwarding, structured error mapping (403/404/502/503),
      verbatim response pass-through, no held state
- [x] Gateway tests: action denial 403, upstream error mapping,
      pass-through fidelity

## R-5: Portal session action and download (W-5)

- [x] ChatView session actions: **Draft as skill** beside
      rename/session-id-copy, role-matrix visibility (server
      re-enforces), busy state, structured-error toasts
- [x] Download via the SPEC-040 R-4 Blob pattern
      (`<suggested-slug>.md`); toast distinguishes `generated` vs
      `skeleton`
- [x] Vitest: visibility per role, busy/error paths, download
      filename; zero-deprecation guard green

## R-6: Provenance marker and content guardrails (folded into W-2)

- [x] Provenance block assertions (session id, incident id when
      present, date, platform version, mode); strip-safe (HTML
      comment, body content)
- [x] Redaction post-processing test on a seeded model output;
      prompt-carries-the-prohibition regression test

## House train (W-6)

- [x] Version lockstep 0.25.2 → 0.26.0; `make verify` green
- [x] `make build` + `make deploy`; browser live check: draft
      download on a triaged session, skeleton path on a quiet session,
      observer denial
- [x] Living-state docs: `docs/guides/skills-guide.md`
      (authoring-from-sessions section), `portal-user-guide.md`,
      `authorization-matrix.md`, `configuration-reference.md`
- [x] CHANGELOG 0.26.0 + release note + index; commit/tag/push per
      the house train
