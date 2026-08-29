# SPEC-044 Implementation Plan

## Approach

One vertical slice across four products plus a policy-bundle and an
audit-enum extension. Backend: skills-hub gains the read-only
validate route on its existing ingestion code path (R-2),
agent-platform gains the skill-draft generator and a bounded skills
validation client beside the SPEC-043 incident client (R-1/R-2), and
platform-gateway adds the pass-through route behind the new
`session:skill_draft` action (R-3/R-4). Portal: the chat view's
session actions gain Draft-as-skill with the SPEC-040 R-4 download
(R-5). Provenance and guardrails ride deterministic post-processing
(R-6). Nothing is persisted; the only durable additions are the
policy rule and the audit event. Version lockstep to 0.26.0.

## Workstreams

### W-1: Validation route on skills-hub (R-2)

- `products/skills-hub/src/skills_hub/api/routes/skills.py`: new
  `POST /api/v1/skills/validate` — request body is one candidate
  document (raw Markdown string, frontmatter included); response
  `{valid: bool, reason?: string}` using the ingestion report
  vocabulary. Calls the same validation functions
  `services/ingestion.py` uses during sync (single code path — the
  route must not re-implement any check); unit tests pin that the
  route and the CLI answer identically on a shared fixture set.
- Auth: the route joins the existing Basic query-credential registry
  (`SKILLS_QUERY_CLIENTS`) — no new auth mechanism; unauthorized
  callers answer the registry's existing structural errors.
- Read-only by construction: no store write, no sync trigger, no
  audit emission from the route itself (the caller owns its event).

### W-2: Skill-draft generator in agent-platform (R-1, R-6)

- New `products/agent-platform/src/agent_service/services/skill_draft.py`:
  digest-bundle assembly (reuse the shift-summary session-fact
  assembly; add the validated triage report leg through the existing
  SPEC-043 incident client when the session is incident-linked),
  prompt builder (`build_skill_draft_prompt` — digest bundle only,
  fenced `skill-frontmatter` contract, facts-only prohibition + the
  secrets/hostnames/customer-data rule), fenced-block parser
  (Pydantic-validated frontmatter within Skill Format caps),
  deterministic post-processing (cap enforcement, the gateway's
  redaction vocabulary applied to the body), the facts-only skeleton
  builder, and the provenance comment block.
- Prompt posture mirrors `document_prose.generate_prose`: one bounded
  model call on the session's model context, parse failure → skeleton,
  never a 500.
- Route: `POST /api/v2/sessions/{session_id}/skill-draft` in
  `api/v2/routes.py` — server-side ownership check (foreign ids →
  structural 404), calls the validation client (W-3), one bounded
  regeneration on validation rejection, response schema:
  `{markdown, mode: generated|skeleton, validation: passed,
  suggested_filename}`.
- Regression tests: prompt input bound (nothing outside the digest
  bundle reaches the builder), skeleton is format-valid, redaction
  post-processing, provenance block shape, ownership 404.

### W-3: Skills validation client in agent-platform (R-2)

- New `products/agent-platform/src/agent_service/services/skills_client.py`,
  modeled on `incident_client.py`: Basic-auth query credential,
  `httpx.AsyncClient` with bounded timeout, `x-request-id`
  forwarding, structured error mapping (not configured → 503,
  unreachable → 502 at the generation route, never an unvalidated
  draft).
- Settings: `AGENT_SKILLS_SERVICE_URL`, `AGENT_SKILLS_CLIENT_ID`,
  `AGENT_SKILLS_CLIENT_SECRET` in the frozen settings dataclass
  (empty default = not configured).
- dev-k8s wiring: register the agent-platform credential in the
  skills-hub query-auth registry Secret (`sync-skills-secrets.sh`
  conventions) and expose the URL knob in the agent-platform
  runtime-config ConfigMap.

### W-4: Policy gate, gateway route, audit (R-3, R-4)

- `shared/shared-contracts/policies/policy-default.yaml`: one new
  rule `allow-operators-skill-draft` — roles `platform-admin`,
  `approver`, `operator`; action `session:skill_draft`; the
  documents-create grant comment pattern. `make validate-policy` +
  `make sync-policy` to both gateway copies.
- `products/platform-gateway/src/platform_gateway/api/routes/sessions.py`:
  `POST /api/v1/sessions/{session_id}/skill-draft` —
  `enforce_policy` gate on `session:skill_draft`, delegated-identity
  forwarding, structured error mapping (403/404/502/503), verbatim
  response pass-through, no held state.
- Audit: `skill_draft_generated` joins the audit-service event enum
  (`schemas/audit.py`) with the SPEC-029 parity-guard members
  updated; agent-platform emits on the canonical fire-and-forget
  emitter with requester, session id, incident id (when present),
  mode, validation outcome, and forwarded `x-request-id`.

### W-5: Portal session action and download (R-5)

- `products/operator-portal/web-ui/app/src/chat/ChatView.tsx` (session
  actions cluster beside rename / session-id copy): **Draft as
  skill** action, client-side visibility from the caller's role matrix
  (server re-enforces), busy state during generation, error toasts for
  the structured 403/502/503 shapes.
- Download via the SPEC-040 R-4 Blob pattern
  (`text/markdown;charset=utf-8`, `<suggested-slug>.md`); the toast
  distinguishes `generated` from the facts-only `skeleton` mode.
- Vitest coverage: action visibility per role, busy/error paths, the
  download filename; the zero-deprecation guard stays green.

### W-6: Verification, docs, release (house train)

- `make verify` (tests + overlays + policy + version lockstep
  0.25.2 → 0.26.0), `make build`, `make deploy`; browser live check
  of the flow on a triaged session (draft download, skeleton path via
  an untriaged/quiet session, observer denial); e2e extension if the
  demo scripts can seed a deterministic draft (adjudicate during
  delivery — the LLM leg may stay browser-verified only, as prose
  generation does).
- Living-state docs per spec.md Impact; release note + CHANGELOG
  0.26.0.

## Sequencing

W-1 and W-3 are independent; W-2 needs both for its validation leg;
W-4 lands with W-2 (route + gate + audit together); W-5 after the
gateway route; W-6 last. The whole slice is additive — no existing
route, contract, or posture changes shape.

## Risks

- **Draft quality on quiet sessions** — the skeleton fallback keeps
  the surface honest; the live check deliberately includes a quiet
  session.
- **Validation round-trip latency** adds one bounded internal call to
  generation; the timeout knob matches the incident client's posture.
- **Policy bundle churn** is one rule; the sync/validate gate catches
  drift before commit.
