# SPEC-028: Tasks

## Backend (agent-platform)

- [x] T-1 (R-1, R-4): `runtime_settings.py` — `"luban"` in
      `RuntimeProvider` / `SUPPORTED_RUNTIME_PROVIDERS`; `_provider_options_from_env`
      luban branch (OpenAI-shaped, `LUBAN_THINKING_ENABLE` opt-in only)
- [x] T-2 (R-1, R-2): `providers/luban.py` adapter (OpenAI-compatible
      build, mandatory base URL validation, permissive discover filter,
      empty curated series) + registry entry
- [x] T-3 (R-1): `model_catalog.py::resolve_credentials` — adapters with
      `default_base_url is None` require `<PROVIDER>_BASE_URL` (drop +
      warning otherwise); existing providers unaffected
- [x] T-4 (R-1…R-4): unit tests — gating (key-only dropped, key+base URL
      enabled), mandatory-base-URL parity for existing providers,
      discover filter, options defaults (thinking off), duplicate-id
      guard, discovery ladder against a stubbed endpoint

## Docs & ops (R-5, R-6)

- [x] T-5: `docs/guides/luban-llm-guide.md` — stack selection,
      laptop/desktop setup with token auth, platform wiring, K8s hosting,
      verification checklist, troubleshooting; guides README row
- [x] T-6: `shared/platform-ops/gitops/llm-hosting/` — README + Ollama
      reference manifests (Deployment/Service/Secret/PVC, sizing notes)
- [x] T-7: configuration-reference `LUBAN_*` rows,
      `runtime-secrets.example.env` commented `LUBAN_*` block,
      agent-platform README provider bullet, CHANGELOG entry

## Delivery

- [x] T-8: `make verify`; commit; `make build`; `make deploy`
- [ ] T-9: live verification — apply Ollama manifests to dev-k8s, wire
      `LUBAN_*` secrets, confirm `/api/v2/models` grouping, portal turn
      on a luban model, audit attribution, discovery metrics; L3 gate;
      push
