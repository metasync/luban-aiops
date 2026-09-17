# SPEC-058 Plan: HTTP Service-Check Tools — `http.get` and `http.post`

## Approach

One new connector module in tool-gateway holding both tools, plus one extracted
helper it shares with the browser connector, plus one curated approval-card
formatter kernel-side. Nothing else moves.

The implementation groups into four stages, ordered so that each stage leaves
`make verify` green on its own:

1. **Extract, do not add.** `_redact_secret_query` and `_SECRET_QUERY_PARAMS`
   move out of `browser_connector.py` into a new `tools/url_redaction.py`, and
   `validate_secret_vocabulary.py`'s `TOOL_GATEWAY_REL` constant moves in the
   same edit. This is a pure move — behaviour byte-identical, every existing
   browser test passing unmodified — and it lands first because it is the only
   change in the slice that can break `make verify` for a reason unrelated to
   the new code.
2. **Configuration.** Six `GATEWAY_HTTP_*` settings on `GatewaySettings`, all
   defaulting to the closed position (`http_enabled=false`, empty allowlist).
3. **The connector.** `tools/http_connector.py`: one shared request helper
   carrying the allowlist, scheme, destination, redirect and credential
   discipline, with two thin `BaseTool` subclasses over it. Gated wiring in
   `app.py`.
4. **The card.** Kernel-side `_cr_http_post` in `hitl_confirmations.py` and one
   `KNOWN_SAFE_FIELDS` entry in `secret_params.py`, then tests, docs, GitOps and
   the e2e demo.

The single design decision that shapes the code is that **all bounds live in the
connector, not in the tool classes**. R-3 says a future verb inherits the
allowlist, redirect and destination rules "without a re-implementation"; the
mechanical way to make that true is one `_request()` helper that both tools call
and that a third would call too. It is also what makes the test seam single
(R-8's `FakeResponse` double patches one place).

## Design Per Requirement

### R-1: `http.get` — a read-tier bounded response check

- affected files: `products/tool-gateway/src/tool_gateway/tools/http_connector.py` (new),
  `products/agent-platform/src/agent_service/services/kernel_middleware.py`
- chosen approach: `HttpGetTool(BaseTool)` with `risk_level="read"`,
  `category="http"`, `SOURCE_SYSTEM = "http"`. `execute()` measures its own
  `time.perf_counter()` and builds the evidence envelope with `build_evidence`,
  exactly as `k8s_connector` does. Parameter coercion returns
  `(value, error_message)` tuples rather than raising — the `_coerce_tail_lines`
  idiom — because LLM-supplied parameters are untrusted and a bad value must
  surface as a structured `INVALID_PARAMETERS` result.
- The projection is a module-level `_project_response()` shared by both verbs,
  returning the fixed key set. `_PROJECTED_HEADERS` is a frozenset of six
  lowercase names; `set-cookie` and `authorization` are absent from it and the
  set is not configurable, so the only way to add them is to edit the constant —
  which is the point (a test asserts their suppression with a response that
  carries them).
- Body handling: `application/json` → `response.json()` guarded by a
  `ValueError` catch that degrades to text; `text/*` → string; anything else →
  `body` omitted and `content_type`/`content_length` reported. Truncation reads
  `response.content[:max_bytes]` and sets `truncated` when the cut was real.
- The upstream-status-is-a-fact rule falls out of the shape: `_request()`
  returns the response and only raises for transport-level failures, so a 503
  reaches `_project_response` and comes back as `status: "success"` with
  `data.status == 503`. `UPSTREAM_ERROR` is reserved for the case where the
  gateway could not complete a response at all (an `httpx.HTTPError` subclass
  that is neither a timeout nor a connect error).
- The read tier is a fact about two products, not one. The gateway registers
  `http.get` at `risk_level="read"`; agent-platform's permission middleware
  decides separately whether a call parks, and it admits only tools that are
  **both** on its curated `DEFAULT_AUTO_ALLOWED_TOOLS` and `is_read_only`.
  `http.get` joins that list — the same footing SPEC-049 gave the read-class
  `web.*` probes — and `http.post` stays off it. Found by the SPEC-059 ladder's
  bottom rung, which is the first assertion in the repository that a read-tier
  tool parks *zero* cards end to end rather than at the gateway alone.
- alternatives rejected: a general-purpose `http.request(method, …)` tool — one
  tool with a `method` parameter is a wider surface than two named tools and
  gives the model a choice it does not need; R-3's write tier could not be
  enforced per-verb at all, since risk level is a property of the definition.

### R-2: A server-side origin allowlist that both tools share

- affected files: `http_connector.py`
- chosen approach: a module-level `_validate_destination(url, allow_origins)`
  returning `(origin, error_code, message) | (origin, None, None)`, called by
  `_request()` before any client is constructed. It reuses
  `browser_connector.origin_of` for normalization — importing rather than
  re-implementing, because two connectors computing an origin differently is
  exactly the drift the allowlist exists to prevent.
- Redirects: `httpx.AsyncClient(follow_redirects=False)` and an explicit loop
  of at most `_MAX_REDIRECTS = 3`, re-validating each `location` against the
  allowlist and resolving a relative target with `urljoin` before the check.
  An out-of-allowlist hop returns `HTTP_REDIRECT_NOT_ALLOWED` naming the origin
  it tried to reach; exhausting the budget returns `HTTP_REDIRECT_NOT_ALLOWED`
  too, with a message saying the hop limit was reached. Manual redirect
  following is not optional here — `follow_redirects=True` would let httpx
  cross the boundary before the connector could look.
- Destination refusals use `ipaddress` on the parsed host: loopback, link-local
  (which covers `169.254.169.254`) and multicast are refused with
  `HTTP_ORIGIN_NOT_ALLOWED` regardless of allowlist content. A hostname that is
  not an IP literal is never refused on this ground — `http://acme-admin:8080`
  is the intended shape. Private ranges are deliberately not refused.
- Userinfo: `urlsplit(...).username or .password` present → `INVALID_PARAMETERS`
  with an explicit message. Scheme not in `{http, https}` →
  `HTTP_SCHEME_NOT_ALLOWED`.
- alternatives rejected: resolution-time pinning — recorded as R-2's known
  limit and a Non-Goal; it needs a custom transport and a DNS-TTL decision.

### R-3: `http.post` — a write-tier bounded JSON mutation

- affected files: `http_connector.py`
- chosen approach: `HttpPostTool(BaseTool)` with `risk_level="write"`, offered
  unconditionally by `register_tools` and refused by the registry's existing
  risk-tier admission when `GATEWAY_MUTATING_TOOLS_ENABLED` is off — the same
  division of labour `k8s_connector.register_tools` uses, so the flag semantics
  stay in one place.
- Body validation is a module-level `_validate_body(body, max_bytes)` running
  **before** `_request()`: must be a dict; depth ≤ 2 measured by
  `_json_depth`; total key count ≤ 32 measured across both levels; serialized
  size ≤ `GATEWAY_HTTP_MAX_REQUEST_BYTES`. Depth or key overflow →
  `INVALID_PARAMETERS`; size overflow → `HTTP_BODY_TOO_LARGE`. Both are checked
  before the transport is touched, and the tests assert that with a double that
  fails if called.
- `content-type` is set by the connector, never taken from a parameter.
- The POST-URL secret rule: `_validate_destination` gains a
  `forbid_secret_query: bool` argument, `False` for GET and `True` for POST,
  checking each query key against the extracted `_is_secret_param` from
  `url_redaction` and returning `HTTP_URL_SECRET_NOT_ALLOWED`. One helper, two
  policies, no duplicated vocabulary.
- `mutation_confirmed` is added by the POST tool after projection:
  `data["mutation_confirmed"] = 200 <= status < 300`.
- alternatives rejected: a `PUT`/`PATCH`/`DELETE` set — Non-Goal; and taking the
  body as a JSON *string* parameter, which would put serialization errors in the
  model's hands and make the depth bound unenforceable before parsing.

### R-4: Credentials enter by reference only

- affected files: `http_connector.py`, `core/config.py`
- chosen approach: the connector holds a `CredentialSetStore` constructed from
  `http_credential_sets_path`, which defaults in `GatewaySettings.from_env()` to
  the browser path when unset — so one mounted secret serves both surfaces and
  an operator can still point them apart. Resolution happens inside
  `_request()`, and the resulting `httpx.BasicAuth` is passed to the client
  constructor. The credential value never touches a result, a log line or an
  evidence field; only the set name does.
- Unknown name → `CREDENTIAL_SET_NOT_FOUND`, the browser connector's existing
  code. Unconfigured store → the same code with a distinct message, so the two
  are separable in a transcript.
- Neither `parameters_schema` declares a `headers` property, and a test asserts
  its absence on both — the structural control R-5's masking divergence rests
  on, so it is asserted rather than merely omitted.
- alternatives rejected: an `authorization` string parameter (a literal secret
  in a durable record) and a free-form `headers` map (the same, plus it would
  let the agent send SPEC-059's `X-Luban-Demo-Reset`).

### R-5: The `http.post` approval card

- affected files: `products/agent-platform/src/agent_service/services/hitl_confirmations.py`,
  `services/secret_params.py`
- chosen approach: a `_cr_http_post(parameters, display_hint)` formatter beside
  the eight existing ones, registered in `_CHANGE_REQUEST_FORMATTERS`. Its
  summary is `POST to <masked url> — N field(s): k1, k2`, and its `fields` are
  the body's keys rendered through `_cr_field` with `masked=is_secret_param(key)`,
  plus a `credential_set` row when present (the reference name, never a value).
  Nested values are rendered by `_display_value` (which JSON-dumps a dict) after
  a recursive mask of secret-named keys, so `{"user": {"password": "…"}}` shows
  the shape with the secret hidden.
- `KNOWN_SAFE_FIELDS` gains `http.post.url` only. `OPAQUE_VALUE_FIELDS` gains
  nothing — R-5's reasoning is that a JSON body's keys are visible to name
  matching and `_parameterize_nested` already descends, so marking the body
  opaque would make every HTTP-mutating skill un-graduable.
- The URL is masked through `secret_params.redact_secret_query` even though R-3
  already refuses a secret-bearing POST URL: defence in depth, and it means the
  formatter is correct if that refusal is ever relaxed.
- alternatives rejected: leaving the tool uncurated (the generic fallback
  renders `url: ***` / `body: ***`, which is approval theatre) and adding
  `http.post.body` to `KNOWN_SAFE_FIELDS` (that would unmask the body in the raw
  `parameters` sibling too, collapsing the intended asymmetry).

### R-6: URL secret-masking becomes a shared gateway helper

- affected files: `products/tool-gateway/src/tool_gateway/tools/url_redaction.py` (new),
  `tools/browser_connector.py`, `shared/shared-contracts/scripts/validate_secret_vocabulary.py`
- chosen approach: move `_SECRET_QUERY_PARAMS`, `_is_secret_param` and
  `_redact_secret_query` verbatim into `url_redaction.py` with the leading
  underscore dropped from the two names that now cross a module boundary
  (`SECRET_QUERY_PARAMS`, `is_secret_param`, `redact_secret_query`), keeping the
  TWIN comments and the docstrings intact. `browser_connector.py` imports all
  three and keeps no local definition. The kernel twin in `secret_params.py` is
  untouched.
- **The validator constant moves in the same commit.** `TOOL_GATEWAY_REL`
  becomes `products/tool-gateway/src/tool_gateway/tools/url_redaction.py` and
  `TOOL_GATEWAY_VAR` becomes `SECRET_QUERY_PARAMS`. `extract_vocabulary`'s
  `_tuple_pattern` anchors at line start, so the un-underscored name matches
  unchanged. Splitting the move from the constant breaks `make verify` in
  between, which is why these are one edit.
- The validator's own docstring names the old path; that sentence is corrected
  in the same edit so the documentation and the constant agree.
- alternatives rejected: re-exporting the names from `browser_connector` for
  compatibility — nothing outside the module imports them, and a re-export would
  leave two importable homes for one vocabulary, which is the drift this leg
  exists to prevent.

### R-7: Configuration, wiring, and activation documentation

- affected files: `core/config.py`, `app.py`,
  `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`,
  `docs/guides/tool-configuration.md`, `docs/guides/adding-a-tool.md`,
  `docs/guides/configuration-reference.md`
- chosen approach: six settings with `DEFAULT_HTTP_*` module constants in the
  same block style as the browser defaults, `_env_bool` for the flag, and the
  same comma-split-and-strip expression for the allowlist that
  `browser_allow_origins` uses. `app.py` gains a gated block after the browser
  one, with the import inside the branch, constructing `HttpConnector` and
  calling `register_tools`. The connector has no lifecycle hooks, so it is not
  returned from `_build_tool_registry()` and the function's tuple shape is
  unchanged — a deliberate non-change, since `create_app` unpacks it.
- `runtime-config.env` gains `GATEWAY_HTTP_ENABLED=false` plus commented
  examples and an activation block in the voice of the two already there,
  naming all four preconditions. The base names no origin.
- alternatives rejected: gating the connector on allowlist presence (the guide's
  `cmdb.lookup` pattern) — this connector has no single upstream URL, so the
  boolean flag is the honest switch, and gating on a list would make an operator
  who sets the flag but forgets the list get a registered tool that denies
  everything rather than a clear startup log.

### R-8: Tests and delivery traceability

- affected files: `products/tool-gateway/tests/test_http_connector.py` (new),
  `products/agent-platform/tests/services/test_hitl_confirmations.py`,
  `products/agent-platform/tests/test_kernel_middleware.py`,
  `shared/platform-ops/e2e/http-check-demo.sh` (new), `Makefile`
- chosen approach: model the suite on `test_skills_connector.py`'s `FakeResponse`
  seam — a `FakeTransport` object patched over the connector's single
  `_request` transport call site, recording the URL, method, headers and body it
  was given and returning a canned response. Recording is what makes the
  "refused before any request is made" criteria assertable: a denial test checks
  both the error code and that the double was never called.
- Kernel-side, the `_cr_http_post` tests sit beside the existing formatter tests
  and include the digest-invariance assertion and the uncurated-tool regression
  guard. The auto-allow half of R-1 lands in `test_kernel_middleware.py` beside
  the SPEC-049 browser-tier test it mirrors: `http_get` on the resolved list,
  `http_post` off it, and `http_post` still ASKing when forced on.
- The e2e script asserts registration, an allowlist denial, a live `http.get`
  against the deployed target, and one parked-and-approved `http.post`, and is
  added to the `e2e` target's hardcoded list.

## Sequencing And Dependencies

1. R-6 extraction + validator constant — depends on nothing; must land whole.
2. R-7 configuration settings — depends on nothing.
3. R-2 destination validation, R-1 GET, R-3 POST, R-4 credentials — depends on
   stages 1 and 2 (the helper and the settings).
4. R-7 `app.py` wiring — depends on stage 3.
5. R-5 kernel formatter and `KNOWN_SAFE_FIELDS` — depends on nothing in the
   gateway, but is tested against the real tool name, so it lands with stage 3.
6. R-8 tests — written alongside each stage, run as one suite at the end.
7. R-7 GitOps and guides, R-8 e2e script and Makefile entry — depend on stages
   2–5 being settled, since the docs name the final error codes.

## Test Strategy

- unit tests: `test_http_connector.py` covers every R-1…R-4 acceptance criterion
  through the `FakeTransport` seam — parameter coercion, the projection's fixed
  key set, header allowlisting with a `set-cookie` present, truncation, binary
  omission, the upstream-status-is-a-fact rule for both verbs, every allowlist
  and destination refusal, both redirect outcomes, the three body bounds,
  credential resolution and its never-echoed assertions, and registration
  present/absent on the flag. Kernel-side, the `_cr_http_post` projection, the
  raw-sibling asymmetry and the digest invariance.
- mutation spot-checks on the three security-critical behaviours (allowlist
  denial, `set-cookie` suppression, credential non-echo): each is deliberately
  broken once and the suite must fail.
- contract tests: none new — `tool-result.schema.json` is a generic envelope and
  `data` is free-form, so there is no schema to validate. The existing
  tool-result envelope tests cover the shape.
- integration / overlay validation: `make verify` must pass with
  `validate-policy` green against an **unmodified** bundle (that is the
  assertion, not a convenience) and `validate-secret-vocabulary` green after the
  R-6 move; `make overlays` renders the base with the new keys and no origin.
  Live validation is `shared/platform-ops/e2e/http-check-demo.sh` under
  `make e2e`, and SPEC-059's demo scripts exercise both tools against a real
  deployed target.

## Rollout And Migration

- deployment or configuration changes required: none to activate by default.
  `GATEWAY_HTTP_ENABLED` ships `false` in the base overlay, so an existing
  cluster gains nothing and loses nothing on upgrade. Activation is the
  four-precondition checklist the base env block and `tool-configuration.md`
  both carry; SPEC-059's `browser-dev` runtime profile is the first place it is
  switched on.
- backward compatibility notes: the connector registers no tool until the flag
  is set, so discovery output is unchanged for every existing deployment. No
  policy action, no audit event type and no contract changes, so nothing
  downstream needs a coordinated release. The R-6 move is import-internal.
- rollback approach: set `GATEWAY_HTTP_ENABLED=false` (or remove the profile
  entries) and the tools disappear from discovery on the next gateway start; no
  state is written anywhere. Reverting the code is likewise safe — nothing
  persists an `http.*` result in a shape a rollback could not read, since the
  result envelope is the generic one.
