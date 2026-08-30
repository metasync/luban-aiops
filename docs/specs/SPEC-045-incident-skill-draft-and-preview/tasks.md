# SPEC-045 Tasks

## R-1: Incident-anchored generation in agent-platform (W-1)

- [x] `skill_draft.py` extended (not forked):
      `build_incident_skill_draft_bundle` through the existing
      SPEC-043 incident client; envelope with `triage_raw`
      stripped; validated triage report required (typed
      `NoValidatedTriageReport`); dispatches excluded; prompt-purity
      regression test asserts nothing outside the bundle reaches
      the builder
- [x] Skeleton builder extension: facts-only skeleton from the
      incident envelope + triage-report facts (always format-valid);
      provenance block carries incident id (no session id), date,
      platform version, mode; slug from the incident title
- [x] Route `POST /api/v2/incidents/{incident_id}/skill-draft` in
      `api/v2/routes.py`: incident-client error mapping (503 not
      configured, 502 transport, 404 unknown id), deterministic 409
      triage gate, the SPEC-044 generate → validate → bounded
      regeneration → skeleton sequence reused; response
      `{markdown, mode, validation, suggested_filename}`; nothing
      persisted; the session route untouched
- [x] Degradation tests: parse failure → skeleton; second validation
      failure → skeleton; skeleton validates; generation never 500s;
      409 per missing-triage status (`new`/`triaging`/`triage_failed`)

## R-2: Gateway pass-through and error mapping (W-2)

- [x] `POST /api/v1/incidents/{incident_id}/skill-draft` in
      `api/routes/incidents.py`: dual gate (`incident:skill_draft`
      then `incident:read`, denial reports the first failing
      action), delegated-identity + `x-request-id` forwarding,
      verbatim response pass-through, no held state
- [x] `agent_client.create_incident_skill_draft` + gateway service
      proxy with the house mapping: 4xx passthrough incl. the 409,
      502/503 verbatim, other 5xx/transport → 502; 60 s leg timeout
- [x] Gateway tests: dual-gate denial order, upstream error mapping
      incl. 409, pass-through fidelity, policy-matrix and
      route-inventory updates

## R-3: Policy gate and audit (W-2)

- [x] `policy-default.yaml`: rule
      `allow-operators-incident-skill-draft`
      (`incident:skill_draft` → platform-admin/approver/operator,
      session-skill-draft grant comment pattern);
      `make validate-policy` + `make sync-policy` to both gateway
      copies and the dev-k8s ConfigMap
- [x] audit-service: `incident_skill_draft_generated` in the event
      enum (`schemas/audit.py`) + shared `audit-event.schema.json`
      with the SPEC-029 parity-guard members updated
- [x] agent-platform: emit `incident_skill_draft_generated` on the
      canonical emitter (requester, incident id, mode, validation
      outcome, forwarded `x-request-id`); blocked requests ride the
      gateway's blocked-attempt audit

## R-4: Portal incident-detail action (W-3)

- [x] `api/incidents.ts`: `createIncidentSkillDraft()` on the shared
      `SkillDraftResponse` shape; `roles.ts`
      `INCIDENT_SKILL_DRAFT_ROLES` mirroring the grant
- [x] `IncidentsView.tsx` detail toolbar: **Draft as skill** beside
      Run/Re-run triage and Continue in chat; role-matrix
      visibility (server re-enforces); busy state; structured
      toasts 403/404/409 ("run triage first")/502/503; success opens
      the preview
- [x] Vitest: visibility per role, busy state, the five error
      toasts, preview-open on success

## R-5: Shared skill-draft preview (W-4)

- [x] `SkillDraftPreview` modal: bounded scrollable rendered
      markdown (escape-first renderer) + raw-markdown toggle (raw
      shows the provenance HTML comment), mode badge, validation
      status, suggested filename; read-only — no editing affordance
- [x] **Download .md** primary (SPEC-040 R-4 Blob download, raw
      markdown, filename from the response) and **Discard**
      secondary (close, drop the in-memory response); nothing
      persisted on either path
- [x] Rewire `DraftAsSkillButton` (chat header) through the preview;
      existing error toasts kept; the generated/skeleton toast
      becomes the modal badge
- [x] Vitest: rendered/raw toggle, mode badge, download filename +
      Blob call, discard without download, modal bounds;
      zero-deprecation guard green

## R-6: Session surface unchanged (verification)

- [x] The v0.26.0 session-scoped suite passes untouched (route,
      policy action, audit event, chat button); no backend movement
      on the session surface

## House train (W-5)

- [x] Version lockstep 0.26.0 → 0.27.0; `make verify` green before
      **and** after `make build`; `make deploy`
- [x] Browser live check: incident-entry draft + preview + download
      on a triaged incident by a user who does not own the triage
      session; 409 on an untriaged incident; observer denial (hidden
      button + API 403); preview discard; session entry still works
      through the preview
- [x] Living-state docs: `skills-guide.md`, `portal-user-guide.md`,
      `incident-guide.md`, `authorization-matrix.md`
      (`configuration-reference.md` gains no new knobs)
- [x] CHANGELOG 0.27.0 + release note + index; commit/tag/push per
      the house train
