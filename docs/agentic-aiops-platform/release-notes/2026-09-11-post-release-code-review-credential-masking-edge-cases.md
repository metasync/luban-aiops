# Post-Release Code Review Remediation: Credential-Masking Edge Cases (v0.36.2)

Date: 2026-09-11

A patch batch closing an in-depth code review of the credential-masking surface
v0.36.1 introduced — `agent_service/services/prose_redaction.py` and the two
`redact_secret_query` twins (kernel `secret_params.py` and gateway
`browser_connector.py`). Seven fixes across three source files: six close an
edge where a credential still reaches a human-readable or persisted surface,
and the seventh is the opposite failure — an over-mask that destroys a
non-secret word. There is no contract, policy, schema, or audit change: the
stream contract stays at v11 and Skill at v2.

## How this batch differs from v0.36.1

v0.36.1 was written from live runs: every entry described a defect *observed*
in a browser session against the dev-k8s cluster, with the plaintext quoted
from the evidence store or the rendered reply. This batch is written from a
*code review* of the machinery that release added. The v0.36.1 fixes were
correct on the paths their tests exercised; the review read the new functions
for the inputs those tests did not reach, and each finding below was then
**reproduced against the live code** — a `python -c` probe through the product
venv showing the plaintext in the output — before it was fixed. That
reproduce-then-fix discipline is what separates a real edge from a theoretical
one, and it is the same standard v0.36.1 set: a finding is not fixed on
inspection alone, and a fix is not shipped without a test confirmed to fail
against the unpatched code.

The organizing observation is that a masker is only as strong as its narrowest
input. v0.36.1 proved the masking *paths* work; this batch proves the
*detectors* fire on the inputs that reach them — a credential in a URL's
userinfo rather than its query, a scheme that is not `http(s)`, a shape or a
scheme split across stream deltas, a secret riding an exception message, a
length met only by trailing punctuation, and a `key=value` token that should
give up its value but keep its name.

## What changed

### The DSN userinfo, masked in both query-redactor twins

`redact_secret_query` and its gateway twin `_redact_secret_query` opened with:

```python
if not parsed.query:
    return url
```

A credential carried in the *userinfo* — `scheme://user:password@host`, the
shape of a database DSN, which frequently has no query string at all — hit that
early return and was handed back untouched, then re-serialized into a tool
result, an evidence frame, and the audit trail. Both copies now mask
`parsed.password` in the netloc first, by a single first-occurrence replace
(`:{password}@` → `:MASK@` in the kernel, `:***@` in the gateway) that
preserves every non-secret byte exactly — no re-encoding, matching the
segment-wise query rewrite beside it — and the empty-query early return is
gone, so the userinfo is masked whether or not a query is also present. The two
stay lockstep, which is the invariant `validate_secret_vocabulary.py` already
enforces on the vocabulary they share; this fix keeps their *behaviour* aligned
too.

### The DSN in prose, recognised and harvested

The prose layer had the twin gap. `URL_TOKEN` matched only `https?://` or
`www.`, so a `postgres://admin:pw@db/app` DSN the model echoed back sailed
straight through the URL layer, and `_secret_query_values` — which harvests the
literals the exact-match layer later masks — read only a query string, so it
took nothing from the userinfo either. The scheme is now any RFC-3986 scheme
(`[a-z][a-z0-9+.\-]*://`, still case-insensitive), and `_secret_query_values`
harvests the userinfo password, quoted and unquoted, on the same footing as a
query value. An assistant restating a DSN credential bare — the value without
its URL — now meets the exact-literal layer, because the literal was harvested
from the user's turn where the DSN first appeared.

### Streaming: a pinned shape held across deltas

`StreamingProseRedactor` holds back the tail of each delta so a secret split
across two chunks is never published in pieces. v0.36.1 taught it to hold a URL
split mid-scheme and mid-query. It did **not** hold a *pinned shape* split the
same way — a PEM `-----BEGIN … PRIVATE KEY-----` header, a JWT `eyJ…`, a
`Bearer`/`Basic` token, an AWS `AKIA…` key id — and the class docstring said so
outright, listing it as a known limit that "would need unbounded lookahead" and
leaning on the durable transcript for the guarantee.

That limit is now closed for the streaming projection too. A new
`_shape_hold()` holds a tail that either *is* a proper prefix of one of the
five shape anchors (the boundary fell inside `-----BEG` or `ey`) or *opens
with* a whole anchor whose pattern has not matched yet (a JWT still streaming
its segments). It is wired into `feed` beside the existing scheme and literal
holds:

```python
cut = min(cut, len(self._pending) - self._shape_hold())
```

`_safe_cut` takes over once the shape completes; `flush` releases it if it
never does. Anchors already inside a completed match are skipped — that match
is `_safe_cut`'s job, not a shape still arriving.

The hold is capped at `SHAPE_HOLD_MAX_CHARS = 512`, and the cap is a stated
tradeoff rather than an afterthought. A real single-token credential — a JWT, a
Bearer token, an AKIA id — is comfortably under 512 and is held whole. A shape
longer than the cap (a large multi-line PEM key) is best-effort in the stream
and falls back to the durable transcript for the unbounded guarantee, exactly
as the docstring's "not finished arriving" limit already described. The cap
also bounds how long a *false* anchor stalls the stream: `Bearer token expired`
opens with the `Bearer` anchor but `token` is too short to match the pinned
pattern, so without a cap the redactor would hold to end-of-stream on ordinary
prose. The anchors are the leading literals of
`skill_draft.REDACTION_VALUE_PATTERNS`, not a third secret vocabulary, and
`test_streaming_holds_every_pinned_shape` streams one canonical example of each
shape so an anchor that drifts from its pattern fails the suite rather than
silently reopening the leak.

### Streaming: an uppercase scheme held across deltas

`URL_TOKEN` is `re.IGNORECASE`, so the match layer redacts `HTTPS://…` as
readily as `https://…`. But `_scheme_hold` compared the raw buffer tail against
`URL_SCHEME_STARTS`, which is lowercase, so an uppercase scheme split across
deltas (`… to HTTPS` | `://…`) matched no prefix, published `HTTPS`, and left
the `://…` half with no scheme to be recognised by — the URL leaked character
by character. The held tail is now lowercased before the comparison, so the
case the match layer already accepts is the case the hold layer protects.

### Gateway: the navigation error path

`web.navigate`'s exception handler passed `str(exc)` straight to
`make_error_result`. A Playwright navigation error interpolates the target URL
into its message — `Page.goto: navigating to "<url>", timed out` — and for the
password-reset demo that URL carries `?newpw=<value>`, while a DSN-style target
could carry it in the userinfo. The message rides into the tool result, the
evidence frame, and the audit trail, so the secret left in plaintext on the
*error* path even though the success path masks it in nine places (v0.36.1).
The message now goes through `_redact_secret_query(str(exc))` first. The fix is
kept at the navigate call site rather than pushed into the shared
`make_error_result`, which every tool calls and which has no URL context to
redact — a structural change there would be both too broad and unable to know
which argument is a URL.

### The literal detector: length gate before punctuation strip

`is_credential_literal` decides whether a whitespace-delimited token looks like
a typed credential. It stripped sentence punctuation *first*, then applied the
`CREDENTIAL_MIN_CHARS` (8) length gate:

```python
candidate = token.strip(TOKEN_EDGE_PUNCTUATION)
if len(candidate) < CREDENTIAL_MIN_CHARS:
    return False
```

A valid eight-character credential the operator ended with a sentence `!` or
`.` — `Secret1!` — was cut to seven by the strip and rejected, so the
exact-literal layer never harvested it and the assistant's restatement leaked.
The gate now runs on the token *as written* (`len(token.strip())`), and the
character-class test still runs on the stripped core, so surrounding
punctuation counts toward neither budget.

### The literal detector: not harvesting a `key=value` token whole

The one over-mask in the batch, and the opposite of a leak — worth fixing
precisely because a masker that destroys non-secret information is not thereby
safer, only less useful. `credential_literals`'s secret-name heuristic
harvested whole whitespace tokens when the text mentioned a secret name, so
`newpw=Temp…` went onto the literal list *including its key*. But the
`KEY_VALUE_SECRET` pass had already harvested the value on its own, so the
whole-token entry added nothing on the value side and everything on the damage
side: an assistant writing "the `newpw=***` field" collapsed to "the `***`
field", losing the one token that said what the field was. The heuristic branch
now skips any token `KEY_VALUE_SECRET` matches; the value stays covered by that
pass, and the informative key survives.

## Untouched

The stream contract (v11) and the Skill contract (v2) are unchanged, as are the
policy bundles, the authorization matrix, the JSON schemas, the audit event
types, and SPEC-037 signed execution. No new knob, endpoint, or policy action.
The masking *vocabulary* is unchanged — `validate_secret_vocabulary.py` still
reports 20 secret-parameter substrings, the `<credential-reference>` hole
marker, and 4 shape patterns in order — because these fixes widen what the
detectors recognise, not what they consider secret. The v0.36.1 machinery these
edge cases sit inside (the nine gateway emission sites, the evidence-frame
posture, the title masker, the per-session serialization lock, the HITL expiry
settle) is unchanged in behaviour. Execution-runtime, incident-service,
audit-service, identity-broker, platform-gateway, skills-hub, and the portal
take no change beyond the version lockstep.

The same review recorded further findings that are **not** credential leaks —
robustness and documentation-quality observations rather than masking edges.
They are deliberately out of this batch, which was scoped to the leak class,
and are tracked for the follow-up code-and-documentation review rather than
dropped.

## Verification

`make verify` is green at 0.36.2: **2551 tests** across the eight Python
products with no failures (+42 over 0.36.1, the new regression tests), all four
GitOps overlays rendering, 18 policy rules and 137 api + 19 tools scenarios
passing, version lockstep validated across every product and the portal's vite
wiring, and all three secret-vocabulary couplings agreeing — 20
secret-parameter substrings and 4 shape patterns between agent-platform and
tool-gateway, and the `<credential-reference>` hole marker between
agent-platform and skills-hub. The portal's own vitest suite runs separately,
since `make verify` does not include operator-portal.

Every fix is pinned by a regression test **confirmed to fail against the
unpatched code** — the batch's own discipline, since a test that cannot fail
cannot protect anything. The three source files were stashed with the tests
left in place, and the suite ran red for the right reasons before running
green:

- prose redaction (`test_prose_redaction.py`, 59 → 99 passing): the
  pinned-shape hold is parametrized over all four shapes × eight split sizes,
  asserting the secret never appears in the emitted stream *and* that streaming
  is byte-identical to whole-text redaction; plus the uppercase-scheme split,
  the non-HTTP DSN, the `Secret1!` length gate, and the `key=value` over-mask;
- query redactor (`test_secret_params.py`, 24 → 25): the userinfo credential
  masked with the query params preserved;
- gateway (`test_browser_connector.py`, 118 → 119): the navigation-error
  message masks the secret, keeps `newpw=***`, and leaves `user=alice` intact.

In total 36 tests failed pre-fix across the two products, all behavioural, and
all passed post-fix.

## Deployment state

This release's cluster rebuild was **batched into the v0.36.3 follow-up**, not
cut standalone. The post-release documentation review landed right after this
tag as v0.36.3, so the two ship one coordinated build/deploy and no
`0.36.2-dev-k8s-<sha>` image tag exists on its own; the masking fixes here go
live on that v0.36.3 build. Until it lands the cluster keeps serving the
previously deployed v0.36.1 functional images, which is what live testing
continues against.

The coordinated tag still cannot be recorded inside the commit that creates it
— the short sha is an input to the tag — so the authoritative record remains
the gitignored `shared/platform-ops/gitops/dev-k8s/.images.env`, which
`make build` writes and `make deploy` consumes, verifiable from the running
pods. This is the platform's traceability posture (ADR-0008): the tag is
derived from a git ref rather than asserted in prose. A rebuild resets
in-flight agent state, since redis runs on an `emptyDir`; sessions persist in
Postgres, and approval cards parked before the redeploy are disrupted by it —
the accepted cost of testing against a properly tagged image.
