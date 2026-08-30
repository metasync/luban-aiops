# SPEC-045 Implementation Plan

## Approach

One vertical slice across three products plus a policy-bundle and an
audit-enum extension — no new services, no new clients, no new knobs.
Backend: agent-platform gains the incident-anchored generator and
route by reusing the SPEC-044 generator internals and the SPEC-043
incident client (R-1); platform-gateway adds the pass-through on its
incidents router behind the dual `incident:skill_draft` +
`incident:read` gate (R-2/R-3). Portal: the incident detail toolbar
gains Draft-as-skill (R-4) and both entry points route through one
new shared preview modal (R-5). The session surface is untouched
(R-6). Nothing is persisted; the only durable additions are the
policy rule and the audit event. Version lockstep to 0.27.0.

## Workstreams

### W-1: Incident-anchored generator and route in agent-platform (R-1)

- `products/agent-platform/src/agent_service/services/skill_draft.py`:
  extend, do not fork. New bundle assembler
  `build_incident_skill_draft_bundle(settings, request_id,
  incident_id)` calling the existing `incident_client
  .fetch_incident_bundle`; strips `triage_raw` from the envelope;
  requires a validated triage report (raises a typed
  `NoValidatedTriageReport` when absent); excludes dispatches.
  `build_skill_draft_prompt` gains an optional incident-anchored
  bundle shape — the fenced contract, prohibitions, and digest-only
  signature posture stay identical; prompt-purity regression test
  asserts nothing outside the bundle reaches the builder.
- Skeleton builder extension: facts-only skeleton from the incident
  envelope + triage-report facts (deterministic, always
  format-valid); provenance block carries incident id (no session
  id), date, platform version, mode; slug from the incident title.
- Route `POST /api/v2/incidents/{incident_id}/skill-draft` in
  `api/v2/routes.py`: incident client error mapping (503 not
  configured, 502 transport, 404 unknown id), the 409 triage gate,
  then the exact SPEC-044 generate → validate → bounded-regenerate
  → skeleton sequence (shared helpers; the session route must keep
  passing untouched). Emit `incident_skill_draft_generated` on the
  canonical fire-and-forget emitter.
- Tests: bundle purity (no `triage_raw`, no dispatches), 409 gate
  per missing-triage status (`new`/`triaging`/`triage_failed`),
  skeleton format-validity, provenance shape, generation-failure
  degradation, client error mapping — mirroring the SPEC-044 test
  classes.

### W-2: Gateway pass-through, policy, audit (R-2, R-3)

- `shared/shared-contracts/policies/policy-default.yaml`: rule
  `allow-operators-incident-skill-draft`
  (`incident:skill_draft` → platform-admin/approver/operator),
  session-skill-draft grant comment pattern; `make validate-policy`
  + `make sync-policy` to both gateway copies and the dev-k8s
  policy ConfigMap.
- audit-service `schemas/audit.py`: `incident_skill_draft_generated`
  in the `EventType` Literal with the SPEC-029 parity-guard members;
  shared `audit-event.schema.json` enum + details description.
- platform-gateway: `ACTION_INCIDENT_SKILL_DRAFT` +
  `PROTECTED_ACTIONS` in `policy_engine.py`; dual gate in the route
  (denial reports the first failing action);
  `create_incident_skill_draft` in `gateway_service.py` +
  `agent_client.py` (60 s leg timeout, same mapping: 4xx passthrough
  with `_upstream_detail` incl. the 409, 502/503 verbatim, other
  5xx/transport → 502); route
  `POST /api/v1/incidents/{incident_id}/skill-draft` in
  `api/routes/incidents.py` with delegated identity, `x-request-id`,
  and the `incident_skill_draft_generated` log event.
- Tests: dual-gate denial order (missing first action reported),
  upstream error mapping incl. 409 passthrough, pass-through
  fidelity, policy-matrix and route-inventory updates, audit enum
  parity guard.

### W-3: Portal incident-detail action (R-4)

- `web-ui/app/src/api/incidents.ts`: `createIncidentSkillDraft()`
  returning the shared `SkillDraftResponse` shape (hoist the
  interface to a shared api type or re-export).
- `web-ui/app/src/roles.ts`: `INCIDENT_SKILL_DRAFT_ROLES`
  (platform-admin/approver/operator) mirroring the grant.
- `IncidentsView.tsx` detail toolbar: **Draft as skill** beside
  Run/Re-run triage and Continue in chat, visibility per role,
  busy state, structured toasts (403 role / 404 unknown / 409 "run
  triage first" / 502+503 dependency), success opens the preview
  (W-4).
- Vitest: visibility per role, busy state, the five error toasts
  incl. the 409 wording, preview-open on success.

### W-4: Shared skill-draft preview (R-5)

- New `web-ui/app/src/chat/SkillDraftPreview.tsx` (or
  `components/`): bounded scrollable modal — rendered-markdown view
  through the existing escape-first renderer with a raw-markdown
  toggle (raw shows the provenance HTML comment), mode badge
  (*generated* / *facts-only skeleton*), validation status,
  suggested filename; **Download .md** primary (SPEC-040 R-4 Blob
  download of the raw markdown, filename from the response) and
  **Discard** secondary (close, drop the in-memory response).
  Read-only — no editing affordance.
- Rewire `DraftAsSkillButton` (ChatView) to open the preview on
  success instead of downloading blindly; the generated/skeleton
  toast moves into the modal's badge. Keep the error toasts.
- Vitest: rendered/raw toggle (provenance visible only in raw),
  mode badge, download filename + Blob call, discard closes without
  download, modal bounds; zero-deprecation guard green.

### W-5: House train (R-6 verification + release)

- Session surface regression: the v0.26.0 session tests pass
  untouched (the split changed nothing there).
- Version lockstep 0.26.0 → 0.27.0 (VERSION, 8× pyproject.toml,
  8× metadata.py, 2× `__init__.py`, 8× uv.lock); `make verify`
  before **and** after `make build`; `make deploy`.
- Browser live check on the canonical aiops.luban.metasync.cc:
  incident-entry draft with preview + download on a triaged
  incident (by a user who does **not** own the triage session —
  the motivating case), the 409 path on an untriaged incident,
  observer denial (button hidden + API 403), preview discard, and
  the session entry still working through the preview.
- Living-state docs per spec.md Impact; CHANGELOG 0.27.0 + release
  note + index; commit → scan gate → tag v0.27.0 → push (never
  combined).

## Sequencing

1. **W-1** first — the generator/route and its tests pin the
   bundle purity and the 409 gate before anything consumes them.
2. **W-2** in parallel with or right after W-1 — policy/audit and
   the gateway pass-through; agent-platform emits the event.
3. **W-4 before W-3** — build the shared preview, rewire the
   session button through it (keeping every existing test green),
   then add the incident action on top of the proven component.
4. **W-5** last, per the house train.

## Risks

- **Preview rewires a shipped flow.** The session button's behavior
  changes (download → preview). Mitigation: W-4 keeps the response
  contract and error toasts identical, migrates the existing tests
  rather than deleting them, and the live check re-verifies the
  session path end-to-end.
- **Two-step vs one-step UX.** Preview adds a click. Adjudicated:
  the mode badge and discard affordance are worth it; operators can
  still one-click Download from the modal.
- **409 wording.** "Run triage first" must not read like a platform
  failure — the toast and the guide name it as a precondition, not
  an error.
- **Dual-gate denial order.** The route evaluates
  `incident:skill_draft` first, then `incident:read`; tests pin the
  first-failing-action reporting so matrix drift is caught.
- **Edit-then-revalidate pressure.** Operators may immediately want
  to tweak title/tags in the preview. The parked trigger (Q-7) is
  the answer; the preview stays read-only this slice.
- **Bundle scope creep.** Dispatches stay excluded (Q-3); a test
  asserts their absence from the prompt so a future hand cannot
  quietly widen the input.
