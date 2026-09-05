# SPEC-052 Tasks: Skill Content Viewer

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Single-skill detail proxy (platform-gateway)

- [x] add `get_skill(settings, request_id, skill_id)` to `services/skills_hub_client.py`, reusing `_base_url` / `_credential` / `_raise_upstream` and the `httpx.HTTPError`→502 guard (`products/platform-gateway/`)
- [x] add `@router.get("/api/v1/skills/{skill_id:path}")` after the list route in `api/routes/skills.py`: resolve request id, resolve identity, `enforce_policy(ACTION_SKILLS_READ)`, delegate to `get_skill`, log `skill_detail_proxied` (`products/platform-gateway/`)
- [x] assert the new route in `tests/test_route_inventory.py` (`products/platform-gateway/tests/`)
- [x] add detail-proxy cases to `tests/test_workspace_proxies.py`: `skills:read` holder gets the full record; non-holder denied before upstream; gateway Basic credential forwarded (not the user token); 404 passthrough; 503 unconfigured; 502 transport/5xx (`products/platform-gateway/tests/`)

## R-2: Portal View action with lazy detail fetch

- [x] declare a local `SkillDetail` interface and add a View actions column + `openSkill(id)` lazy fetch (per-id loading flag, inline `Alert` on error, no fetch until clicked) in `src/views/control/SkillsView.tsx` (`products/operator-portal/web-ui/app/`)
- [x] render `<SkillContentViewer>` from the viewer state and clear it on close (`products/operator-portal/web-ui/app/`)
- [x] add `src/views/control/__tests__/SkillsView.test.tsx`: View control per row; exactly one detail request on click (none for unopened rows); loading state; error surfaces inline without opening the modal (`products/operator-portal/web-ui/app/`)

## R-3: Read-only rendered/raw skill content viewer

- [x] create `src/chat/SkillContentViewer.tsx`: `Modal` with metadata header (title/source/version/tags + `web_target`), `Segmented` Rendered/Raw defaulting to Rendered, bounded scroll pane reusing `md-content` / `evidence-pre`, `renderMarkdown` for the rendered branch, single Close footer, no download/discard, nothing persisted (`products/operator-portal/web-ui/app/`)
- [x] add `src/chat/__tests__/SkillContentViewer.test.tsx`: opens on Rendered; toggle shows raw body; header metadata; a `<script>`/`<img onerror>` body is escaped (not executed); Close dismisses; no download/discard controls (`products/operator-portal/web-ui/app/`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-3)
- [x] `make verify` green (gateway pytest incl. route-inventory + policy-matrix guards; overlays; policy; version lockstep)
- [x] portal `npm test` and `npm run build` green
- [x] living state docs updated: operator guide Skills/transparency section, affected RepoWiki pages (portal workspace views; gateway routing)
- [x] `CHANGELOG.md` entry added referencing SPEC-052
- [x] spec index in `docs/specs/README.md` set to `delivered`
- [x] spec status set to `delivered`

> Delivered 2026-09-05 (v0.34.0), bundled with SPEC-053 and the two v0.33.x
> UX quick-win commits already on `main`. The four Delivery-Gate items closed
> at release time with the version bump: gateway detail proxy 37 passed,
> portal suite green, `npm run build` clean, `make verify` green at VERSION
> 0.34.0.
