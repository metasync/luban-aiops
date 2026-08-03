# SPEC-009 Tasks: Pre-Production Hardening

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Deterministic redaction of tool output

- [ ] add `tools/redaction.py` with code-owned value patterns and the bounded
  explicit key list (`products/tool-gateway/src/api_gateway/tools/redaction.py`)
- [ ] add `GATEWAY_REDACTION_ENABLED` setting, default true
  (`products/tool-gateway/src/api_gateway/core/config.py`)
- [ ] wire redaction into the `invoke_tool` choke point before response and
  audit (`products/tool-gateway/src/api_gateway/services/gateway_service.py`)
- [ ] tests: value patterns, key list, byte-identical passthrough, opt-out
  switch (`products/tool-gateway/tests/test_redaction.py`)

## R-2: Redaction observability and failure policy

- [ ] add `gateway_tool_redacted_spans_total` counter (label: tool)
  (`products/tool-gateway/src/api_gateway/core/metrics.py`)
- [ ] implement fail-closed `REDACTION_OVERFLOW` at the configured fraction
  (default 0.2) via `GATEWAY_REDACTION_OVERFLOW_FRACTION`
  (`products/tool-gateway/src/api_gateway/tools/redaction.py`, `core/config.py`)
- [ ] add `redacted_spans` to the tool-invocation audit log entry
  (`products/tool-gateway/src/api_gateway/services/gateway_service.py`)
- [ ] tests: overflow fail-closed on synthetic mostly-credential payload;
  audit field present (`products/tool-gateway/tests/`)

## R-3: Workload-identity-bound service tokens at the exchange

- [ ] broker: bearer branch in `authenticate_client` validating projected
  SA tokens against the cluster OIDC issuer JWKS with audience check and
  workload-subject → client mapping
  (`products/identity-broker/src/identity_service/services/exchange_service.py`)
- [ ] broker: config `IDENTITY_WORKLOAD_ISSUER_URL` (empty = off),
  `IDENTITY_WORKLOAD_AUDIENCE`, registry mapping
  (`products/identity-broker/src/identity_service/core/config.py`)
- [ ] broker: exchange route accepts `Authorization: Bearer` as the service
  credential alongside HTTP Basic
  (`products/identity-broker/src/identity_service/api/routes/`)
- [ ] broker tests: valid workload token → same delegated claims as static
  path; expired/wrong-audience/unregistered → 401; feature off when issuer
  URL empty (`products/identity-broker/tests/test_exchange_service.py`)
- [ ] gateway: `GATEWAY_WORKLOAD_TOKEN_PATH` setting; `DelegationClient`
  prefers the projected token file, falls back to the static secret with a
  once-per-process warning (`products/tool-gateway/src/api_gateway/`)
- [ ] gateway tests: projected token preferred; fallback + warning when the
  file is missing (`products/tool-gateway/tests/test_delegation.py`)

## R-4: Overlay and documentation alignment

- [ ] document the redaction opt-out and the workload-token contract
  (projected volume snippet, issuer/audience env names)
  (`shared/platform-ops/gitops/dev-k8s/README.md`)
- [ ] mark the static secret as the dev fallback in the gateway example file
  (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env`)
- [ ] verify all overlays render (`make overlays`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (`make verify` green)
- [ ] living state docs updated: root `README.md`, tool-gateway and
  identity-broker READMEs, dev-k8s README
- [ ] Release 1 release notes: Known Limitations updated (redaction and
  workload-identity items resolved)
- [ ] `CHANGELOG.md` entry added referencing SPEC-009
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
