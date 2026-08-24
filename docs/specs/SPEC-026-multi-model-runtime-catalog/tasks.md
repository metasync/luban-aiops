# SPEC-026: Tasks

## Backend (agent-platform)

- [x] T-1 (R-1): provider adapters gain `model_series`; curated sets for
      deepseek / dashscope / openai — `providers/{base,deepseek,dashscope,openai}.py`
- [x] T-2 (R-4, R-5): `runtime_settings.py` parses `<PROVIDER>_MODELS`,
      drops the `profile == provider` equality check
- [x] T-3 (R-1, R-2): `services/model_catalog.py` emits one entry per
      model (id = model name), override filtering, default force-include,
      duplicate-id guard
- [x] T-4 (R-3): kernel resolution accepts legacy provider-name ids via
      alias map; unresolvable pinned ids fall back to catalog default —
      `runtime_kernel.py` MODEL_CATALOG call sites
- [x] T-5 (R-1…R-4): unit tests: series build, override, force-include,
      legacy alias, fail-closed unknown id, duplicate guard

## Contracts + portal

- [x] T-6 (R-2): `shared/shared-contracts/schemas/model-catalog.schema.json`
      id semantics update
- [x] T-7 (R-2): portal `ModelSelect` groups options by provider;
      `ModelSelect.test.tsx` + `ComposerSelectionBar.test.tsx` updated

## GitOps consolidation (R-5)

- [x] T-8: `runtime-profiles/default/` (configmap + secrets example with
      all provider keys + `<PROVIDER>_MODELS` docs)
- [x] T-9: delete `runtime-profiles/{deepseek,dashscope,openai}`; migrate
      local untracked secret file into `default/`
- [x] T-10: update references — `select-runtime-profile.sh`,
      `sync-runtime-secret.sh`, `verify-runtime-profile.sh`,
      `sync-otel-secrets.sh`, Makefile profile list,
      `dev-k8s/kustomization.yaml`

## Docs + delivery

- [x] T-11: CHANGELOG, agent-platform / operator-portal READMEs,
      configuration-reference
- [ ] T-12: `make verify`; commit; `make build`; `make deploy`; secret
      sync as `default` profile
- [ ] T-13: live verification — catalog series, one turn per provider,
      audit attribution; L3 gate; push
