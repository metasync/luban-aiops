# SPEC-058 Tasks: HTTP Service-Check Tools — `http.get` and `http.post`

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-6: URL secret-masking becomes a shared gateway helper

Lands first and whole: the move and the validator's path constant are one
atomic change, because splitting them breaks `make verify` in between.

- [x] create `products/tool-gateway/src/tool_gateway/tools/url_redaction.py`
      holding `SECRET_QUERY_PARAMS`, `is_secret_param` and
      `redact_secret_query` moved verbatim from `browser_connector.py`, TWIN
      comments and docstrings intact
- [x] `browser_connector.py` imports all three and keeps no local definition
      (`products/tool-gateway/src/tool_gateway/tools/browser_connector.py`)
- [x] move `TOOL_GATEWAY_REL`/`TOOL_GATEWAY_VAR` in
      `shared/shared-contracts/scripts/validate_secret_vocabulary.py` and
      correct the docstring sentence that names the old path — same commit
- [x] test: every existing browser test passes after the helper import move
      (`products/tool-gateway/tests/`)
- [x] `make validate-secret-vocabulary` exits 0
- [ ] optional mutation spot-check: adding a term to one copy only fails
      (not separately rerun during this delivery)

## R-7: Configuration

- [x] six `DEFAULT_HTTP_*` constants and six `GatewaySettings` fields —
      `http_enabled`, `http_allow_origins`, `http_timeout_ms`,
      `http_max_response_bytes`, `http_max_request_bytes`,
      `http_credential_sets_path` — with the credential-sets path defaulting to
      the browser path when unset (`products/tool-gateway/src/tool_gateway/core/config.py`)
- [x] test: `from_env()` defaults are the closed position; the allowlist parses
      and strips exactly as `browser_allow_origins` does
      (`products/tool-gateway/tests/test_http_connector.py`)

## R-2: Destination validation

- [x] `_validate_destination(url, allow_origins, forbid_secret_query)` reusing
      `browser_connector.origin_of`, returning a code and message rather than
      raising (`products/tool-gateway/src/tool_gateway/tools/http_connector.py`)
- [x] scheme refusal, userinfo refusal, loopback/link-local/multicast refusal
      via `ipaddress`, empty-allowlist denial, port-sensitivity
- [x] GET redirect loop, max three hops, relative targets resolved with
      `urljoin` and re-checked, out-of-allowlist hop halting
- [x] review hardening: POST never follows redirects; `location` projection
      masks secret queries; regression tests cover both boundaries
- [x] test: empty allowlist denies and the transport double is never called
- [x] test: `file:///etc/passwd`, `http://user:pass@host/`,
      `http://169.254.169.254/latest/meta-data/` each refused with its named
      code regardless of allowlist content
- [x] test: three-hop in-allowlist chain succeeds; second hop leaving it returns
      `HTTP_REDIRECT_NOT_ALLOWED` naming that origin
- [ ] optional mutation spot-check (not rerun): removing the allowlist check fails the suite

## R-1: `http.get`

- [x] `HttpGetTool` at `risk_level="read"`, `category="http"`,
      `source_system="http"`, with `_coerce_*` parameter helpers returning
      `(value, error)` tuples (`products/tool-gateway/src/tool_gateway/tools/http_connector.py`)
- [x] `_project_response()` fixed key set: `url` (query-masked), `status`,
      `elapsed_ms`, `headers` (six-name allowlist), `body` (JSON / text /
      omitted), `content_type`, `content_length`, `truncated`
- [x] error ladder: `INVALID_PARAMETERS`, `HTTP_SCHEME_NOT_ALLOWED`,
      `HTTP_ORIGIN_NOT_ALLOWED` (denied), `HTTP_REDIRECT_NOT_ALLOWED`,
      `HTTP_TIMEOUT`, `TOOL_EXECUTION_ERROR`, `UPSTREAM_ERROR`
- [x] test: JSON endpoint projects status/elapsed/headers/parsed body; binary
      endpoint omits `body` and reports `content_type`
- [x] test: a body over `max_bytes` is cut and `truncated` is true
- [x] test: `set-cookie` present in the response produces no `set-cookie` key,
      and a JSON body carrying `token` is `[REDACTED]` by the gateway redaction
- [x] test: upstream 503 yields `status: "success"` with `data.status == 503`
- [x] test: timeout → `HTTP_TIMEOUT`, connection refusal →
      `TOOL_EXECUTION_ERROR`, neither raises
- [ ] optional mutation spot-check (not rerun): adding `set-cookie` to `_PROJECTED_HEADERS` fails
- [x] `http.get` joins `DEFAULT_AUTO_ALLOWED_TOOLS`; `http.post` does not
      (`products/agent-platform/src/agent_service/services/kernel_middleware.py`)
      — without it a read-tier health check parks an `action` card, so the
      gateway's `risk_level="read"` would be true only of the gateway
- [x] test: `http_get` is on the resolved allow-list and `http_post` is not;
      forcing `http_post` on still yields an ASK
      (`products/agent-platform/tests/test_kernel_middleware.py`)
- [x] the built-in list documented in `docs/guides/approval-and-hitl.md`
      names the browser reads and `http.get`, and points at the constant as
      the authoritative copy

## R-3: `http.post`

- [x] `HttpPostTool` at `risk_level="write"`, registered unconditionally so the
      registry's risk-tier admission is the only gate
- [x] `_validate_body()` — dict only, depth ≤ 2, ≤ 32 keys, serialized size ≤
      `GATEWAY_HTTP_MAX_REQUEST_BYTES` — running before the transport
- [x] `content-type` fixed by the connector; POST URL secret-query refusal via
      `forbid_secret_query=True`
- [x] `data.mutation_confirmed` false on a non-2xx response
- [x] test: with the mutating flag off `http.post` is absent from discovery and
      invoking it returns `TOOL_NOT_FOUND`
- [x] shared authorization regression: a read-only observer is denied a write
      with `risk_level="write"` in the evidence (`test_tool_invoke.py`);
      HTTP-specific registration tests independently pin POST's write tier
- [x] test: depth 3, 33 keys and over-cap bodies each refused with the transport
      double uncalled
- [x] test: `http.post` on `…?newpw=hunter2` → `HTTP_URL_SECRET_NOT_ALLOWED`,
      while `http.get` on the same URL succeeds with the value masked
- [x] test: a 409 yields `status: "success"`, `data.status == 409`,
      `data.mutation_confirmed == false`

## R-4: Credentials by reference only

- [x] `CredentialSetStore` held by the connector; `httpx.BasicAuth` applied in
      `_request()`; only the set name ever surfaces
      (`products/tool-gateway/src/tool_gateway/tools/http_connector.py`)
- [x] `CREDENTIAL_SET_NOT_FOUND` for an unknown name and for an unconfigured
      store, with distinct messages
- [x] test: the resolved value appears in no result, evidence field or log
      record; the set name does
- [x] test: rotating the file changes the value used with no restart
- [x] test: neither tool's `parameters_schema` contains a `headers` property

## R-5: The `http.post` approval card

- [x] `_cr_http_post` formatter registered in `_CHANGE_REQUEST_FORMATTERS`
      (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [x] `KNOWN_SAFE_FIELDS` gains `http.post.url` only; `OPAQUE_VALUE_FIELDS`
      unchanged (`products/agent-platform/src/agent_service/services/secret_params.py`)
- [x] test: summary names the origin, path and body key names; `{"locked": true}`
      renders; `{"password": "hunter2"}` renders `password: ***`;
      `{"user": {"password": "hunter2"}}` renders the nested key masked
      (`products/agent-platform/tests/`)
- [x] test: the raw `parameters` sibling shows `body: "***"` and the URL
      verbatim, and the signed `args_digest` is byte-identical with the
      projection disabled
- [x] test: the uncurated-tool generic fallback still masks everything
      (regression guard, unchanged by this slice)

## R-7: Wiring, GitOps and guides

- [x] gated block in `_build_tool_registry()` with the import inside the branch;
      the returned tuple shape unchanged
      (`products/tool-gateway/src/tool_gateway/app.py`)
- [x] test: with no `GATEWAY_HTTP_*` variable set, no `http.*` tool registers
      and discovery is unchanged from today
- [x] `GATEWAY_HTTP_ENABLED=false` plus commented examples and the
      four-precondition activation block
      (`shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`)
- [x] `make overlays` renders `dev-k8s` and all runtime profiles; the rendered
      base carries the flag and no origin
- [x] HTTP Connector Tools table, activation checklist and error codes
      (`docs/guides/tool-configuration.md`); the six variables
      (`docs/guides/configuration-reference.md`); the two-tool-shapes sentence
      (`docs/guides/adding-a-tool.md`)

## R-8: Tests, e2e and traceability

- [x] `products/tool-gateway/tests/test_http_connector.py` over a single
      `httpx.MockTransport` seam with a request-recording `_Router`
- [x] `shared/platform-ops/e2e/http-check-demo.sh` asserting registration,
      allowlist denial, a live `http.get` and one parked-and-approved
      `http.post`; added to the `make e2e` hardcoded list (`Makefile`)
- [x] `make -C products/tool-gateway test` green; `make verify` green including
      `validate-policy` with an **unmodified** bundle

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
