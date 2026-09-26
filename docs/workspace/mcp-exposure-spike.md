# Spike: Independent MCP Toolsets — Use Cases, Adoption, and Extraction

Status: assessment complete — recommend retaining native connectors; MCP adoption or extraction is trigger-gated, not approved for implementation
Date: 2026-09-23
Roadmap home: [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog), "Independent MCP toolsets consumed by tool-gateway"
Evidence baseline: repository at 0.42.0 (`bd756e9`); static code/manifests inspection and upstream documentation accessed 2026-09-23. No candidate server was installed, tested, or deployed.

This assessment supersedes the initial read-tier tool-gateway exposure proposal.
The filename is retained for continuity; neither an implementation spec nor an
ADR is being promoted or assigned a number.

## 1. Question and recommendation

> Would independently deployable toolsets, consumed through tool-gateway,
> deliver enough practical value to justify the additional complexity?

Luban's current product focus is self-contained, human-led AI-assisted operations.
Three different concerns must not be conflated:

- **External access to Luban workflows:** another application asks Luban to
  perform work under Luban's governance. No concrete consumer or workflow has
  been established; this is a separate product decision, not this spike's goal.
- **Luban consuming MCP tools:** an optional connector implementation beneath
  tool-gateway, preserving Luban's policy, approvals, and operator experience.
- **Reusable independent toolsets:** other systems may consume the same server
  implementation under their own governance. They need not share Luban's
  deployment, credentials, production resources, or approval state.

Recommendation: **no-go on implementation or extraction now; retain native
connectors.** Kubernetes is the best first candidate if a concrete need emerges.
Evaluate an existing server before owning a new one; extract Luban's Kubernetes
operations only if a documented adoption gap justifies that ownership. This is
not a rejection of MCP, nor a requirement that independent servers be read-only.

## 2. Use cases and evidence of need

| Use case | What is established | What would justify changing the implementation |
|---|---|---|
| Current Luban Kubernetes operations | Five native operations already exist; the shipped gateway deployment uses its Kubernetes service account. | No missing transport capability has been demonstrated for this workflow. Keep native. |
| Independent connector releases | Kubernetes and Elastic client dependencies are packaged with tool-gateway; platform versions follow a coordinated release train. Product-level image builds also exist. | A connector owner identifies recurring release delays or dependency conflicts, with examples and a target improvement. Separate server maintenance must cost less than the current friction. |
| Credential-local execution near restricted infrastructure | The native connector loads in-cluster credentials or a local kubeconfig. The supplied requirements do not identify a restricted remote cluster. | A named target forbids credentials or direct API access from Luban but permits an authenticated, bounded MCP endpoint. Confirm network direction, data-egress rules, and endpoint ownership; MCP does not bypass a firewall or an air gap. |
| Reuse by a second system | The user identified reuse as a possible architectural benefit; no second consumer and required operation set have been named. | A consumer commits to a concrete workflow and contract. Separate instances and least-privilege credentials are the starting point, not a shared production endpoint. |
| New operational capabilities | Existing tools are intentionally narrow. Upstream servers advertise much broader functionality. | An operator identifies a missing task and acceptance criteria. Admit only the required operations; a large catalog is not itself a use case. |

The unvalidated items are unknowns, not evidence that the needs cannot exist.
Independent deployment may serve Luban alone; a second consumer is not mandatory
if credential locality or release independence provides sufficient value. None
of these benefits has yet been measured, and none establishes completion of R5.

## 3. Verified implementation boundaries

### 3.1 Existing extension seam and governance

- Tool discovery and invocation use REST (`/api/v2/tools` and
  `/api/v2/tools/invoke`). No configured MCP server or MCP-backed gateway
  connector was found in the inspected implementation. The `mcp` package in
  AgentScope's lockfile is a transitive dependency, not evidence of integration.
- [BaseTool and ToolDefinition](../../products/tool-gateway/src/tool_gateway/tools/base.py)
  provide the adapter seam: a local definition plus
  `execute(parameters, identity) -> ToolResult`. Native and MCP-backed
  implementations could coexist without making the agent an independent MCP
  client that bypasses tool-gateway.
- The [HTTP routes](../../products/tool-gateway/src/tool_gateway/api/routes/tools.py)
  resolve verified identity before the
  [invocation service](../../products/tool-gateway/src/tool_gateway/services/gateway_service.py).
  Invocation evaluates `tools:invoke`, additionally `tools:mutate` for non-read
  tools, and any `extra_required_actions`; it dispatches through the registry,
  redacts results, and emits `tool_invoked`. Audit delivery is fire-and-forget
  with log fallback, not a transactional durability guarantee.
- [GatewayPermissionMiddleware](../../products/agent-platform/src/agent_service/services/kernel_middleware.py)
  auto-allows gateway tools only when both read-only and explicitly vetted.
  Unvetted reads can require confirmation. Mutations use Luban's approval and
  signed-execution path; approved browser flows have a tightly scoped exception.
  The gateway's role checks do not themselves verify the signed handoff.
- [execution-runtime](../../products/execution-runtime/src/execution_runtime/services/executor.py)
  calls tool-gateway after the approved handoff. An MCP-backed mutation must
  remain beneath this path, not replace it. Browser binding and deviation guards
  also exist in tool-gateway; browser authority is not exclusively kernel-local.

### 3.2 Kubernetes: good separation candidate, not a demonstrated need

The [native connector](../../products/tool-gateway/src/tool_gateway/tools/k8s_connector.py)
contains four reads and one exact-name pod deletion. It uses the official Python
client with in-cluster configuration first, kubeconfig fallback, and a single
client configuration rather than per-call user impersonation or cluster selection.
The `identity` argument does not select Kubernetes credentials.

Namespace resolution is `parameters.get("namespace") or default_namespace`.
That is a default, **not an authorization boundary**. The
[base RBAC](../../shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml)
grants cluster-wide reads on selected resources. The separate
[mutating profile Role](../../shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml)
grants pod deletion only in `dev-luban-aiops`. The
[deployment](../../shared/platform-ops/gitops/dev-k8s/base/tool-gateway/tool-gateway-deployment.yaml)
uses the `tool-gateway` service account. These are manifest findings, not a
fresh inspection of live cluster permissions.

The [gateway dependency set](../../products/tool-gateway/pyproject.toml) includes
Kubernetes and Elasticsearch clients. The [root Makefile](../../Makefile) owns
coordinated version/build routines, while [product image routines](../../mk/image.mk)
also support separate builds. Extraction could separate release ownership, but
there is no measured release bottleneck in the evidence collected here.

### 3.3 Do not extract every connector

| Connector | Assessment |
|---|---|
| Kubernetes | First candidate: domain operations can be separated from Luban admission and result normalization. |
| Elasticsearch | Possible later candidate; current queries and projections assume specific observability fields and alert schemas, so reuse is not automatic. |
| Browser | Defer: session state, skill-bound flows, credential filling, and deviation guards are coupled to Luban semantics. Extracting browser mechanics requires a separate boundary study. |
| Skills and incidents | Keep native: these primarily wrap Luban-owned services, not independent infrastructure toolsets. |
| Secret generation and delivery | Defer: read-tier generation deliberately passes a generated secret to kernel masking; delivery includes owner-scoped redemption and portal behavior. Gateway redaction alone is not the complete secrecy contract. |

## 4. Native, adopted, or extracted implementation

| Option | Benefit | Cost and limitation | Recommendation |
|---|---|---|---|
| Keep native connectors | Known contracts and deployment; no extra process, protocol, or network boundary. | Connector dependencies and lifecycle remain in tool-gateway; direct target access remains necessary. | Default now. Modular domain code or a shared library may suffice if only code reuse is needed. |
| Adopt an existing MCP server | Reuse domain coverage and independent packaging; potentially deploy beside the target. | Own the Luban adapter, server admission/auth configuration, compatibility tests, upgrades, monitoring, and another failure boundary. | First option to evaluate after a use-case trigger. Not a drop-in replacement. |
| Extract a standalone Kubernetes server | Control a narrow contract and preserve curated behavior; reusable outside Luban without importing approval state. | Own server lifecycle, MCP compatibility, security patches, releases, client-library dependencies, and two-sided integration tests. | Only after a specific adoption gap outweighs these costs. |

If extraction becomes justified, separate Kubernetes operations and a neutral
server contract from Luban's `ToolDefinition`, policy actions, identity tokens,
and audit-envelope adapter. Do not move the entire gateway into another process.
Independent toolset ownership and versioning matter more than immediately
creating another repository; repository placement is a later delivery decision.

### 4.1 Existing candidates: documentation-level comparison

[containers/kubernetes-mcp-server](https://github.com/containers/kubernetes-mcp-server)
is the preferred candidate for a future compatibility evaluation, not a selected
dependency. Its documentation describes direct Go Kubernetes API calls, binary
and container distribution, stdio and Streamable HTTP, per-tool allowlisting,
and counterparts for all five native operations. Important qualifications:

- Its default `config` and `core` toolsets are broader than Luban's contract.
  `enabled_tools` can restrict the server; the adapter must separately admit only
  local, reviewed definitions. Exclude configuration viewing, generic CRUD,
  exec/run, Helm, and other unrequested capabilities.
- `read_only` defaults to false and filters by remote tool annotations when
  enabled. Neither this flag nor `readOnlyHint` substitutes for Luban's local
  risk classification or target RBAC.
- Lists default to table output, with YAML as another documented format.
  Machine-readable output sufficient for Luban's projections must be verified;
  the existence of MCP `structuredContent` does not prove this server supplies it.
- HTTP OAuth is opt-in. The documented `cluster_auth_mode` defaults to
  `passthrough`, forwarding a bearer token when present; a separate skip-validation
  mode also exists. Those defaults/modes are not acceptable for the proposed
  Luban boundary. Evaluate authenticated, audience-checked MCP access plus
  `cluster_auth_mode="kubeconfig"` with dedicated target credentials, or a
  separately designed token exchange. Verify actual behavior in a pinned release.
- Optional server confirmation rules are not Luban HITL. Their documented
  fallback when elicitation is unsupported defaults to `allow`; never rely on
  that mechanism to enforce Luban approval.

[Azure/mcp-kubernetes](https://github.com/Azure/mcp-kubernetes) documents a released
binary run as a stdio subprocess, no supported container images, and a unified
`call_kubectl(command)` interface by default. It offers access levels, namespace
restrictions, and optional legacy tools, but requires kubectl. A command-string
surface needs additional validation/translation to fit Luban's static per-tool
risk model; stdio alone does not provide remote credential-local deployment.
Keep it as a comparison, not the first remote-server candidate.

These observations come from moving upstream documentation, not source audits,
benchmark results, or conformance tests. No release, license suitability, support
commitment, artifact provenance, or image digest has been approved. Adoption
requires those checks even if the operation names match.

## 5. Conditional ownership and trust boundary

Proposed direction only; no MCP adapter exists as a result of this assessment:

```text
Luban users -> agent-platform policy / HITL
                 -> existing signed execution + execution-runtime for mutations
                 -> tool-gateway admission, dispatch, redaction, audit
                      -> native connector -> target
                      -> MCP adapter -> independent tool server -> target

Other system -> its own policy / approval -> its MCP client
                 -> independently configured tool-server instance -> target
```

| Owner | Responsibility |
|---|---|
| Luban | User authorization, local risk classification, approval decisions, signed arguments, worker dispatch, operator evidence, and decision-to-execution audit correlation. |
| Gateway adapter | Explicit tool admission, canonical names/schemas, deterministic translation, endpoint/target selection, server authentication, deadlines, response validation, normalization, and error mapping. |
| Independent server | Authenticate callers, authorize tools/resources, isolate credentials, validate inputs, bound execution/output, and record executions. It need not know Luban cards, sessions, or policy vocabulary. |
| Target system | Independently enforce Kubernetes RBAC or equivalent resource permissions. |
| Each consumer | Govern its own use and provision its own permissions; sharing implementation grants no access to Luban resources. |

Effective authority is the intersection of consumer admission and server/target
permissions. A caller-provided `approved=true`, session ID, or correlation ID
must not expand server authority. An independent server can offer reads and
mutations; Luban decides which operations to admit and approve for its users.

[ADR-0004](../adr/0004-broker-mediated-token-delegation.md) binds delegated tokens
to `aud=tool-gateway`, with user `sub` and service `act`. Do not forward that token
to an independent MCP server or on to Kubernetes. HTTP server access requires
its own authenticated audience/credential relationship, separate from target
credentials. The [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
requires intended-audience validation and prohibits token passthrough to upstream
APIs. Local stdio instead needs explicitly scoped process credentials and
lifecycle isolation; it does not remove the target-authorization obligation.

A private remote endpoint needs verified TLS, caller authentication, controlled
network reachability, Origin/Host protections as applicable, and isolated
health/metrics exposure. Endpoint URLs, executable paths, and credential sources
are operator configuration, never model-selected arguments. One dedicated target
identity can preserve today's service-account model, but is not per-user target
RBAC; document that limitation rather than implying identity delegation.

## 6. Kubernetes compatibility requirements for a future pilot

These are acceptance requirements to investigate, not claims of compatibility.
Keep canonical Luban names and local risk tiers. Do not import every remote tool
or use server descriptions/annotations as permission authority.

| Luban tool | Candidate counterpart in containers/kubernetes-mcp-server | Required translation and scope |
|---|---|---|
| `k8s.list_pods` (read) | `pods_list_in_namespace` | Resolve and pass namespace explicitly; map `label_selector` to `labelSelector`. Do not use all-namespace `pods_list`. |
| `k8s.get_pod` (read) | `pods_get` | Preserve required name; pass resolved namespace and pinned target. |
| `k8s.get_events` (read) | `events_list` | Map `field_selector` to `fieldSelector`; always pass resolved namespace because omission upstream means all namespaces. |
| `k8s.get_pod_logs` (read) | `pods_log` | Map `tail_lines` to `tail`; preserve native coercion/default 100/cap 1000 and below-1 errors, optional container, and current-log behavior. Do not add streaming or previous-log access implicitly. |
| `k8s.delete_pod` (write; later gate) | `pods_delete` | Preserve one exact name and resolved namespace; no selector, wildcard, bulk operation, or expanded target permission. |

Native pod results include phase, node, timestamps, labels, and container
readiness/restarts/state; detail adds conditions. Events and logs have their own
curated envelopes. Normalize to those contracts, including null/default behavior
and error codes, rather than returning raw Kubernetes resources or parsing a
human-oriented table. For pod/event resources, a pinned server must supply
sufficient structured JSON or safely parsed bounded YAML; logs may be bounded
text wrapped in the existing log envelope. Otherwise adoption fails this
compatibility gate. `ToolResult` status, evidence, output limits, and gateway
redaction remain local.

Additional invariants:

- **Pinned meaning:** one configured target/context and explicit namespaces;
  no automatic discovery of extra kubeconfig contexts. Record a versioned mapping
  of endpoint, target, schema, and implementation. Defaults/configuration changes
  must not redirect an already approved call; invalidate and reapprove when the
  execution meaning changes. This is future work, not a current signature claim.
- **Explicit admission:** fail closed on missing tools, incompatible schemas,
  name collisions, and unknown required arguments. Remote discovery changes must
  not silently add capabilities or replace a canonical implementation.
- **Untrusted results:** validate types and size before normalization; preserve
  redaction/overflow behavior. Do not automatically fetch returned resource links
  or let remote prompts, sampling, or elicitation introduce side effects. Admit
  only the capabilities the connector needs.
- **Errors:** distinguish JSON-RPC failures from tool results with `isError=true`;
  HTTP success is not tool success. Preserve authorization denial versus target
  API failure without exposing unredacted server errors.
- **Uncertain outcomes:** a disconnect or timeout after dispatch may follow a
  completed mutation. The current worker maps `TIMEOUT` to a timeout receipt;
  it does not establish that no change occurred. A mutation pilot must define
  how uncertainty is surfaced and reconciled. No blind retry or automatic native
  fallback after a possibly dispatched mutation. Current pod deletion supplies
  no UID precondition; any UID/idempotency design is an explicit contract change,
  not an assumed safety property of deletion by name.
- **Attribution:** retain Luban's verified user/service attribution and add an
  explicit remote execution correlation strategy. Test the actual headers and
  identifiers across worker, gateway, server, and target logs; do not assume
  existing request IDs automatically propagate. Remote logs supplement, not
  replace, Luban's approval/audit record. Never log credentials or raw secrets.

## 7. Go/no-go gates and next decision

**Now:** keep native connectors and park implementation. Correct the README's
unshipped MCP claim and reframe the backlog as consumption/selective extraction.
Do not expose tool-gateway, create a server, or promote an ADR/spec from this memo.

**Reopen when one concrete trigger from section 2 is recorded.** The sponsor
must identify the workflow, target/consumer, operational owner, current pain,
network/credential constraints, and a measurable success criterion. A selected
missing capability also requires reconsidering whether native extension is
cheaper. A standard protocol alone is not the success criterion.

If that gate is met, propose a separately approved Kubernetes pilot:

1. Pin an upstream release/artifact and inspect its license, provenance,
   authentication behavior, output schemas, and maintenance posture. Compare
   against the native baseline before choosing transport/deployment topology.
2. Start with the four existing reads in an isolated target and explicit tool
   allowlists. Preserve the current operator-facing contract. Keep pod deletion
   native and approval-gated during this stage. This staging limits pilot risk;
   it is not an architecture-wide prohibition on server mutations.
3. Require contract tests for all four tools, default/explicit namespace handling,
   selectors, log bounds, missing resources, denial, malformed/oversized/secret-
   shaped output, protocol errors, tool errors, timeout, and server unavailability.
   Prove missing/expired/wrong-audience credentials and out-of-scope resources are
   refused. Verify unadvertised/unadmitted operations cannot widen access.
4. Exercise the same Luban operator workflow and evidence/replay behavior. Prove
   correlation end to end and measure latency/error rate against native behavior.
   Before the pilot starts, its sponsor sets acceptable performance/operating-cost
   thresholds and the use-case-specific benefit target; do not invent a baseline.
5. Validate rollback by switching subsequent calls to the native implementation
   without widening permissions, changing tool names, or losing evidence. Pin
   routing/configuration while calls are in flight. Do not double-dispatch.
6. Consider remote pod deletion only under a separate approval after the read
   gate passes. Require unchanged HITL/signed-worker behavior, least-privilege
   target RBAC, rejection of altered approved arguments, uncertain-outcome handling,
   and denial tests proving no unauthorized target mutation occurs.

**Adopt** only if the selected benefit and compatibility/security gates pass
without substantial custom server behavior. **Extract** only if a named gap
cannot reasonably be resolved upstream and an owner accepts independent server
maintenance. **Stop and retain native** if the use case remains hypothetical,
the server requires authority widening, contracts cannot be preserved, or costs
outweigh the measured benefit. Failure of adoption is not automatic approval to
build a replacement.

## 8. Evidence and corrections to the initial proposal

Repository evidence is linked at the relevant findings above. Additional connector
boundaries were inspected in
[Elastic](../../products/tool-gateway/src/tool_gateway/tools/elastic_connector.py),
[browser](../../products/tool-gateway/src/tool_gateway/tools/browser_connector.py),
and [secrets](../../products/tool-gateway/src/tool_gateway/tools/secrets_connector.py).
Upstream references, accessed 2026-09-23:

- [containers Kubernetes MCP README](https://github.com/containers/kubernetes-mcp-server)
  and [configuration reference](https://github.com/containers/kubernetes-mcp-server/blob/main/docs/configuration.md):
  operation names, packaging, output formats, allowlists, authentication modes,
  and confirmation fallback. These are moving-branch documentation claims.
- [Azure Kubernetes MCP README](https://github.com/Azure/mcp-kubernetes/blob/main/README.md):
  stdio-only binary deployment, command interface, access levels, and namespace controls.
- [MCP tools specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools):
  structured content, optional output schemas, protocol versus tool errors, and
  client/server security responsibilities.
- [MCP authorization specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization):
  intended audiences and separate upstream credentials.

The initial proposal's conclusions are withdrawn: a transitive dependency does
not establish an MCP client integration; read-tier classification alone does not
preserve approval or secret masking; browser binding spans kernel and gateway;
gateway admission is not the complete approval chain; a namespace default is not
resource authorization; and audit emission is not guaranteed durable delivery.
MCP does not inherently make asynchronous approval integration impossible. An
external workflow service would require its own lifecycle and trust design if
that product use case were established. This assessment neither fulfills nor
redefines the broader R5 external-consumption goal.

## Changelog

- 2026-09-23, initial draft (superseded): proposed read-tier tool-gateway exposure
  and ADR/spec promotion before establishing a consumer use case.
- 2026-09-23, revised assessment: incorporated the user's product-boundary
  correction; compared native/adopted/extracted toolsets, inspected Kubernetes
  scope and upstream candidates, and recommended retaining native connectors
  until a concrete trigger justifies a separately approved pilot. No runtime
  implementation, deployment, or spec promotion is part of this assessment.
