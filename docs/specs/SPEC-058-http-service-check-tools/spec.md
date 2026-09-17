# SPEC-058: HTTP Service-Check Tools — `http.get` and `http.post`

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-17
- approved: 2026-09-17
- delivered: 2026-09-17 (v0.38.0)
- release slice: R5 — Hardening and External Consumption (twentieth R5 slice,
  v0.38.0 — it lands before SPEC-057 because SPEC-057's compositions need the
  single-target repertoire SPEC-059 supplies and SPEC-059 needs this spec's
  tools; SPEC-057 therefore moves to v0.40.0, and SPEC-059 ships alongside this
  spec in v0.38.0 rather than waiting for v0.39.0)
- related ADRs: **ADR-0008** (spec delivery requires requirement-to-test
  traceability and exercised samples — R-8), ADR-0007 (one HITL gate per
  mutating browser flow — **not** extended and not reversed: an `http.post` is
  not a browser interaction and parks its own per-action card, which is the
  SPEC-054 posture, not the flow posture), ADR-0010 (signed execution
  envelopes declare their authority provenance — unchanged; an approved
  `http.post` rides the existing envelope and `args_digest` machinery).
  lineage: extends SPEC-049 (browser web-check tools — the origin-allowlist,
  credential-set and URL-redaction postures this spec reuses rather than
  reinvents), SPEC-050 (tool registration and discovery), SPEC-021 (bounded
  mutating actions — the risk-tier admission and one-named-object discipline
  `http.post` inherits), SPEC-054 (action-level approval and the
  change-request card — the card an `http.post` parks), SPEC-055 R-7 (the
  fail-closed masking posture R-5 reasons about and deliberately diverges
  from on one field), SPEC-009 (redaction at the gateway choke point),
  SPEC-007 (tool execution framework — `BaseTool`/`ToolRegistry`/`ToolResult`).
- drafting: from the 2026-09-17 design discussion on enriching the
  single-target skill walkthroughs, which needs an API-checking surface the
  platform does not have. Grounded in `docs/guides/adding-a-tool.md`, whose
  worked example (`cmdb.lookup`) is the *other* tool shape — see Motivation.

## Summary

Give the agent a bounded HTTP surface for the most common operations task
there is — checking whether a service is healthy and what its API says — by
adding two tools to the tool-gateway: `http.get` (read tier) and `http.post`
(write tier). Both are confined to a server-side origin allowlist that is
deny-by-default, both report through the existing `ToolResult` evidence
envelope, and neither introduces a policy action, an audit event type, or a
shared-contract schema change. `http.post` parks exactly one per-action
change-request card through machinery that already exists for every
non-browser write tool, so the platform's first non-browser mutating
primitive arrives with the approval, signing, redaction and audit posture
already built rather than newly invented.

## Motivation

**The platform has no HTTP surface at all.** The tool-gateway registers
fifteen `web.*` tools and five `k8s.*` tools. A "check whether this service is
healthy" skill therefore has to drive a headless browser to `/healthz` and
scrape JSON out of a rendered page with `web.extract`. That works, and it is
not absurd — but it is the wrong instrument: it costs a browser session, it
couples an API assertion to DOM rendering, and it cannot express the simplest
operational fact ("this endpoint returned 503") without a page load in the
way. Operators asking Luban to check a service API is a first-class use case,
and today it is served by a workaround.

**The shape question is the reason this is a spec and not a
`cmdb.lookup`-style connector.** [`docs/guides/adding-a-tool.md`](../../guides/adding-a-tool.md)
already documents the contributed-connector recipe, and its worked example
takes the upstream from *configuration* (`GATEWAY_CMDB_SERVICE_URL`) while the
model supplies only a validated identifier. That shape is safe because the
deployment chooses the upstream. `http.get(url)` inverts it: **the model
supplies the URL**, which is `web.navigate`'s shape, so it must inherit
`web.navigate`'s discipline — a server-side origin allowlist, deny-by-default,
and redirects that halt when they leave it — rather than `cmdb.lookup`'s.
Getting that inversion wrong is the whole risk in this slice, and it is why
R-2 is a requirement of its own.

**Why now.** SPEC-059 (the `acme-admin` sample application and its
single-target skill suite) needs a genuinely read-only, card-free health-check
skill to complete a 0/0/1/1 approval-pattern teaching ladder, and SPEC-057's
compositions need single-target skills to compose. Both are blocked on an API
surface. There is also a gap nobody has been able to close: **every shipped
`web-checks` skill is `risk_class: write`**, including `InventoryHealth`,
because signing into a page requires `web.click`. An unauthenticated
`http.get` makes a card-free read-only skill possible for the first time.

**And the shipped skill library already claims this surface exists.**
[`InventoryHealth`](../../../shared/platform-ops/skills/platform-runbooks/web-checks/InventoryHealth.md)
states its own purpose as "Complements the API-level checks by exercising the
rendered UI". There are no API-level check skills anywhere in
`shared/platform-ops/skills/` — not one — because there is no HTTP tool to
write one with. That sentence is a documented promise the platform cannot
keep, and it is the cheapest available evidence that this gap is felt rather
than invented.

**The cost is genuinely small, and three repo facts establish it.** Policy in
this platform is tier-based, not tool-name-based — `tools:invoke` and
`tools:mutate` are the only tool actions in the bundle
([`policy-default.yaml:107`](../../../shared/shared-contracts/policies/policy-default.yaml),
`:126`) — so a read-tier tool needs **no bundle change**, as
`adding-a-tool.md` §6 states outright. `httpx` is already a tool-gateway
dependency and `opentelemetry-instrumentation-httpx` is already wired, so the
connector is traced for free with no new dependency. And redaction is applied
at the single `invoke_tool` choke point (SPEC-009), so results are already
scrubbed of PEM blocks, JWTs, Bearer values and the sensitive-key vocabulary
before they leave the gateway.

**`http.post` is included in this slice on the operator's explicit decision**,
against the drafting recommendation to defer it. The recommendation was based
on it being the platform's first arbitrary-body mutating primitive outside the
browser. Verification during drafting removed most of that concern, and the
residue is narrow enough to be a requirement rather than a separate spec:
[`runtime_kernel.py:1251`](../../../products/agent-platform/src/agent_service/runtime_kernel.py)
computes `approval_kind = "flow" if browser_flow else "action"`, so **a
non-browser write tool already parks as an `action` card** and already
receives SPEC-054 R-3's change-request projection and SPEC-055 R-7's
fail-closed raw-parameter redaction. `k8s.delete_pod` has been exercising that
path since SPEC-021. What is *not* free is the card's legibility (R-5), and
that is where this spec spends its design attention.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: `http.get` — a read-tier bounded response check

The connector registers `http.get(url, timeout_ms?, max_bytes?)` at
`risk_level="read"`, `category="http"`, returning the standard `ToolResult`
envelope with `source_system="http"`. It exists to answer "is this endpoint
up, and what does it say", not to be a general-purpose fetch.

Parameters:

- `url` (required, string) — absolute `http`/`https` URL. Model-supplied, so
  it is validated and allowlisted server-side (R-2) before any request is
  made.
- `timeout_ms` (optional, integer, default 10000, hard max 30000) — mirrors
  the `REQUEST_TIMEOUT_SECONDS = 10.0` convention the other connectors use.
- `max_bytes` (optional, integer, default and hard max from
  `GATEWAY_HTTP_MAX_RESPONSE_BYTES`, itself defaulting to 65536) — the
  response-body cap, matching the `GATEWAY_BROWSER_SCREENSHOT_MAX_BYTES`
  precedent of a bounded payload with a configured ceiling.

The result `data` projects a **fixed key set**, per the guide's rule that a
tool's output stays stable for the agent even when the upstream grows fields:

- `url` — the request URL with secret-bearing query values masked (R-6).
- `status` — the HTTP status code as an integer.
- `elapsed_ms` — gateway-measured round trip.
- `headers` — **an allowlist projection, never the upstream's header set**:
  `content-type`, `content-length`, `location`, `server`, `date`,
  `cache-control`. Every other header is dropped. `set-cookie` and
  `authorization` are dropped unconditionally and are not configurable into
  the list: a session cookie is a credential, and neither the redaction
  engine's value patterns nor its sensitive-key vocabulary would catch one
  sitting under the key `set-cookie`.
- `body` — content-type aware: `application/json` is parsed and included as a
  structure; `text/*` is included as a string; anything else (binary, images,
  octet-stream) is **omitted**, with `content_type` and `content_length`
  reported instead so the agent can say what it found without receiving bytes
  it cannot reason about.
- `truncated` — boolean, true when the body was cut at `max_bytes`.

`execute()` never raises; it follows the guide's error ladder with these
codes: `INVALID_PARAMETERS`, `HTTP_SCHEME_NOT_ALLOWED`, `HTTP_ORIGIN_NOT_ALLOWED`
(as a `denied` result, R-2), `HTTP_REDIRECT_NOT_ALLOWED`, `HTTP_TIMEOUT`,
`TOOL_EXECUTION_ERROR` for transport failures, `UPSTREAM_ERROR` for a
non-2xx/3xx status the caller should see as a failure. A 4xx/5xx from the
upstream is **returned as a successful tool result carrying that status**, not
as an error: "the service answered 503" is the fact a health check exists to
report, and turning it into a tool error would hide the very signal the skill
is asking for. `UPSTREAM_ERROR` is reserved for responses the gateway itself
could not complete.

The tier is only half the story: agent-platform decides whether a call parks
on its own curated auto-allow list
(`DEFAULT_AUTO_ALLOWED_TOOLS`,
[`kernel_middleware.py`](../../../products/agent-platform/src/agent_service/services/kernel_middleware.py)),
which admits a tool when it is **both** listed and `is_read_only`, and answers
everything else with an explicit ASK. `http.get` therefore joins that list —
alongside the read-class `web.*` probes SPEC-049 admitted on the same footing —
and `http.post` does not. Without the entry a read-tier health check parks an
`action` card per call, and the gateway's `risk_level="read"` would be true
only of the gateway.

Acceptance criteria:

- `http.get` appears in discovery when and only when the connector is
  configured (R-7), and requires only `tools:invoke` — no policy bundle
  change, no `GATEWAY_MUTATING_TOOLS_ENABLED`.
- A JSON endpoint returns `status`, `elapsed_ms`, the projected `headers` and
  the parsed `body`; a binary endpoint returns no `body` and reports
  `content_type`.
- A body larger than `max_bytes` is cut and `truncated` is true.
- A response carrying `set-cookie` produces no `set-cookie` key in `headers`,
  and a response whose JSON contains a `token` key has that value replaced by
  `[REDACTED]` by the existing gateway redaction (SPEC-009) — asserted, not
  assumed.
- An upstream 503 yields `status: "success"` with `data.status == 503`.
- A timeout yields `HTTP_TIMEOUT`; a connection refusal yields
  `TOOL_EXECUTION_ERROR`; neither raises.
- The evidence block carries `risk_level="read"`, `source_system="http"` and
  a measured `duration_ms`.
- `http.get` is on the kernel's built-in auto-allow list and `http.post` is
  not; forcing `http.post` onto the list still yields an ASK, because the
  read-only half of that gate refuses it.

### R-2: A server-side origin allowlist that both tools share, deny-by-default

`GATEWAY_HTTP_ALLOW_ORIGINS` is a comma-separated origin allowlist parsed and
compared exactly as `GATEWAY_BROWSER_ALLOW_ORIGINS` is
([`config.py:161-163`](../../../products/tool-gateway/src/tool_gateway/core/config.py),
`is_origin_allowed`): scheme + host + port, lowercased, no path, no wildcards.
An empty allowlist denies everything. A URL whose origin is not listed returns
a `denied` result with `HTTP_ORIGIN_NOT_ALLOWED` naming the offending origin —
**before** any socket is opened, so the model cannot use the tool to probe.

Redirects are the hole an allowlist usually has, so the rule is the browser
connector's: redirects are followed only while every hop stays inside the
allowlist, up to a hard maximum of three hops, and a redirect leaving it halts
the request and returns `HTTP_REDIRECT_NOT_ALLOWED` naming the origin it tried
to reach. A relative redirect resolves against the current URL and is checked
the same way.

Scheme and destination posture:

- Only `http` and `https` are accepted; anything else (`file`, `ftp`, `gopher`,
  `data`) is `HTTP_SCHEME_NOT_ALLOWED`.
- URL userinfo is rejected outright (`HTTP_SCHEME_NOT_ALLOWED` is too blunt for
  this, so it is `INVALID_PARAMETERS` with an explicit message): a credential
  in `scheme://user:pass@host` is a literal secret in a model-supplied
  argument, and R-4 exists precisely so that never happens.
- Loopback, link-local (including the cloud metadata address `169.254.169.254`)
  and multicast hosts are refused even if an operator lists them, because an
  allowlist entry is not a considered decision to reach the node's own
  metadata service. Private-range and cluster-DNS hostnames are **not**
  refused — `http://acme-admin:8080` is the intended shape in-cluster.

Known limit, recorded rather than closed: the allowlist compares the origin
*string*, so a hostname that resolves to an unexpected address is not caught.
Resolution-time pinning (resolve, check the IP, connect to that IP) is out of
scope — see Non-Goals.

Acceptance criteria:

- An empty allowlist denies every URL with `HTTP_ORIGIN_NOT_ALLOWED` and opens
  no connection (asserted with a transport double that fails the test if
  called).
- A listed origin is allowed; the same origin with a different port is denied.
- A three-hop redirect chain inside the allowlist succeeds; a chain whose
  second hop leaves it returns `HTTP_REDIRECT_NOT_ALLOWED` naming that origin.
- `file:///etc/passwd`, `http://user:pass@host/`, and
  `http://169.254.169.254/latest/meta-data/` are each refused with the code
  this requirement names for them, regardless of allowlist content.
- Denial is a `denied` result, not an exception, and carries the evidence
  envelope.

### R-3: `http.post` — a write-tier bounded JSON mutation

The connector registers `http.post(url, body?, credential_set?, timeout_ms?)`
at `risk_level="write"`, so the registry refuses to register it at all unless
`GATEWAY_MUTATING_TOOLS_ENABLED=true` (SPEC-021 R-1) and every invocation
additionally requires `tools:mutate` and parks for human confirmation.

Bounds, in the SPEC-021 spirit of one named object per invocation and no
selector or wildcard variants:

- **One URL per invocation.** No batching, no list-of-requests form, no
  fan-out parameter.
- `body` must be a JSON **object** whose values are scalars or one level of
  nested object/array of scalars; depth is capped at 2, key count at 32, and
  serialized size at `GATEWAY_HTTP_MAX_REQUEST_BYTES` (default 4096). A body
  that exceeds any bound is `HTTP_BODY_TOO_LARGE` or `INVALID_PARAMETERS`
  **before** the request is made. Arbitrary-depth JSON is refused because it
  cannot be projected onto an approval card legibly (R-5), and a card an
  approver cannot read is not a gate.
- `content-type` is always `application/json`. There is no parameter to change
  it: form-encoded, multipart and XML bodies are out of scope.
- **A POST URL may not carry a secret-vocabulary query parameter.** A URL whose
  query contains any key matching the secret vocabulary is refused with
  `HTTP_URL_SECRET_NOT_ALLOWED`. This is what makes R-5's decision to treat
  `http.post.url` as known-safe sound: a payload belongs in the body, and a
  secret in a POST URL would land in upstream access logs, proxies and the
  durable record. The GET surface keeps the opposite rule — a secret-bearing
  query is *permitted* (the browser walkthroughs' `?newpw=` convention depends
  on it) but *masked* everywhere it is reported (R-6).
- The same allowlist, scheme, redirect and destination rules as R-2 apply
  unchanged; they live in the connector, not in the tool, so a future verb
  inherits them without a re-implementation.

The response is projected exactly as R-1 projects one, and the same
"an upstream 4xx/5xx is a fact, not a tool error" rule applies — with one
addition: a non-2xx response to a POST is reported with `data.status` and a
`data.mutation_confirmed: false` marker so a skill cannot read a rejection as
a success.

Acceptance criteria:

- With `GATEWAY_MUTATING_TOOLS_ENABLED=false`, `http.post` is absent from
  discovery and invoking it returns `TOOL_NOT_FOUND` — the existing registry
  behaviour, asserted for this tool.
- With the flag on, `http.post` requires `tools:mutate`: an identity holding
  only `tools:invoke` is denied, and the denial carries `risk_level="write"`
  in its evidence (the SPEC-021 honest-envelope rule).
- A body of depth 3, of 33 keys, or over the byte cap is refused before any
  request is made (transport double not called).
- `http.post("http://allowed/x?newpw=hunter2")` is refused with
  `HTTP_URL_SECRET_NOT_ALLOWED`, while `http.get` on the same URL succeeds and
  reports the value masked.
- An approved invocation executes under the confirmer's delegated token and
  produces a signed execution envelope with an `args_digest` over the raw
  parameters (SPEC-037) — asserted, since this is the first non-browser tool
  to carry a structured body through that path.
- A 409 response yields `status: "success"`, `data.status == 409` and
  `data.mutation_confirmed == false`.

### R-4: Credentials enter by reference only, never as an argument

`http.post` and `http.get` accept an optional `credential_set` **name**, which
the gateway resolves at call time from the same secret-mounted JSON file the
browser connector uses, through the existing
[`CredentialSetStore`](../../../products/tool-gateway/src/tool_gateway/tools/credential_sets.py)
— lazy, mtime-refreshed, path-only configuration, unknown names a structured
error rather than a crash. The resolved pair becomes an HTTP Basic
`Authorization` header on the outgoing request. `GATEWAY_HTTP_CREDENTIAL_SETS`
defaults to the browser path so one mounted secret serves both surfaces, and
can be pointed elsewhere independently.

The value never appears in a parameter, a result, an evidence frame, a log or
an audit event; only the set **name** does, exactly as `web.fill_credential`
behaves (SPEC-049 R-5). An unknown or unconfigured set returns
`CREDENTIAL_SET_NOT_FOUND` — the browser connector's existing code, reused so
both surfaces report identically.

There is deliberately **no** `headers` parameter on either tool. A free-form
header map is how an `Authorization` value ends up as a model-supplied literal
in a durable record, and every header this spec needs is either fixed
(`content-type`) or reference-resolved (`authorization`). A future verb that
genuinely needs a caller-chosen header should add a *named* parameter for it,
not a map.

Acceptance criteria:

- `credential_set: "acme-admin"` produces an outgoing Basic auth header whose
  value never appears in the tool result, the evidence envelope, the
  confirmation card, the durable record, or gateway logs (asserted on each
  surface, mirroring the SPEC-049 R-5 tests).
- An unknown set name yields `CREDENTIAL_SET_NOT_FOUND`; an unconfigured store
  yields the same code with a distinct message.
- Rotating the secret file changes the value used with no gateway restart
  (the store's mtime reload, asserted once for the HTTP path).
- Neither tool's `parameters_schema` contains a `headers` property.

### R-5: The `http.post` approval card, and one deliberate masking divergence

An `http.post` parks one `approval_kind: "action"` card with no new
enforcement machinery: [`runtime_kernel.py:1251`](../../../products/agent-platform/src/agent_service/runtime_kernel.py)
already derives `action` for any non-browser write, which is the path
`k8s.delete_pod` has exercised since SPEC-021. That card already carries
SPEC-054 R-3's `change_request` projection as a sibling of `parameters` (so
the signed `args_digest` is byte-identical with and without it) and SPEC-055
R-7's fail-closed redaction of the raw sibling.

Left uncurated, though, the card is **useless**: `build_change_request` falls
through to `_generic_fields`, which masks every parameter not positively
listed in `KNOWN_SAFE_FIELDS`, so the approver would see `Confirm http.post`
with `url: ***` and `body: ***`. An approval gate that will not say what it is
approving is approval theatre, and it would be worse than no gate because it
manufactures a record of a considered decision. So this spec adds a curated
`_cr_http_post` formatter to `_CHANGE_REQUEST_FORMATTERS`, alongside the
eight that exist today.

The formatter's effect sentence names the target and the field names —
`POST to http://acme-admin:8080/api/users/alice/lock — 1 field: locked` — and
its fields render:

- `url` **verbatim, through R-6's query masking** (a no-op here, since R-3
  already refuses a secret-bearing POST URL — the masking stays as defence in
  depth);
- `body` **shape-preserving**: keys visible at both levels, secret-named
  values masked wholesale, other scalar values rendered;
- `credential_set` as the reference name, never a value.

**The divergence, stated plainly.** Rendering non-secret-named body values is
a relaxation of SPEC-055 R-7's fail-closed posture, under which an
off-vocabulary, generically-named secret would project as plaintext. This spec
accepts that residual risk for `http.post.body` on one structural argument,
which is the same argument the codebase already makes for the browser:
[`secret_params.py`](../../../products/agent-platform/src/agent_service/services/secret_params.py)
records that "the structural control is … credentials enter through
`web.fill_credential` as a reference, never as a literal". R-4 makes that
literally true for HTTP — there is no `headers` parameter and no way to pass a
credential as an argument — so a credential cannot be in the body by
construction, and a body value is a payload fact the approver needs
(`locked: true` versus `locked: false` is the entire decision). The relaxation
is bounded to `http.post.body` and to scalar values at depth ≤ 2, which R-3
enforces before the request.

Concretely, then:

- `KNOWN_SAFE_FIELDS` gains **`http.post.url` only**. It does **not** gain
  `http.post.body`, so the raw `parameters` sibling still masks the body to
  `***` while the curated projection renders it — the intended asymmetry, and
  the same one SPEC-055 R-7 documents when it calls the raw sibling
  "redundant".
- `OPAQUE_VALUE_FIELDS` does **not** gain `http.post.body`. That list exists
  for fields where a secret is invisible to name matching (`web.type.text`,
  `web.evaluate.expression`). A JSON body's keys *are* visible, and
  `parameterize_for_trace` already descends through `_parameterize_nested`, so
  a nested `{"password": "…"}` becomes `<credential-reference>` in an
  authoring trace while `{"locked": true}` survives and stays replayable.
  Marking the whole body opaque would make every HTTP-mutating skill
  un-graduable, which is the exact cost that file's own docstring warns
  against.

Acceptance criteria:

- A parked `http.post` card carries `approval_kind: "action"`, a
  `change_request` whose `summary` names the origin, path and body key names,
  and no `flow_summary`.
- `{"locked": true}` renders on the card; `{"password": "hunter2"}` renders as
  `password: ***`; `{"user": {"password": "hunter2"}}` renders the nested key
  masked.
- The raw `parameters` sibling on the same frame shows `body: "***"` and the
  URL verbatim, and the signed `args_digest` is byte-identical to a run with
  the projection disabled.
- An uncurated-tool regression guard still passes: a write tool with no
  formatter gets the generic masked projection (this spec must not change that
  fallback).
- `make validate-secret-vocabulary` passes with the R-6 extraction change in
  place.

### R-6: URL secret-masking becomes a shared gateway helper

`_redact_secret_query` and its `_SECRET_QUERY_PARAMS` vocabulary currently live
inside
[`browser_connector.py:196`](../../../products/tool-gateway/src/tool_gateway/tools/browser_connector.py),
and the kernel keeps a deliberate twin in `secret_params.py`. Two connectors
now need the gateway side, so the function and the vocabulary move to a new
`products/tool-gateway/src/tool_gateway/tools/url_redaction.py`, with
`browser_connector` importing from it. Behaviour is unchanged byte-for-byte;
this is a move, not a rewrite, and the kernel twin stays where it is.

**The consequence that must not be missed:** `make validate-secret-vocabulary`
extracts the gateway copy **textually, by hardcoded path and variable name**
([`validate_secret_vocabulary.py:61-62`](../../../shared/shared-contracts/scripts/validate_secret_vocabulary.py)
— `TOOL_GATEWAY_REL`, `TOOL_GATEWAY_VAR`), and treats an extraction failure as
a build failure. The move and the validator's path constant are therefore one
atomic change; splitting them across commits breaks `make verify` in between.
The validator diffs the two copies **as sets**, so the kernel twin continues to
match unchanged.

Acceptance criteria:

- `browser_connector` contains no local definition of `_redact_secret_query`
  or `_SECRET_QUERY_PARAMS` and imports both; every existing browser test
  passes unmodified.
- `validate_secret_vocabulary.py`'s `TOOL_GATEWAY_REL` points at
  `tools/url_redaction.py` and `make validate-secret-vocabulary` exits 0.
- Adding a term to one copy and not the other still fails the build (the leg's
  whole purpose, re-asserted after the move).
- `http.get` on a URL carrying `?newpw=hunter2` reports
  `?newpw=***` in `data.url` while the request actually sent carries the real
  value.

### R-7: Configuration, wiring, and activation documentation

`GatewaySettings` gains, following the existing `GATEWAY_<CONNECTOR>_*`
convention and never defaulting a secret:

- `GATEWAY_HTTP_ENABLED` (bool, default `false`) — the connector's master
  switch, matching `GATEWAY_BROWSER_ENABLED`.
- `GATEWAY_HTTP_ALLOW_ORIGINS` (comma-separated, default empty = deny all).
- `GATEWAY_HTTP_TIMEOUT_MS` (default 10000, max 30000).
- `GATEWAY_HTTP_MAX_RESPONSE_BYTES` (default 65536).
- `GATEWAY_HTTP_MAX_REQUEST_BYTES` (default 4096).
- `GATEWAY_HTTP_CREDENTIAL_SETS` (path; defaults to the browser credential-sets
  path when unset).

Wiring follows the guide's §5 pattern: a gated block in `_build_tool_registry()`
with the import inside the branch, gated on the boolean flag (not URL-presence,
because unlike `cmdb.lookup` this connector has no single upstream URL — the
allowlist is the bound). `register_tools` registers `http.get` always and
`http.post` unconditionally too, letting the registry's own risk-tier admission
refuse it when mutating tools are off — the same division of labour
`k8s_connector` uses, so the flag semantics stay in one place.

[`dev-k8s/base/tool-gateway/runtime-config.env`](../../../shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env)
gains `GATEWAY_HTTP_ENABLED=false` plus commented examples for every other
variable, and an activation block in the same voice as the two already there,
naming all four preconditions: the flag, a non-empty allowlist,
`GATEWAY_MUTATING_TOOLS_ENABLED=true` for `http.post`, and
`AGENT_HITL_CONFIRM_TIMEOUT>0` on agent-platform. The base names no origin —
SPEC-050 R-11's rule that the base overlay never names a sample applies to
allowlist entries exactly as it does to Deployments, so `acme-admin`'s origin
goes into the `browser-dev` runtime profile in SPEC-059.

[`docs/guides/tool-configuration.md`](../../guides/tool-configuration.md)
gains an **HTTP Connector Tools** table in the same four-column shape as the
other five, an **HTTP Tool Activation Checklist** beside the browser one, and
the new error codes. [`docs/guides/adding-a-tool.md`](../../guides/adding-a-tool.md)
gains one sentence noting that its worked example is the config-base-URL shape
and that `http.*` is the model-supplied-URL shape, pointing at this spec —
because the next contributor to read that guide will otherwise assume the
example covers both.

Acceptance criteria:

- With no `GATEWAY_HTTP_*` variable set, no `http.*` tool is registered, the
  gateway starts cleanly, and discovery is unchanged from today.
- `make overlays` renders `dev-k8s` and all three runtime profiles with the new
  base keys present.
- The rendered base config carries `GATEWAY_HTTP_ENABLED=false` and no origin.
- Both guides render, list all new error codes, and the tool table's risk
  column reads `read` for `http.get` and `write` for `http.post`.

### R-8: Tests and delivery traceability per ADR-0008

Every requirement above maps to a named test, per ADR-0008's traceability
gate, and deny and error paths are not optional per CONTRIBUTING. The suite
lives at `products/tool-gateway/tests/test_http_connector.py`, modelled on
`test_skills_connector.py`'s `FakeResponse` double patched over the connector's
single transport seam — which is why R-3 keeps the request in one connector
helper rather than spreading `httpx` calls through the tool classes.

Minimum coverage: parameter validation including the URL-interpolation guard
with a hostile value (`"../../admin"`, `"http://allowed@evil/"`); every
allowlist denial and both redirect outcomes; the scheme, userinfo and
destination refusals; the body bounds; timeout and transport failure; the
upstream-status-is-a-fact rule for both verbs; the header allowlist with a
`set-cookie` present; truncation; credential resolution and its
never-echoed assertions on every surface; registration present/absent on the
flag; and, kernel-side, the `_cr_http_post` projection including the
digest-invariance assertion.

The `make verify` legs this slice touches: `test`, `validate-policy` (must
still pass with **no bundle change** — that is the assertion),
`validate-secret-vocabulary` (R-6). Because SPEC-059's demo scripts exercise
these tools against a live cluster, ADR-0008's exercised-sample half is
satisfied there rather than here; this spec's own demonstration is a
`shared/platform-ops/e2e/http-check-demo.sh` that asserts registration,
allowlist denial, a live `http.get` against the deployed target, and one
parked-and-approved `http.post`.

Acceptance criteria:

- `make -C products/tool-gateway test` passes with the new suite, and every
  R-1…R-7 acceptance criterion has a test that fails when the behaviour is
  removed (spot-checked by mutation on the three security-critical ones:
  allowlist denial, `set-cookie` suppression, credential non-echo).
- `make verify` passes, including `validate-policy` with an unmodified bundle.
- `make e2e` runs the new demo script to a green `E2E_OK`, and the script is
  added to the `e2e` target's explicit list at
  [`Makefile:196-199`](../../../Makefile) — that loop is hardcoded, so a new
  script does not join it by existing.
- `docs/specs/SPEC-058-*/tasks.md` records the requirement-to-test mapping.

## Non-Goals

- **`http.head`, `http.put`, `http.patch`, `http.delete`.** `http.get` already
  returns status, projected headers and elapsed time, so HEAD adds an
  LLM tool-selection decision and teaches nothing. PUT/PATCH/DELETE belong
  with POST's trust conversation and can join it later without reshaping the
  connector, since R-2/R-3's bounds live there.
- **Named targets instead of URLs** (`GATEWAY_HTTP_TARGETS=acme=http://…`, tool
  takes `target` + `path`). This is the safer shape — SSRF-proof by
  construction, and it is the `cmdb.lookup` idiom — and it was **considered and
  rejected**: it requires a config entry per service, which does not survive
  contact with an operator who wants to check forty endpoints, and the target
  discipline it would provide is already carried at the skill layer by
  `web_target` and SPEC-055 R-4's blast-radius re-validation. The allowlist
  bounds the origin, which is the part that is a platform responsibility.
- **Resolution-time address pinning** (resolve, validate the IP, connect to
  that IP). R-2's known limit. It needs a custom transport and a decision about
  DNS TTLs, and the allowlist already reduces the exposure to "a hostname an
  operator explicitly listed resolves somewhere unexpected".
- **Non-JSON request bodies**, file upload or download, response streaming,
  retries, caching, cookies/jar state, and per-request TLS configuration.
- **A `headers` parameter** — see R-4 for why this is a decision and not an
  omission.
- **Any policy bundle change.** `tools:invoke` and `tools:mutate` already cover
  both tiers; adding a per-tool action would be the first in the platform and
  is not this slice's fight.
- **Any new audit event type.** `tool_invoked` and `policy_decision` already
  fire for every invocation with the acting identity.
- **Cross-origin discipline against a bound browser flow.** Whether an
  `http.get` to an origin other than the session's declared `web_target` should
  be denied — the HTTP analog of SPEC-055 R-4 — is a real question and is
  deferred to Open Questions rather than silently decided, because it couples
  this connector to browser flow state.

## Impact

- products touched: `products/tool-gateway` (new `tools/http_connector.py`, new
  `tools/url_redaction.py` extracted from `browser_connector.py`, `core/config.py`,
  `app.py`, `tests/test_http_connector.py`); `products/agent-platform`
  (`services/hitl_confirmations.py` — one curated formatter;
  `services/secret_params.py` — one `KNOWN_SAFE_FIELDS` entry; tests for both).
- shared touched: `shared/shared-contracts/scripts/validate_secret_vocabulary.py`
  (path constant, R-6); `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`;
  `shared/platform-ops/gitops/runtime-profiles/browser-dev/` (profile entries
  land in SPEC-059, not here); `shared/platform-ops/e2e/http-check-demo.sh`.
- contracts touched: **none**. `tool-result.schema.json` is a generic envelope
  and `data` is free-form; `agent-stream-event.schema.json` already carries
  `change_request` and `approval_kind`. No schema version bump.
- identity / policy / audit / execution safety impact: **no new policy action,
  no new audit event type, no bundle edit.** `http.post` is write tier, so it
  inherits `tools:mutate`, the `GATEWAY_MUTATING_TOOLS_ENABLED` admission gate,
  tier_2 two-person approval under SPEC-030 R-4, and a SPEC-037 signed
  envelope per execution. The new attack surface is model-supplied URLs, and
  R-2 is the control: deny-by-default origin allowlist, redirect halt, scheme
  and destination refusals, all enforced server-side before a socket opens.
  The new secret surface is a POST body, and R-4/R-5 are the control: no
  `headers` parameter, credentials by reference only, secret-bearing POST URLs
  refused, and a card that names the target and fields.
- living state docs to update on delivery: `docs/guides/tool-configuration.md`
  (tool inventory, activation checklist, error codes),
  `docs/guides/adding-a-tool.md` (the two tool shapes),
  `docs/guides/configuration-reference.md` (the six new variables),
  `docs/specs/README.md` (this row → `delivered`),
  `docs/agentic-aiops-platform/delivery-roadmap.md` (slice row),
  `CHANGELOG.md`, `VERSION`.

## Open Questions

All four were resolved at approval on 2026-09-17, adopting the recommendation
recorded in the draft in every case. The original options are retained so the
decision stays auditable; from here a requirement changes only by agreement,
recorded in the changelog (the `approved`-spec rule).

- **OQ-1 — version slot.** SPEC-057 was `approved` targeting v0.38.0. This slice
  and SPEC-059 are intended to land first, because SPEC-057's compositions need
  a repertoire of single-target skills to compose and SPEC-059 is what supplies
  it. Does SPEC-058 take v0.38.0 and SPEC-057 move to v0.40.0 (with SPEC-059 at
  v0.39.0), or do the three ship as one release? **Resolved: 058 → v0.38.0,
  059 → v0.39.0, 057 → v0.40.0**, since each is independently demoable and the
  platform has shipped one slice per release throughout R5.
- **OQ-2 — cross-origin discipline.** Should `http.get`/`http.post` be denied
  when a browser flow is bound to a different origin (the HTTP analog of
  SPEC-055 R-4's deviation guard)? For: it makes the single-target property
  hold across both surfaces, which is exactly what SPEC-057 compositions will
  lean on. Against: it couples a stateless connector to browser session state,
  and a legitimate runbook may check a dependency service while operating on a
  target. **Resolved: no** in this slice; revisit with evidence from
  SPEC-059's skills, and the decision is recorded here so it is not
  re-litigated.
- **OQ-3 — does `http.get` need `credential_set` too?** R-4 gives it to both
  tools. A read-only authenticated status endpoint is common, but so is an
  unauthenticated `/healthz`, and every authenticated GET widens the surface
  where a Basic credential is sent to an allowlisted origin. **Resolved: keep
  it on both**, since the allowlist is the same and the value never appears in
  a result either way.
- **OQ-4 — one connector or two?** `http.get` and `http.post` share the
  allowlist, transport, projection and credential machinery, so one
  `http_connector.py` with two tool classes is the obvious shape. It is named
  here only because a reviewer may reasonably ask whether the write-tier tool
  should live in its own module for auditability. **Resolved: one module**,
  matching `k8s_connector.py`, which ships four read tools and one write tool
  together.

## Changelog

- 2026-09-17: created as `draft` from the 2026-09-17 walkthrough-enrichment
  design discussion, with `http.post` folded in on the operator's decision
  against the drafting recommendation to defer it — a decision the drafting
  verified as sound once `runtime_kernel.py:1251` was found to already derive
  `approval_kind: "action"` for non-browser write tools.
- 2026-09-17: approved by the operator with all four open questions resolved as
  recommended. Version slots settled at 058 → v0.38.0, 059 → v0.39.0 and
  SPEC-057 → v0.40.0, so this slice lands first; `docs/specs/README.md`, the
  delivery roadmap and SPEC-057's own release-slice line move in the same
  change.
- 2026-09-17: delivered in **v0.38.0** with the full `make verify` gate green
  (2679 product tests, four kustomize overlays, 18 policy rules, 137 + 19
  policy scenarios, version lockstep and the three secret-vocabulary checks),
  deployed to dev-k8s and exercised end to end: the deterministic
  `demo-suite.sh` (all four rungs plus the cross-skill verification), the
  opt-in chat legs asserting the 0 / 0 / 1 / 1 card counts, `make e2e`, and a
  live browser pass over each walkthrough. Running the rungs surfaced one real
  gap this slice owns — `http.get` was absent from the kernel's read-tier
  auto-allow list, so a card-free read skill still parked a card — fixed in the
  kernel rather than worked around in the sample. SPEC-059 ships in the same
  release, collapsing its OQ-5 v0.39.0 slot (and OQ-1's 059 → v0.39.0 above).
- 2026-09-17: pre-release review tightens R-2/R-3: **only GET follows
  redirects** under the three-hop allowlist rule; POST returns
  `HTTP_REDIRECT_NOT_ALLOWED` without following any 301/302/303/307/308.
  This supersedes R-3's original identical-redirect-rule wording: a write may
  not move to a path the approver never saw. The initial POST may already
  have changed state, so a refusal is not a rollback or permission to retry.
  R-1's projected `location` header also receives R-6 query masking, like
  `url`. Both review fixes are pinned by connector regression tests.
