---
kind: business_term
name: Business Glossary
category: business_term
scope:
    - '**'
---

### HITL
- Definition：Human-In-The-Loop approval gate. Write-tier browser actions (click, type, select, press_key, upload_file) park a confirmation card in the operator portal that a human must approve before execution proceeds. The design enforces a single HITL boundary per mutating flow (e.g., the admin sign-in click is the access-control gate; subsequent password reset uses read-only navigation).
- Aliases：human-in-the-loop、approval gate、confirmation card

### read-tier / write-tier
- Definition：Risk classification for browser tools. Read-tier tools (navigate, snapshot, screenshot, fill_credential, extract, wait_for, hover, evaluate, scroll, switch_frame) do not mutate state and auto-execute after origin re-check. Write-tier tools mutate the target page and require HITL approval. This distinction drives whether a call parks a confirmation card or executes immediately.
- Aliases：risk tier、tier_1、tier_2

### flow-bound / bound flow
- Definition：A browser session is scoped to a single target origin established when `web.navigate` first loads a page. Subsequent tool calls must stay within that origin; cross-origin interactions (including iframes via `web.switch_frame`) are denied. The flow also tracks steps consumed and can be marked approved/denied.
- Aliases：flow binding、bound origin、flow scope

### skill
- Definition：A natural-language runbook document (Markdown) that instructs the AgentScope agent how to operate a target system. Skills are ingested into the skills-hub service and surfaced to agents during chat. A complete automation pairs a skill with target infrastructure, credential sets, deployment wiring, and a demo script.
- Aliases：runbook、platform-runbook、ResetUserPassword skill

### credential set
- Definition：Server-side secret definitions (e.g., `admin-portal`) mounted into the agent runtime. Tools like `web.fill_credential` consume a credential set name — the actual values never leave the secrets store and are never logged or returned in snapshots/results.
- Aliases：credentials、secret set

### SPEC-NNN
- Definition：The project's requirement/specification numbering scheme. Each feature goes through draft → approved → delivered stages tracked in `docs/specs/SPEC-NNN-*/spec.md`, with index rows in `docs/specs/README.md` and roadmap entries in `delivery-roadmap.md`. Examples seen: SPEC-049 (browser web-check tools), SPEC-050 (browser tools expansion + samples reorganization), SPEC-048 (policy testing & rollout controls).
- Aliases：spec number、SPEC

### samples/web-checks/password-reset
- Definition：Self-contained tutorial sample demonstrating a write-class browser web-check: an agent follows the ResetUserPassword skill to log into a simulated legacy admin panel and reset a user's password, with a single HITL gate for the login click. Bundles the skill doc, target HTML pages, credential set, demo script, and kustomize wiring.
- Aliases：password-reset demo、password-reset sample

### tool-gateway
- Definition：FastAPI service that hosts the browser tool surface (`web.*` tools). It owns session lifecycle, origin allowlisting, deviation guarding, credential masking, and HITL confirmation cards exposed to the operator portal. Runs alongside a browser sidecar container.
- Aliases：gateway、tool gateway

### skills-hub
- Definition：Service that serves skill documents to agents. Skills are mounted into its volume via a ConfigMap generator; changes to skill content require regeneration and redeploy.
- Aliases：skills hub

### agent-service
- Definition：Service that orchestrates agents. It forwards tool calls to the tool-gateway, renders HITL confirmation cards in the operator portal, and enforces flow binding and step budgets.
- Aliases：agent service

### operator portal
- Definition：Web UI at `http://localhost:8080` where operators chat with agents, view live streams, and approve HITL confirmation cards. Also shows settings and audit logs.
- Aliases：portal、operator UI

### target admin panel
- Definition：Simulated legacy web application served at `http://localhost:9090/admin/` for demos. Includes login, user management, password reset form (auto-fills from URL params and auto-submits), and confirmation page. Mounted into the cluster as HTML files via a ConfigMap.
- Aliases：admin panel、legacy admin panel、target

### L3 deep review
- Definition：Security scan performed before pushing commits. In this repo it is invoked as a subagent that reviews diffs and reports findings with severity/confidence. Findings can be accepted as deliberate design (e.g., `web.fill_credential` auto-allow classified as correct per SPEC-049 D-3).
- Aliases：security scan、deep review、L3 scan

### make verify
- Definition：Top-level verification gate that runs all product test suites, renders all kustomize overlays, validates policy rules, checks version lockstep across products, and confirms scenario coverage. Green status is required before tagging releases.
- Aliases：verify gate、verification
