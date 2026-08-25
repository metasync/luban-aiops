# Spike: Shared-Package Extraction vs Copy-with-Parity (review finding M1)

Status: spike complete — decision recorded: keep copy-with-parity, revisit on stated triggers
Date: 2026-08-25
Roadmap home: Exploration Backlog "Shared-package extraction of duplicated service modules"
Verified against: `test_module_parity.py` and product build paths at 0.11.1

## 1. Question

The modules intentionally copied across services (telemetry, observability,
token verifier, audit emitter, ingest/query auth) are drift-guarded by
`products/tool-gateway/tests/test_module_parity.py`. Should they be
extracted into `shared/shared-sdk`, or is the copy-with-parity model still
the better trade once packaging, versioning, and image-build coupling
across the seven Python products are weighed?

## 2. Findings — measured state (verified)

- **Five parity families, small unique surface.** `core/telemetry.py`
  (~25 lines) is byte-identical in all seven services; `core/observability.py`
  diverges only by docstrings; `services/token_verifier.py` (~98 lines) has
  two gateway copies; `services/audit_emitter.py` (~97 lines) has four
  copies (platform-gateway, tool-gateway, identity-broker, skills-hub);
  `services/ingest_auth.py` / `query_auth.py` (~117 lines) are two
  placeholder-renamed copies. Unique logic totals roughly 400 lines; the
  duplication footprint is ~1,000 lines of pinned copies.
- **Churn is real but slow.** SPEC-029 added the fourth emitter copy;
  each emitter change must touch all copies in one commit (the suite
  enforces this). That is the one family whose copy count keeps growing.
- **Build coupling is the real cost of extraction.** Every product
  Dockerfile copies only its own directory (`.python-version`,
  `pyproject.toml`, `uv.lock`, `src/`) and runs `uv sync --frozen --no-dev`
  against a per-product lockfile. A path dependency on `shared/shared-sdk`
  would (a) widen every Docker build context to the repo root or add a
  copy/vendoring step, (b) ripple all seven `uv.lock` files on every
  shared-sdk change, and (c) interact with the coordinated `VERSION`
  lockstep enforced by `validate_version.py`. `shared-sdk` is currently a
  placeholder README — there is no packaging skeleton to grow into.
- **Deliberate divergences must survive any extraction.** observability
  docstrings are per-service by design, emitters bind to per-service
  settings classes, and incident-service's `audit_emitter.py` is a
  different design (triage `AuditConnector`) that the parity suite
  explicitly excludes. A shared package would need parameterization for
  exactly the axes the parity placeholders already describe.

## 3. Options weighed

| Option | Shape | Cost | Risk | Verdict |
|---|---|---|---|---|
| A. Keep copy-with-parity (status quo) | Copies + AST-normalized drift guards, same-commit update discipline | Ongoing: N-copy edits per change | Low; guards fail loudly | Current winner |
| B. Extract into `shared/shared-sdk` (path dep, uv package) | One source, per-product `pyproject` dependency | Packaging skeleton, seven lockfiles ripple per change, wider Docker build contexts, parameterization of the deliberate divergences | Medium; machinery cost is paid before any behavioral gain | Premature |
| C. Single source + `make sync` generator (like `sync-policy`) | Canonical file copied to products by a Make target | Build machinery + generation step in CI/local flow | Medium; generated files complicate diffs and review; parity tests already enforce the same invariant atomically | Rejected — duplicates the parity suite's job with more machinery |

## 4. Decision

**Keep the copy-with-parity model.** The duplicated surface is small,
slow-churning, and already drift-guarded; the extraction cost (packaging,
lockfile ripple, image-build coupling for seven products) is not yet
earned. Option C is rejected outright: it enforces the same invariant the
parity suite enforces, but with generation machinery that complicates
reviews.

**Revisit triggers** (any one is sufficient to re-open):

1. A sixth parity family is proposed, or a family grows to five or more
   copies (the audit emitter is at four and is the growth leader).
2. The same family needs behavioral changes in three or more specs within
   one quarter (same-commit N-copy edits stop being cheap).
3. `shared/shared-sdk` must be born anyway for another reason (e.g. typed
   shared-contract clients or service clients) — in which case extract the
   full family set at once, starting with the audit emitter; never extract
   one family piecemeal.

## 5. Backlog update

The roadmap row updates from "needs a spike" to "spiked 2026-08-25:
copy-with-parity retained; revisit triggers recorded". No spec promotion.
