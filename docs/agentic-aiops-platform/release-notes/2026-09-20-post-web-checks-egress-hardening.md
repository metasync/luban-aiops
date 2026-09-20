# Post-web-checks Egress Hardening: `http.get` becomes opt-in for HITL bypass (v0.39.1)

Date: 2026-09-20

A patch hardening the agent kernel's tool auto-allow posture after the v0.39.0
`web-checks` consolidation train. There is no contract, policy, schema, audit,
or database-migration change. One shipped-code change to the kernel's vetted
default, one new additive configuration variable, the matching dev-k8s overlay
opt-in, and the test and living-doc updates that keep the posture honest.

## How this batch differs from v0.39.0

v0.39.0 was a samples-and-docs consolidation train that deliberately changed no
product behaviour. This batch is written from an **L3 deep security review** of
that train, which surfaced a single medium-severity SSRF finding (CWE-918,
confidence 75) against the SPEC-058 R-1 entry that placed the outbound-egress
read `http.get` in the kernel's built-in `DEFAULT_AUTO_ALLOWED_TOOLS`.

The finding is **defence-in-depth, not a live vulnerability**, and it is worth
being precise about why, because the scanner's framing ("removing the human
approval card for agent-initiated outbound HTTP requests") reads as though the
card were the only thing standing between the model and the network. It is not.
The auto-allow list is a *human-in-the-loop bypass switch*, not an egress
control. The actual egress boundary lives in the tool-gateway's `http_connector`
and runs on **every** call regardless of the kernel allow-list:

| Control (in `http_connector._validate_destination`) | Effect |
|---|---|
| Deny-by-default origin allowlist | An origin not in `GATEWAY_HTTP_ALLOW_ORIGINS` is refused before any socket is opened |
| Loopback / link-local / multicast refusal *even when allowlisted* | Blocks the `169.254.169.254` cloud-metadata path and `127.0.0.0/8`; an allowlist entry is not treated as a decision to reach the node's own metadata service |
| Scheme validation | Only `http`/`https`; `file://`, `gopher://`, etc. are refused |
| Userinfo refusal | `http://user:pass@host` shapes are rejected |
| Redirect re-validation (≤ 3 hops) | The allowlist is re-checked against the **final** post-redirect origin, so an allowlisted host cannot bounce the call to an internal one |

Private ranges are deliberately *not* refused, because in-cluster targets like
`http://acme-admin:8080` are private by design — that is the intended shape, not
a hole.

So the model could never have used `http.get` to reach an arbitrary internal
endpoint. What the finding correctly identifies is narrower and still worth
fixing: a read-tier **network-egress** tool was auto-bypassing the operator
confirmation card on the same footing as in-cluster reads, and egress is a
different risk class. This patch makes that bypass opt-in.

## What changed

### `http.get` left the built-in default

`DEFAULT_AUTO_ALLOWED_TOOLS` in
`products/agent-platform/src/agent_service/services/kernel_middleware.py` no
longer names `http.get`. With the shipped default, an agent-initiated read-tier
`http.get` now answers an explicit `ASK` and parks an `action` card for operator
confirmation, exactly like any other read-tier tool that is off the resolved
list. `http.post` is unchanged — it is write-tier, so the `is_read_only` half of
the gate already refused it, and its single per-action card is the point of the
tool. The read-only-by-construction invariant (SPEC-021 R-3) is untouched:
naming a mutating tool in any auto-allow variable remains a logged no-op.

### A new additive variable: `AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA`

The existing `AGENT_GATEWAY_TOOL_AUTO_ALLOW` *replaces* the vetted default —
that is the posture the live HITL demo relies on when it drops `k8s.get_pod_logs`
to force a card. Replacement semantics are the wrong tool for opting a *single*
tool back in: an environment that wanted `http.get` card-free would have to
restate all eighteen default entries and then keep that copy manually synced
with every future change to the default — a permanent drift footgun.

`AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA` is therefore **additive**: its entries are
unioned with the resolved set (the built-in default, or the replacement set when
`AGENT_GATEWAY_TOOL_AUTO_ALLOW` is also present). The resolver normalises dots to
underscores for both variables, matching `FunctionTool.name`. The two compose:

| `AUTO_ALLOW` | `AUTO_ALLOW_EXTRA` | Resolved set |
|---|---|---|
| unset | unset | built-in default (no `http.get`) |
| unset | `http.get` | default ∪ `{http_get}` |
| `k8s.get_pod` | `http.get` | `{k8s_get_pod, http_get}` |
| `""` (empty) | unset | nothing auto-approved |

### The dev-k8s overlay opts back in

`shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env` now
sets `AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA=http.get`. The local demo cluster
therefore keeps the SPEC-058 R-1 "a read-tier `http.get` parks no card"
behaviour that the `acme-admin` health-check and adhoc-password-reset
walkthroughs narrate, while the **shipped** default — what a fresh production
install gets — stays hardened. The variable rides the existing
`platform-runtime-config` ConfigMap into the agent-service pod via `envFrom`; no
new manifest wiring.

## Validation

- `make validate-version` → `OK: all product and portal versions match
  VERSION=0.39.1` (19 version files + 8 `uv.lock` self-version re-locks, all
  version-only with no dependency drift).
- agent-platform suite: **1320 passed** (was 1317; +3 new tests for the
  `_EXTRA` union semantics — unions with the default, unions with the
  replacement set, empty is a no-op). The two pre-existing `http.get` assertions
  were rewritten to pin the new posture: `http_get` is **not** in the default,
  parks under the default middleware, and auto-allows only once opted in, while
  `http.post` parks even when its name is forced onto the list.
- The deterministic `make e2e` legs are unaffected: `http-check-demo.sh`
  exercises `http.get` at the **gateway** (discovery, `risk_level=read`, origin
  denial, live status projection), not through the kernel allow-list, and its
  card-parking HITL leg is about `http.post` and is opt-in (`RUN_HITL_LEG`,
  off by default).

## Deploy notes

- A cluster upgrading from v0.39.0 that **wants** agent-initiated `http.get` to
  stay card-free must set `AGENT_GATEWAY_TOOL_AUTO_ALLOW_EXTRA=http.get` (or
  include `http.get` in `AGENT_GATEWAY_TOOL_AUTO_ALLOW`). Without it, `http.get`
  parks a card — the intended hardened default.
- No migration, no secret re-provisioning, no policy-bundle change. The rollout
  is a config-and-image swap.
