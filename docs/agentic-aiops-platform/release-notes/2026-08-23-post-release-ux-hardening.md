# v0.9.1 — Post-SPEC-023 Portal UX & Stream Hardening

Date: 2026-08-23
Release type: patch (no API, contract, or deployment-shape changes)

## Summary

v0.9.1 closes the live-walkthrough review that followed the SPEC-023
(v0.9.0) portal rebuild. It fixes the stale-session "(no response
received)" defect end to end (gateway stream error propagation plus portal
self-healing), remediates the walkthrough's UX findings (session-creation
gating, evidence-card parity, sticky request banner, markdown tables,
version tag), and reworks the folded sidebar into a navigable icon rail so
navigation stays reachable and every view aligns uniformly. A code and
documentation review of the batch returned an approve verdict; its two
findings (httpx error-body cleanup hardening, a stale drawer-parity
comment) are remediated here as well.

## Change Set

### Fixed

- **Chat stream stale-session empty reply (major)**: a stale portal
  `sessionStorage` pointer at a deleted session made the gateway answer
  `200 text/event-stream` with zero frames, because the upstream 404 only
  fired inside the generator after the response was committed; the portal
  rendered "(no response received)" on every message until a new session
  was created. The gateway now opens the upstream stream eagerly
  (`open_chat_stream`, mirroring the confirm stream's eager-open pattern)
  and maps upstream 4xx to pass-through and 5xx/transport to 502; the
  portal retries once without the session id on a 404 so the agent service
  auto-creates a fresh session (the legacy first-message flow), and
  sessions the server reports as gone are tracked in `missingRef` so they
  never prime the stream pointer again. Gateway route-level tests assert
  404/409 pass-through and 502 mapping; portal hook tests assert the
  retry-once self-heal.
- **Markdown table header/body disconnect**: the ported renderer dropped
  the separator line as a blank line, splitting header and body into two
  stacked tables; a single-pass block parser now emits one `<table>` with
  `<thead>`/`<tbody>`.

### Changed

- **Folded sidebar is a navigable icon rail**: the Sider folds to a 64px
  rail (antd icon-only menu with tooltips, compact avatar + auth footer)
  instead of `collapsedWidth=0`. Because the rail owns its layout space,
  every view — chat included — aligns uniformly to its right; the
  `view-container-inset` hacks and the session-panel-header special case
  are removed, fixing sessions rendering under the pinned menu button.
  Rail sections render as hairline dividers instead of antd-clipped group
  titles ("Cont…"); the expanded sidebar and drawer keep the full
  Control/Workspace labels (SPEC-019 R-1). The drawer remains the full
  labeled menu on narrow viewports, with the rail providing one-tap
  navigation beside it.
- **Sticky request banner**: accent border and left bar, bold uppercase
  label for prominence, and a fully opaque gradient background so
  scrolling transcript text no longer bleeds through the pinned banner.
- **Pre-login session creation disabled**: the New-session button is
  disabled before sign-in like the composer; the server-side 401 path
  remains the defence for mid-session token expiry.
- **Evidence card parity**: cards stretch to the chat message width and
  expanded tool results are bounded (`max-height` + vertical scrollbar).
- **Version tag inline** beside the sidebar logo.
- **Gateway eager-open cleanup hardening**: both stream proxies
  finally-guard the error-body read so a failed `aread()` cannot leak the
  httpx response or client.

### Documented

- **SPEC-025 draft** (evidence persistence in session transcripts):
  durable `tool_call`/`tool_result` frames per turn with redaction and
  size caps (R-1), an additive session-detail contract (R-2), replayed
  evidence-card parity on reopened sessions (R-3), and per-entry
  `request_id`/duration traceability correlating to the audit trail
  (R-4). Lifts the explicit v1 deferral recorded in
  `session_transcript.py`. Numbering skips SPEC-024, reserved on the
  delivery roadmap for runtime LLM model switching.

## Validation

- `make verify` green (all product suites, kustomize overlays, policy and
  version lockstep at 0.9.1); platform-gateway 176 tests including the new
  eager-open error-propagation regressions; portal 64 Vitest tests
  including the stale-session retry cases; `tsc --noEmit` and Vite build
  clean.
- Live dev-k8s browser walkthrough: with zero sessions, a first message
  streams a full reply and auto-creates its session (no "(no response
  received)"); rail icon navigation and dividers verified folded; full
  labels verified expanded; banner verified opaque over scrolled
  transcripts.
