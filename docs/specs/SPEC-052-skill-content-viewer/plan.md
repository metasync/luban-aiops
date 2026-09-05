# SPEC-052 Plan: Skill Content Viewer

## Approach

Three thin, additive layers, no new service and no contract change:

1. **Gateway pass-through (R-1)** — mirror the existing skills *list* proxy with
   a *detail* proxy. skills-hub's `GET /api/v1/skills/{skill_id:path}` already
   returns the full record (including `body`) and already emits `skill_retrieved`,
   so the gateway only needs a sibling client function and route gated by the same
   `skills:read` action and the same gateway-held Basic credential.
2. **Portal fetch + affordance (R-2)** — a View action per Skills-table row that
   lazily fetches the detail through the new proxy, reusing the existing
   `requestJson` client and the SkillsView error pattern.
3. **Portal viewer (R-3)** — a read-only rendered/raw modal that reuses the
   escape-first `renderMarkdown` and the `Segmented` toggle pattern proven by
   `SkillDraftPreviewModal`, adapted to ingested-skill metadata.

The work is deliberately ordered gateway-first so the portal has a real endpoint
to fetch, but the two are independently testable (the portal test mocks the
client; the gateway test mocks skills-hub).

## Design Per Requirement

### R-1: Single-skill detail proxy (platform-gateway)

- affected files:
  - `products/platform-gateway/src/platform_gateway/services/skills_hub_client.py`
    — add `async def get_skill(settings, request_id, skill_id) -> dict`, reusing
    `_base_url` (503 when unconfigured), `_credential` (gateway Basic),
    `_raise_upstream` (4xx passthrough, 5xx→502), and the `httpx.HTTPError`→502
    "skills hub unavailable" guard, exactly as `list_skills` does. The URL is
    `f"{_base_url(settings)}/api/v1/skills/{skill_id}"`; `skill_id` is the
    namespaced `<source_id>/<slug>` form whose charset (`[a-z0-9-/]`) is already
    URL-safe, so slashes are preserved literally for skills-hub's `{skill_id:path}`
    matcher (no percent-encoding of the separators).
  - `products/platform-gateway/src/platform_gateway/api/routes/skills.py` — add
    `@router.get("/api/v1/skills/{skill_id:path}")` **after** the list route,
    resolving the request id, calling `resolve_request_identity`, enforcing
    `ACTION_SKILLS_READ`, delegating to `get_skill`, and logging
    `skill_detail_proxied` (request_id, user_id, skill_id). Route order keeps the
    exact `/api/v1/skills` list match distinct from the greedy path match.
- chosen approach: a sibling of the list proxy — same action, same credential,
  same error posture — because the contract already scopes `body` to full-record
  responses, so a detail hop is the intended path and needs no new gate.
- alternatives rejected: (a) fattening the *list* payload to include `body` —
  rejected, it contradicts `skill.schema.json` ("list and search responses omit or
  excerpt it"), bloats every inventory read, and changes a delivered contract
  surface; (b) calling skills-hub directly from the portal — rejected, it would
  bypass the gateway policy edge and leak the gateway credential.

### R-2: Portal View action with lazy detail fetch

- affected files: `products/operator-portal/web-ui/app/src/views/control/SkillsView.tsx`.
- chosen approach: add a trailing "actions" column with a small `Button`
  (`aria-label="View <title|skill_id>"`). `openSkill(id)` sets a per-id loading
  flag, awaits `requestJson<SkillDetail>('/api/v1/skills/' + id.split('/').map(encodeURIComponent).join('/'))`,
  and on success sets the viewer state; on failure it surfaces the message through
  the existing inline `Alert` and does not open the modal. Nothing is fetched until
  View is invoked. A `SkillDetail` interface (skill_id, title?, source_id?, tags?,
  version?, updated_at?, web_target?, body?) is declared locally, mirroring the
  existing inline `SkillRecord`/`SkillsPayload` style.
- alternatives rejected: eager-fetching every row's body on list load — rejected,
  it multiplies upstream calls and defeats the contract's list/detail split.

### R-3: Read-only rendered/raw skill content viewer

- affected files: new
  `products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx` (beside
  `SkillDraftPreview.tsx`), importing `renderMarkdown` from `./markdown`; a
  `SkillContentViewer.test.tsx` alongside.
- chosen approach: a `Modal` (`open={skill !== null}`) with the metadata header
  (title, `source_id`, `version`, `tags`, and `web_target` when present) and a
  `Segmented` Rendered/Raw toggle defaulting to Rendered, over a bounded
  (`max-height`, scroll) pane reusing `md-content` (rendered) / `evidence-pre`
  (raw). The rendered branch uses `dangerouslySetInnerHTML` with
  `renderMarkdown(body)` — the same escape-first, http(s)-only renderer, so no new
  HTML path is introduced. Footer is a single **Close**; there is no
  download/discard and nothing is persisted. The skill `body` is already
  frontmatter-stripped by skills-hub, so no fence stripping is needed (the shared
  strip is harmless if applied).
- alternatives rejected: reusing `SkillDraftPreviewModal` directly — rejected, its
  props (`mode`, `validation`, `suggested_filename`, Download .md) are
  draft-export semantics that do not apply to an ingested skill and would muddy the
  SPEC-044/045 authoring flow; a sibling component keeps both surfaces honest while
  sharing the renderer and visual grammar.

## Sequencing And Dependencies

1. Gateway `get_skill` client + detail route (R-1) — depends on nothing
   (skills-hub endpoint already exists).
2. Gateway tests: route inventory + workspace-proxy detail cases (R-1) — depends
   on stage 1.
3. Portal `SkillContentViewer` modal + test (R-3) — depends on nothing (pure
   component over a `SkillDetail` shape).
4. Portal `SkillsView` View action + lazy fetch + test (R-2) — depends on stage 3.
5. Living-state docs + CHANGELOG on delivery — depends on stages 1–4.

## Test Strategy

- unit tests (gateway, `pytest`):
  - `test_route_inventory.py` — assert `("GET", "/api/v1/skills/{skill_id:path}")`
    is registered.
  - `test_workspace_proxies.py` — detail proxy: `skills:read` holder gets the
    upstream full record; a role without `skills:read` is denied at the edge before
    any upstream call; the upstream request carries the gateway Basic credential
    (not the user token); unknown id → 404 passthrough; unconfigured → 503;
    transport/5xx → 502.
- unit tests (portal, `vitest`):
  - `SkillContentViewer.test.tsx` — opens on Rendered; `Segmented` switches to Raw
    showing the body text; header shows title/source/version/tags (+ `web_target`);
    a `<script>`/`<img onerror>` in the body is escaped (not executed) in the
    rendered view; Close dismisses; no download/discard controls.
  - `SkillsView.test.tsx` — a View control per row; clicking issues exactly one
    detail request (rows not opened issue none); loading state; error surfaces
    inline without opening the modal; the list rendering is otherwise unchanged.
- contract tests: none new — `skill.schema.json` is unchanged and skills-hub is
  untouched; the detail response already conforms.
- integration / overlay validation: no GitOps or config change (reuses
  `skills:read` and the existing skills-hub credential); `make verify` must stay
  green (route-inventory and policy-matrix guards included).

## Rollout And Migration

- deployment/configuration changes: none. No new env var, secret, policy action, or
  audit event type; the gateway already holds the skills-hub query credential and
  the `skills:read` grant is unchanged.
- backward compatibility: purely additive — a new gateway route and a new portal
  affordance; the skills list payload, its filters, and every existing route are
  unchanged. Portals served against a gateway without the new route would simply see
  the detail fetch 404, but both ship together in one image set.
- rollback: revert the two commits (gateway route/client, portal view/modal); no
  data migration or state to unwind.
