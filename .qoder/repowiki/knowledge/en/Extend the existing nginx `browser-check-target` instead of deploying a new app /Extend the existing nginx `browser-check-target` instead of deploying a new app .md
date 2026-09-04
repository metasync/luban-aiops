---
kind: design
name: Extend the existing nginx `browser-check-target` instead of deploying a new app for demos
source: session
category: adr
---

# Extend the existing nginx `browser-check-target` instead of deploying a new app for demos

_Source: coding plans from commit period b4f66c1 → c66ad9a — records intent at planning time; the implementation may lag or differ._

## Context
A password-reset demo needs a second admin portal alongside the existing browser-check target. Deploying a separate service would require a new allowlisted origin, new sidecar configuration, and additional infrastructure.

## Decision drivers
- operational simplicity
- no new deployment surface
- reuse existing allowlist and credential pipeline

## Considered options
- **Deploy a separate demo application** _(rejected)_ — pros: Clean separation of concerns; cons: New deployment, new allowlist entry, new credentials, more moving parts
- **Mount static HTML pages under `/admin/` on the existing nginx deployment** — pros: Zero new infrastructure; reuses the same sidecar, allowlist, and credential sync script; cons: Admin pages live alongside the existing check target in the same ConfigMap

## Decision
Add four static HTML pages (`admin-login.html`, `admin-users.html`, `admin-reset.html`, `admin-reset-done.html`) mounted via `subPath` volume mounts into the existing `browser-check-target` nginx pod under `/usr/share/nginx/html/admin/`, and add an `admin-portal` credential set through the existing `sync-browser-credentials.sh` script.

## Consequences
Demo surfaces scale by adding pages to the ConfigMap rather than spinning up pods. The allowlist and credential management remain unchanged, but the nginx deployment's ConfigMap grows and must be kept tidy as more demos are added.