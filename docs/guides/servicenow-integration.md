# ServiceNow Live Integration Guide

How to point the Luban AIOps platform at a **real ServiceNow instance** — a
production tenant, a sub-production instance, or a Personal Developer Instance
(PDI) — and prove the read-tier `servicenow.*` tool surface against it
(SPEC-067). Covers the ServiceNow-side provisioning (integration user, read
ACLs, OAuth client-credentials application), the Luban-side wiring (credential
set, gateway knobs, overlay), validation, restore, day-2 operations, and
troubleshooting.

The [Tool and Connector Guide](tool-configuration.md#servicenow-connector-spec-067)
owns the connector inventory and the dev/mock activation checklist. This guide
owns the live-instance path end to end and is the expanded form of that page's
"Operator Validation Against a Real PDI" runbook; read it before wiring anything
that is not the in-cluster mock.

## 1. What the integration is — and is not

The connector is a **native REST/Table-API binding**
(`products/tool-gateway/src/tool_gateway/ingestion/servicenow_native.py`) over
`GET {base}/api/now/table/{table}[/{sys_id}]`. It is *not* an MCP-adapter
binding: Stage-0 verification (2026-10-19) found ServiceNow's own MCP server
unprovisioned on the operator PDI, which tripped SPEC-067 OQ-3's REST fallback.

| Tool | Table | Operation | Parameters |
|---|---|---|---|
| `servicenow.incident.list` | `incident` | list | `limit` (1–100, default 20) |
| `servicenow.incident.get` | `incident` | get | `sys_id` (32-hex, required) |
| `servicenow.change_request.list` | `change_request` | list | `limit` (1–100, default 20) |
| `servicenow.change_request.get` | `change_request` | get | `sys_id` (32-hex, required) |
| `servicenow.user.get` | `sys_user` | get | `sys_id` (32-hex, required) |
| `servicenow.cmdb_ci.get` | `cmdb_ci` | get | `sys_id` (32-hex, required) |

Invariants that hold regardless of what the instance is configured to do:

- **Read tier only.** No table write, update, delete, or attachment fetch is
  admitted at any tier; every tool carries `risk_level=read`.
- **Gateway-owned binding.** Admission, canonical names, fixed tables, field
  projections, argument schemas, and the tier live in
  `ingestion/servicenow_binding.py`. Nothing a ServiceNow instance returns —
  and nothing a model emits — can widen them.
- **Deny-by-default twice over.** The connector registers only under
  `GATEWAY_SERVICENOW_ENABLED=true`; the admission allowlist
  `SERVICENOW_ADMITTED_TOOLS` denies every name it does not list, including the
  deferred `problem` and `attachment` capabilities.
- **Field projection is a safety allowlist.** Each tool names the exact columns
  it may return; the connector asks for them via `sysparm_fields` *and*
  re-projects every record after the response arrives. The `sys_user` allowlist
  omits `password`, `user_password`, and every other credential column.
- **Acting-service identity.** The instance is addressed with the acting
  service's credential, not the requesting user's delegated identity: every call
  audits `target_identity_mode=acting_service` (SPEC-067 R-4). Per-user target
  RBAC is SPEC-070's seam and is **not** delivered by this integration.
- **Credentials never travel.** The OAuth2 token is acquired in memory and rides
  an outbound `Authorization` header only — never a URL, a tool result, an
  evidence field, an audit payload, or a log line.

## 2. Requirements

### 2.1 ServiceNow side

| Requirement | Detail |
|---|---|
| Table API | `/api/now/table/{table}` on any supported Now Platform release. No plugin to activate and no scoped-application endpoint: the connector calls the **global** namespace. |
| OAuth 2.0 client credentials | An `oauth_entity` application with the **Client Credentials** inbound grant type. On Australia-generation and later instances this grant is behind a platform property (see §3.3). |
| Dedicated integration user | A machine-identity user with no interactive login, owning the OAuth application. Never reuse a human account. |
| Read access to four tables | `incident`, `change_request`, `sys_user`, `cmdb_ci` — read ACLs only (see §3.2 for the two viable postures). |
| Network reachability | The tool-gateway pod must reach `https://<instance>.service-now.com:443` (the same host also serves `oauth_token.do`). TLS verification is **always on** and there is no knob to disable it; see the trust note below. |

**Certificate trust.** The connector builds its `httpx` client with no `verify`
argument, so the trust chain is httpx's default: `SSL_CERT_FILE`, else
`SSL_CERT_DIR`, else the `certifi` bundle baked into the image
(`certifi==2026.7.22` in `products/tool-gateway/uv.lock`). A public ServiceNow
tenant is covered by `certifi` with no work. For a private CA or a TLS-inspecting
proxy, mount your bundle and point `SSL_CERT_FILE` at it — a ConfigMap/env change,
not a code change:

```bash
kubectl -n dev-luban-aiops create configmap servicenow-ca-bundle \
  --from-file=ca-bundle.pem=/path/to/your-ca.pem
# then, in your overlay: mount it read-only and set
#   SSL_CERT_FILE=/etc/ssl/certs/servicenow-ca-bundle.pem
```

Probe from inside the pod before blaming the platform — `curl` is present in the
gateway image, `python3` is not:

```bash
kubectl -n dev-luban-aiops exec deployment/tool-gateway -c tool-gateway -- \
  curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' \
  --max-time 10 https://<instance>.service-now.com/api/now/table/incident
```

A non-zero `ssl_verify_result` is a trust-chain problem; `000` with a timeout is
reachability or NetworkPolicy (§4.4).

Columns the projections expect. If your tenant renames or removes one, the read
still succeeds — the connector projects down to the intersection — but confirm
the result carries the fields you need (§5.3):

| Table | Projected columns |
|---|---|
| `incident` | `sys_id`, `number`, `short_description`, `state`, `priority`, `severity`, `impact`, `urgency`, `category`, `assignment_group`, `assigned_to`, `opened_at`, `updated_at`, `closed_at`, `cmdb_ci` |
| `change_request` | `sys_id`, `number`, `short_description`, `state`, `type`, `priority`, `risk`, `impact`, `start_date`, `end_date`, `requested_by`, `assignment_group`, `cmdb_ci` |
| `sys_user` | `sys_id`, `user_name`, `name`, `email`, `title`, `department`, `active`, `manager` — **never** `password`/`user_password` |
| `cmdb_ci` | `sys_id`, `name`, `sys_class_name`, `ci_class_id`, `operational_status`, `install_status`, `ip_address`, `mac_address`, `support_group`, `assigned_to` |

### 2.2 Luban side

- A deployed platform (`make deploy`) with a healthy `tool-gateway` and the
  `servicenow-dev` runtime profile — or your own overlay carrying the same
  `GATEWAY_SERVICENOW_*` fragment (§4.4). The base overlay keeps the connector
  **off**, so any overlay without the profile stays deny-by-default.
- `audit-service` provisioned (`sync-audit-secrets.sh`) with its durable
  Postgres store, so the R-4/R-5 attribution evidence is queryable rather than
  log-only.
- On the operator workstation: `kubectl` with context on the cluster, and
  `python3` — the credential sync script builds its JSON with it (it is not a
  `jq` shop).

### 2.3 Governance prerequisites

Settle these **before** provisioning, not after:

1. Written approval to let ITSM record content flow into the platform's tool
   results, evidence frames, and audit store.
2. A named owner for the integration credential, a rotation cadence, and a
   custody rule for the client secret (§3.3).
3. The least-privilege decision recorded: custom read-only role + ACLs
   (preferred) or a stock role with a documented deviation (§3.2).
4. Confirmation that no write access is required. The gateway admits none, so a
   request for write access is a **new spec**, not a configuration change.

## 3. Provision the ServiceNow side

### 3.1 Create the dedicated integration user

*System Security → Users and Groups → Users → New*:

| Field | Value | Why |
|---|---|---|
| User ID | e.g. `luban_reader` | Stable, non-human, greppable in the instance's own logs. |
| Identity type | **Machine** | Sets `web_service_access_only=true`: no interactive login, no password reset surface, excluded from license-consuming user counts. |
| Password | *(leave unset)* | A machine identity authenticates through the OAuth client, never with a password. |
| Roles | `rest_service` + the read role from §3.2 | `rest_service` is the baseline for REST access; the read role bounds which rows are visible. |

Two instance behaviours worth checking immediately after saving:

- **Auto-provisioning groups.** Some PDIs run a provisioning job that re-adds new
  users to a "Conditional Script Writer" group
  (`snc_required_script_writer_permission`). Remove the membership and re-check
  after a few minutes; if it keeps coming back, disable the job for this user
  rather than fighting it.
- **Role availability.** The stock read-only roles named in older runbooks
  (`itil_read_only`, `readonly`) do **not** exist on hardened or
  Australia-generation instances. Do not assume a role name; look it up.

### 3.2 Grant read access — two postures

| Posture | What it needs | When to use it |
|---|---|---|
| **Custom read-only role + table read ACLs** (preferred) | `security_admin` to author ACLs on `sys_security_acl`. Create a role (e.g. `luban_table_reader`), add `read` ACLs for the four tables, assign the role to the integration user. | Any production or properly hardened tenant. This is the least-privilege ideal the runbook assumes. |
| **Stock `itil` role** (deviation) | Only `admin`. | A PDI whose Deny-Unless hardening ACLs gate ACL administration behind `security_admin`, which the operator account lacks. |

If you take the deviation, record it: on a hardened PDI, `change_request` and
`cmdb_ci` already carry Deny-Unless read ACLs, and the gateway's own admission
allowlist plus read tier remain the real boundary. Write the deviation into the
dated validation entry (§5.7) so a later reader does not mistake it for the
recommended posture.

Either way, verify from the *instance's* point of view before moving on: sign in
as (or impersonate) the integration user and confirm the four tables are
readable and that no write operation is offered.

### 3.3 Create the OAuth client-credentials application

ServiceNow has two generations of this flow. Check which one your instance has
before you start: open *System OAuth → Application Registry*. If a **Machine
Identity Console** banner or a "New integration" wizard greets you, take the
modern path; if the registry offers *New → Create an OAuth API endpoint for
client_credentials*, take the legacy path.

**Modern path (Application Registry + Machine Identity Console).**

1. Enable the platform property
   `glide.oauth.inbound.client.credential.grant_type.enabled=true`
   (*System Properties → System Security* or a `sys_properties` record). Without
   it the wizard cannot mint a client-credentials integration.
2. *System OAuth → Application Registry* → **Machine Identity Console** →
   *New integration* → **OAuth – Client credentials grant**.
3. Bind the machine user from §3.1 in the **OAuth application user** field. This
   is the identity whose ACLs bound every call.
4. **Provider name** is required by the form but is *not persisted* on the
   resulting `oauth_entity` record — a plain value such as `ServiceNow` works.
   Only external IdP names appear in the picker; the field accepts free text.
5. Select the auth scope. On hardened instances the only offering is the broad
   `useraccount` ("full access to all REST APIs"); actual access stays bounded by
   the bound user's ACLs and the gateway-side allowlist.
6. Save, then open the record and copy the **client secret once**. The
   **client ID is auto-generated and read-only** — you cannot choose it.

**Legacy path.** *System OAuth → Application Registry* → *New* → *Create an
OAuth API endpoint for client_credentials* → set Name, grant type
`client_credentials`, bind the user, and use the generated Client ID / Client
Secret pair. On these releases an "OAuth API Provider Client"
(`oauth_configuration`) model may also exist; it is **removed** on
Australia-generation instances, so do not script against it.

**Client-secret custody rule.** The secret is displayed once. Copy it **directly**
into the operator's local, git-ignored override file (or your secret manager) —
never through a chat transcript, a CI log, a screenshot, or a commit. ServiceNow
secrets routinely contain shell metacharacters (`)`, `$`, `!`), so a file that is
later `source`d by a shell will fail to parse; read it with a key/value parser
instead (§4.3).

Capture and store:

| Field | Example shape | Where it goes |
|---|---|---|
| Instance base URL | `https://<instance>.service-now.com` | `GATEWAY_SERVICENOW_BASE_URL` |
| Token URL | `https://<instance>.service-now.com/oauth_token.do` | credential set `token_url` |
| Client ID | 32-hex, auto-generated | credential set `client_id` |
| Client secret | ~32 chars, may contain metacharacters | credential set `client_secret` (secret only) |
| `oauth_entity` sys_id | 32-hex | your records, for rotation/revocation |
| Integration user sys_id | 32-hex | your records, and as a `sys_user` validation target |

### 3.4 Smoke-test the credential locally

Prove the grant and the four tables **before** touching the cluster, so a
provisioning mistake is not diagnosed as a platform fault. Print only statuses,
counts, and lengths — never a token or a secret:

```bash
python3 - <<'PY'
import base64, json, sys, urllib.error, urllib.parse, urllib.request

BASE = "https://<instance>.service-now.com"
CLIENT_ID = "<client-id>"

# Read the secret from a file: never inline it, and never `source` such a file in
# a shell (ServiceNow secrets contain metacharacters that break parsing).
values = {}
with open("/path/to/servicenow-live.env", encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
CLIENT_SECRET = values["SERVICENOW_CLIENT_SECRET"]


def get(request):
    """Return (status, body). urlopen raises on 4xx/5xx; report the code, not
    the body, so an upstream error page can never echo a credential."""
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, request.full_url.split("?")[0], file=sys.stderr)
        return exc.code, {}


basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
token_request = urllib.request.Request(f"{BASE}/oauth_token.do", data=body)
token_request.add_header("Authorization", f"Basic {basic}")
status, payload = get(token_request)
token = payload.get("access_token", "")
print("token: HTTP", status, "len", len(token))
if not token:
    sys.exit("no access_token — check the client/secret pair and the grant type")

# sysparm_display_value matches what the connector actually sends.
for table in ("incident", "change_request", "sys_user", "cmdb_ci"):
    url = (f"{BASE}/api/now/table/{table}"
           "?sysparm_limit=1&sysparm_fields=sys_id&sysparm_display_value=true")
    read = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    status, payload = get(read)
    rows = payload.get("result", [])
    print(table, "HTTP", status, "rows", len(rows),
          "sys_id", rows[0]["sys_id"] if rows else None)
PY
```

Expected: `token: HTTP 200` and four `HTTP 200` lines. A `401` on the token call
means the client/secret pair or the grant type is wrong; a `403` on a table means
the bound user's ACLs do not cover it (§3.2).

### 3.5 Collect real sys_ids for validation

The shipped live-check asserts canned mock records, so the real-data legs need
real identifiers. Keep the `sys_id`s the smoke test printed for one `incident`,
one `change_request`, and one `cmdb_ci`, plus the integration user's own
`sys_id` — the last one is the best `sys_user` target because you know exactly
which columns it holds.

## 4. Wire Luban to the instance

### 4.1 The credential set

The connector resolves a **named** credential set out of one secret-mounted JSON
file (SPEC-068's seam) — never an inline env value:

```json
{
  "servicenow-live": {
    "scheme": "oauth2_client_credentials",
    "token_url": "https://<instance>.service-now.com/oauth_token.do",
    "client_id": "<client-id>",
    "client_secret": "<client-secret>"
  }
}
```

A set is admitted only when every field its scheme requires is a non-empty
string; an unknown scheme or a missing field is ignored with a warning, so a
half-formed set fails closed rather than half-working. The file reloads on mtime
change, so **rotating the secret needs no gateway restart**. `scope`, `audience`,
`resource`, and `client_auth` (`client_secret_basic`, the default, or
`client_secret_post`) are optional; ServiceNow accepts the default basic client
authentication.

In dev the file lives in the `tool-gateway-servicenow-credentials` secret under
key `credential-sets.json`, mounted read-only at
`/etc/luban/servicenow-credentials/credential-sets.json` by the `servicenow-dev`
profile's strategic merge patch. The mount is `optional: true` so the pod starts
before the secret exists — the connector then fails closed at call time with
`CREDENTIAL_SET_NOT_FOUND` rather than dialing the instance unauthenticated.

### 4.2 Gateway knobs

| Variable | Purpose | Default |
|---|---|---|
| `GATEWAY_SERVICENOW_ENABLED` | Register the six read tools | `false` (code default; `servicenow-dev` flips it) |
| `GATEWAY_SERVICENOW_BASE_URL` | Table-API base | *(none)* — `https://<instance>.service-now.com` for a live tenant |
| `GATEWAY_SERVICENOW_TIMEOUT_MS` | HTTP client timeout | `10000`, clamped by the connector to `1`–`30000` ms (`MAX_TIMEOUT_MS`); a larger value is silently reduced, not honoured |
| `GATEWAY_SERVICENOW_CREDENTIAL_SET` | Name of the credential set to present | *(none)*; dev uses `servicenow-mock` |
| `GATEWAY_SERVICENOW_CREDENTIAL_SETS` | Path to the mounted credential-set JSON | *(none)* — falls back to `GATEWAY_HTTP_CREDENTIAL_SETS`, then `GATEWAY_BROWSER_CREDENTIAL_SETS`, so one synced secret can serve it; dev sets it to the mount above |

All five are **operator configuration, never model-selected**. They merge into
the `platform-runtime-config` ConfigMap from the profile's `servicenow.env`.
Throughout this guide `dev-luban-aiops` is the dev-k8s namespace; substitute your
own in every `kubectl -n` and in the secret names the sync script derives.

### 4.3 Path A — repoint the dev-k8s overlay (validation)

This is the path the live-PDI check used. It is deliberately reversible (§6).

```bash
# 1. Put the live client credentials in a git-ignored file, chmod 600.
#    Values with shell metacharacters break plain `source`, so extract them
#    through a parser and quote them for the shell.
eval "$(python3 -c '
import shlex, sys
vals = dict(l.strip().split("=", 1) for l in open(sys.argv[1]) if "=" in l.strip())
for key in ("SERVICENOW_CLIENT_ID", "SERVICENOW_CLIENT_SECRET",
            "SERVICENOW_PDI_TOKEN_URL"):
    print(f"export {key}={shlex.quote(vals[key].strip())}")
' .workspaces/servicenow-live.env)"

# 2. Write the credential set from those overrides. One generator, two sinks:
#    the script writes the gateway's credential-set secret and the mock's OAuth
#    secret from the same values, and restarts tool-gateway itself.
SERVICENOW_TOKEN_URL="$SERVICENOW_PDI_TOKEN_URL" \
  shared/platform-ops/gitops/sync-servicenow-credentials.sh dev-luban-aiops

# 3. Point the connector at the live instance.
kubectl -n dev-luban-aiops patch configmap platform-runtime-config \
  --type merge -p \
  '{"data":{"GATEWAY_SERVICENOW_BASE_URL":"https://<instance>.service-now.com"}}'
kubectl -n dev-luban-aiops rollout status deployment/tool-gateway
```

Do **not** issue a second `kubectl rollout restart` straight after the sync
script: it already restarted the gateway, and a restart inside the same second
is refused with *"if restart has already been triggered within the past second"*.
Wait for the rollout and verify instead.

Sink 2 (the mock's `access-token`) is unused against a live instance — a real
tenant issues its own tokens dynamically.

### 4.4 Path B — a committed, production-shaped overlay

For anything that is not a validation run, keep credentials out of the sync
script's generated path:

1. Commit an env fragment carrying the **non-secret** knobs
   (`GATEWAY_SERVICENOW_ENABLED`, `_BASE_URL`, `_TIMEOUT_MS`,
   `_CREDENTIAL_SET`, `_CREDENTIAL_SETS`) the way `servicenow-dev/servicenow.env`
   does, and a strategic merge patch mounting your credential secret.
2. Have your secret manager or pipeline write the `credential-sets.json` key into
   that secret, and deploy with `SKIP_SERVICENOW_CREDENTIALS=true` so the dev
   generator does not overwrite it. Skipping leaves both dev secrets unwritten:
   the connector fails closed (`CREDENTIAL_SET_NOT_FOUND`) and the mock 401s
   every call — neither runs open.

   The contract is one key holding one JSON object (§4.1), so any writer works.
   Ad-hoc, from a file your secret manager produced:

   ```bash
   kubectl -n dev-luban-aiops create secret generic \
     tool-gateway-servicenow-credentials \
     --from-file=credential-sets.json=/path/to/credential-sets.json \
     --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n dev-luban-aiops rollout restart deployment/tool-gateway
   ```

   The `--dry-run=client | kubectl apply` form is what the sync script itself
   uses, so re-running either converges on the same object instead of erroring on
   "already exists". Delete the local file afterwards; the credential file reloads
   on mtime change, so a later rotation needs no restart.
3. Never commit a client secret, a token, or an instance-specific credential
   file. `.workspaces/` is git-ignored for exactly this reason.
4. If the cluster restricts egress with NetworkPolicies, add an egress rule for
   the instance host on 443. Note that the policies selecting `tool-gateway` in
   dev are `Ingress`-only, so dev egress is unrestricted by default — a
   production namespace usually is not.

### 4.5 Confirm the wiring inside the pod

```bash
kubectl -n dev-luban-aiops exec deployment/tool-gateway -c tool-gateway -- \
  sh -c 'echo "$GATEWAY_SERVICENOW_BASE_URL $GATEWAY_SERVICENOW_ENABLED $GATEWAY_SERVICENOW_CREDENTIAL_SET"'
kubectl -n dev-luban-aiops exec deployment/tool-gateway -c tool-gateway -- \
  sh -c 'wc -c < /etc/luban/servicenow-credentials/credential-sets.json'
```

Print only non-secret values and byte counts. Slim service images have no
`python3` on `PATH` (`exit code 127`), so parse mounted JSON on the workstation,
not in the pod.

## 5. Validate against the live instance

CI makes **no live external call** (SPEC-067 OQ-5) — the in-cluster thin mock
stands in for the tenant, and the wire path is additionally proven by the
in-process Layer-2 tests. Everything below is an operator step run out-of-band.

### 5.1 The shipped live-check is mock-bound — know what it can prove

```bash
kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000 &
STRICT_LIVE=true shared/platform-ops/e2e/servicenow-check.sh
```

`STRICT_LIVE=true` turns the gated live leg from a skip-with-a-note into a hard
failure, so that in dev a green run proves the live reads rather than merely
registration and fail-closed behaviour. **Against a real tenant the script
cannot go green**: its `[5/6]` live leg asserts the *mock's* canned records —
incident `INC0010001`, change `CHG0020001`, user `mock.operator`, CI
`Mock DB Cluster` — on both the `list` and the `get` legs, and a real instance
holds none of them. The leg therefore fails on its first assertion, and under
`STRICT_LIVE=true` a skip is a failure too.

What the script **does** prove against a live tenant is legs `[1/6]`–`[4/6]`,
which are target-agnostic and worth running: unauthenticated discovery/invoke
returns `401`; a delegated operator token is accepted; exactly six read tools are
registered at `risk_level=read` with no write or deferred verb admitted; and the
denied names (`servicenow.incident.update`, `servicenow.problem.get`) plus a
missing/malformed `sys_id` fail closed with no target contact.

Two legs prove nothing live and must be done by hand:

- `[5/6]` is mock-bound (above) — **including** its `sys_user` credential-stripping
  assertion, which rides the same canned `mock.operator` record. Re-assert the
  stripping on a real user row yourself (§5.3).
- `[6/6]` greps the captured tool-result bodies for the **mock's**
  `client_secret`/`access_token`, not the live tenant's. Against a real instance it
  passes without ever testing the credential you actually provisioned, so check the
  live client secret and access token by hand (§5.6).

The script inspects **no** gateway logs either — log hygiene is likewise the
manual step in §5.6.

So the operator workflow against a live tenant is: run the shipped script for the
target-agnostic legs and *expect* `[5/6]` to fail on the canned records, then
perform §5.2–§5.6 yourself. Most operators keep a private variant of the check
with their own sys_ids substituted (the 2026-10-22 PDI run did exactly that); if
you do, keep it out of `make e2e` — CI must never make a live external call
(OQ-5), and a real-tenant script is not CI-testable.

### 5.2 The live-data legs the script cannot run

For each of the four tables, drive the real reads yourself: `list` first, then
`get` a `sys_id` **that list actually returned** (or the ones collected in
§3.5). Confirm each returns a real record rather than a clean fail-closed code,
and that the projection carries the fields you expect. This is the part an
operator must own — do not report the shipped script's canned leg as a live
pass, and do not report a canned-leg failure as a connector fault.

### 5.3 Field projection on live rows

For each of the four tables, confirm the returned columns are a subset of the
binding's allowlist (§2.1) and that no secret-bearing column appears. On
`sys_user`, assert explicitly that `password` and `user_password` are **absent**
from a real user row. Where a column must be renamed or added, edit
`ingestion/servicenow_binding.py` as **config** — never the connector code — and
re-run the product suite.

### 5.4 Fail-closed negatives

Confirm against the live instance that a denied or deferred name
(`servicenow.incident.update`, `servicenow.problem.get`,
`servicenow.attachment.get`) and a missing or malformed `sys_id` are refused
**gateway-side with no target contact** — check the gateway log for the absence
of an outbound request, not just for the error code.

### 5.5 Audit attribution

`audit-service` stdout carries only HTTP access lines, so grep proves nothing.
Query the durable store. `audit_events` has the columns `event_id`,
`occurred_at`, `event_type`, `service`, `request_id`, `subject`, `username`,
`actor`, `roles`, `session_id`, `outcome`, and `details` — everything
connector-specific (tool name, target system, identity mode, risk level,
failure class, result status) lives inside the JSONB `details`:

```bash
kubectl -n dev-luban-aiops exec postgres-0 -- psql -U audit -d audit -t -A -F'|' -c \
  "SELECT details->>'tool_name', details->>'target_system',
          details->>'target_identity_mode', details->>'risk_level',
          details->>'status', details->>'failure_class', outcome
     FROM audit_events
    WHERE details->>'target_system' = 'servicenow'
      AND occurred_at > now() - interval '10 minutes'
    ORDER BY occurred_at;"
```

Expect one row per invocation with `target_system=servicenow`,
`target_identity_mode=acting_service`, `risk_level=read`, and — on any
timeout/unreachable fault — `failure_class=target_unavailable` (SPEC-067 R-5),
which is distinct from a policy denial and from an upstream error. The actor
column is `actor`, not `actor_id`; `status` and `failure_class` are JSONB keys,
not columns.

### 5.6 Result and log hygiene

Assert the client secret, the access token, and the `Authorization` header value
appear in **no** tool result, evidence frame, audit payload, or gateway log line.
Redaction is the backstop, not the design: the credential never enters those
surfaces in the first place. The shipped script's redaction leg only tests the
*mock's* values (§5.1), so test the live ones yourself:

```bash
# Read the live secret into a variable without echoing it, then count its
# occurrences in the gateway log. The count must be 0. grep sees the value in its
# argv, so run this on a workstation you trust, not a shared shell host.
LIVE_SECRET=$(python3 -c 'print(dict(
    line.strip().split("=", 1)
    for line in open(".workspaces/servicenow-live.env")
    if "=" in line.strip())["SERVICENOW_CLIENT_SECRET"])')
kubectl -n dev-luban-aiops logs deployment/tool-gateway -c tool-gateway \
  --tail=5000 | grep -cF "$LIVE_SECRET"
```

Repeat for any captured tool result or evidence frame you recorded during §5.2.

### 5.7 Record the result

A live validation is evidence, and evidence belongs on the living docs. Add a
dated entry to all three surfaces, stating the instance, the date, which legs
passed, any deviation taken (§3.2), and the restore action (§6):

- `docs/specs/SPEC-067-servicenow-mcp-ingestion-pilot/spec.md` — a new dated
  `## Changelog` entry at the top of the section.
- `docs/agentic-aiops-platform/delivery-roadmap.md` — a new dated paragraph in
  the R6 status block, leaving prior dated entries untouched.
- `docs/guides/tool-configuration.md` — the runbook's executed-record block.

Never record a credential, a client ID, or a token in a committed document.

## 6. Restore the committed dev state

After a validation run, put the cluster back so the repository's committed state
and the running state agree:

```bash
# Regenerate dev credentials into both sinks (no overrides).
shared/platform-ops/gitops/sync-servicenow-credentials.sh dev-luban-aiops

# Repoint at the mock.
kubectl -n dev-luban-aiops patch configmap platform-runtime-config \
  --type merge -p \
  '{"data":{"GATEWAY_SERVICENOW_BASE_URL":"http://servicenow-mock-table-api:8000"}}'
kubectl -n dev-luban-aiops rollout status deployment/tool-gateway

# Close the port-forward and confirm the live credential is gone from the cluster.
kubectl -n dev-luban-aiops get secret tool-gateway-servicenow-credentials \
  -o jsonpath='{.data.credential-sets\.json}' | base64 -d | grep -c '<instance>'
```

The last command should print `0`. The live client secret then exists only in the
operator's git-ignored local file and in the instance itself — at which point
rotating it in ServiceNow is a one-line re-run of §4.3.

## 7. Operating the integration

- **Rotation.** Rotate the client secret in Application Registry, then re-run
  §4.3 (or your secret manager's write) — the credential file reloads on mtime, so
  no restart is strictly required, though the sync script restarts anyway. Rotate
  on a schedule and immediately on any suspected transcript or log exposure.
- **What to watch.** `CREDENTIAL_ACQUISITION_FAILED` (secret wrong, expired, or
  grant disabled), `SERVICENOW_UPSTREAM_ERROR` (a 4xx/5xx fact — usually an ACL or
  a removed column), `SERVICENOW_TIMEOUT` / `SERVICENOW_UNREACHABLE` (network or
  instance maintenance, audited as `target_unavailable`), and a rising
  `REDACTION_OVERFLOW` rate (a column you did not expect is leaking
  credential-shaped content).
- **Rate limits and timeouts.** The connector caps `sysparm_limit` at 100 and
  bounds the HTTP client with `GATEWAY_SERVICENOW_TIMEOUT_MS` (clamped to
  `1`–`30000` ms). A tenant-side REST rate limit shows up as
  `SERVICENOW_UPSTREAM_ERROR`; raise the timeout only if the instance is genuinely
  slow, never to mask a hang.
- **No retry, no backoff, no redirect following.** Each tool call makes exactly
  **one** transport attempt: the client is built with `follow_redirects=False` and
  there is no retry loop. A transient fault therefore surfaces immediately as
  `SERVICENOW_TIMEOUT` / `SERVICENOW_UNREACHABLE` (audited
  `failure_class=target_unavailable`) rather than being silently absorbed, and a
  `3xx` from a proxy or a mis-scoped base URL surfaces as an upstream error rather
  than as a followed hop. This is deliberate for a read tier — retrying belongs to
  the caller, who can see the fail-closed code — but it means a flaky network
  looks like a failing tool. Re-issue the call rather than raising the timeout.
- **Instance upgrades.** ServiceNow can change role names, ACL hardening, and the
  OAuth administration model between releases (the Australia generation replaced
  the legacy client model outright — §3.3). After a tenant upgrade, re-run §3.4
  and §5 before trusting the surface.
- **Revocation.** Deactivate the `oauth_entity` record (or the integration user)
  to cut access immediately; the gateway then fails closed on the next call with
  no platform change required. Follow with a restore (§6) so dev does not sit
  pointed at a dead credential.
- **Data handling.** Records returned by these tools become tool results,
  evidence frames, and audit payloads inside the platform. Treat the four tables'
  content as in-scope for your data-handling review even though the surface is
  read-only.

## 8. Troubleshooting

| Code / symptom | Likely cause | Fix |
|---|---|---|
| `TOOL_NOT_FOUND` on every `servicenow.*` call | `GATEWAY_SERVICENOW_ENABLED` not `true` in the pod, or the name is outside the admission allowlist | Check the pod env (§4.5); confirm the name against §1 |
| `SERVICENOW_NOT_CONFIGURED` / `SERVICENOW_INVALID_BASE_URL` | Missing or malformed base URL | Set `GATEWAY_SERVICENOW_BASE_URL` to `https://<instance>.service-now.com` (no path, no trailing slash needed) |
| `CREDENTIAL_SET_NOT_FOUND` | Secret not written, mount missing, set-name mismatch, **or** the set's `scheme` is not `oauth2_client_credentials` (an unknown scheme is dropped at parse time with a warning, so the set simply does not exist) | Re-run the sync script; confirm `GATEWAY_SERVICENOW_CREDENTIAL_SET` matches the JSON key exactly and that `scheme` is spelled correctly (§4.1) |
| `CREDENTIAL_ACQUISITION_FAILED` | Wrong/expired secret, grant type not enabled, or token URL unreachable | Re-run §3.4 locally; confirm `glide.oauth.inbound.client.credential.grant_type.enabled` on modern instances |
| `SERVICENOW_UPSTREAM_ERROR` (401/403) | The bound user's ACLs do not cover the table | Re-check §3.2; confirm the **OAuth application user** is the integration user |
| `SERVICENOW_UPSTREAM_ERROR` (404) on a `get` | The sys_id does not exist on this tenant | Use a sys_id from a live `list` (§5.2) |
| `SERVICENOW_UPSTREAM_ERROR` (3xx) | The tenant redirected — the client is built with `follow_redirects=False`, so a redirect is reported, never followed | Usually a proxy, a wrong base URL scheme/host, or an endpoint that needs the global namespace |
| `SERVICENOW_TIMEOUT` / `SERVICENOW_UNREACHABLE` | Egress blocked, DNS failure, TLS trust failure, or instance maintenance | Probe from inside the pod (§2.1); check NetworkPolicy egress and the CA bundle |
| `SERVICENOW_RESPONSE_INVALID` | HTTP **200** with a non-JSON body, or a 200 whose `result` is not the expected list (list) / object (get) | An HTML page served as 200 — a captive portal, an IdP interstitial, or a mis-scoped endpoint; confirm with the in-pod probe (§2.1) |
| `SERVICENOW_INVALID_TABLE` | The binding's fixed table name is not a valid ServiceNow table identifier | A binding-config regression, not a runtime fault — check `servicenow_binding.py` against the tenant |
| `INVALID_PARAMETERS` before any request | Missing or non-32-hex `sys_id`, or a non-integer / sub-1 `limit` | Gateway-owned schema rejection; fix the arguments. A `limit` above 100 is **not** rejected — it is silently clamped to 100 |
| Audit query returns 0 rows | Wrong store or wrong column names | Query the durable Postgres store, not stdout; the column is `actor` and the details are JSONB (§5.5) |
| Credential file fails to `source` | ServiceNow secrets contain shell metacharacters | Parse key/value in Python and quote for the shell (§4.3) |

## 9. Extending the surface

- **A new table or column** is a binding-config change in
  `ingestion/servicenow_binding.py`: a new `ServiceNowReadTool` entry with its
  fixed table, its field allowlist, its argument schema, and `risk_level="read"`,
  plus admission in `SERVICENOW_ADMITTED_TOOLS`. Never a connector-code change,
  and never something the instance can advertise into existence.
- **Deferred today:** `problem` and `attachment`. The attachment file endpoint
  (`/attachment/{sys_id}/file`) is a binary/exfiltration surface and needs its own
  approved spec before it is admitted.
- **Out of scope:** any write, update, or delete tier; free-form `sysparm_query`
  filters (an unbounded filter string is an injection surface with no approved use
  case); and per-user target identity — every call is `acting_service` until
  SPEC-070 delivers user-delegated outbound identity.
- **Should a future instance expose ServiceNow's own MCP server**, the reuse path
  is the generic server-agnostic MCP adapter from SPEC-069: a new binding, not a
  connector rewrite.

## Related

- [Tool and Connector Guide](tool-configuration.md) — connector inventory, dev/mock activation, credential-set file format
- [Configuration Reference](configuration-reference.md) — environment variables, secret contracts, runtime profiles
- [Adding a Tool to the Tool Gateway](adding-a-tool.md) — contributor walkthrough for a new connector or tool
- [Approval and HITL Governance](approval-and-hitl.md) — the four-layer approval model the read tier sits under
- [Troubleshooting](troubleshooting.md) — platform-wide symptom diagnostics
- [SPEC-067](../specs/SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) — the ServiceNow read-tier ingestion pilot specification
- [SPEC-068](../specs/SPEC-068-outbound-execution-credential-schemes/spec.md) — the outbound credential schemes (`oauth2_client_credentials`)
- [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md) — the deferred per-user target identity seam
