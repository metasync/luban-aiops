# GitHub Repository Governance

## Objective

Define the baseline GitHub repository settings, review controls, labels, and milestones that fit the workspace model.

## Repository Baseline

Use the repository as a single workspace monorepo with:

- `main` as the protected default branch
- pull-request-based changes for normal work
- required review coverage aligned to `CODEOWNERS`
- issue and pull request templates enabled

## Recommended Repository Settings

Enable:

- branch protection for `main`
- secret scanning and push protection
- dependency graph and Dependabot alerts
- automatic deletion of head branches after merge
- merge queue only if review volume later justifies it

Keep disabled unless needed later:

- force pushes to `main`
- direct commits to `main` by default
- overly broad write access for contributors outside owning teams

## Branch Protection For `main`

Recommended baseline:

- require pull requests before merging
- require at least one approval
- require review from code owners
- dismiss stale approvals when new commits are pushed
- require branches to be up to date before merge
- require conversation resolution before merge
- block force pushes and branch deletion

As automation matures, add required status checks for:

- Markdown linting or link validation
- YAML validation for `.github` templates
- future workspace build and test jobs

## Merge Strategy

Recommended default:

- allow squash merges
- use clear PR titles so commit history remains meaningful

Optional later:

- allow rebase merge if the team wants a more linear history
- disable merge commits to keep the release history concise

## Label Scheme

Create labels in three groups.

Area labels:

- `area:docs`
- `area:operator-portal`
- `area:agent-platform`
- `area:policy-center`
- `area:identity-broker`
- `area:skills-hub`
- `area:platform-gateway`
- `area:tool-gateway`
- `area:execution-runtime`
- `area:shared-contracts`
- `area:shared-sdk`
- `area:platform-ops`
- `area:repo-governance`

Type labels:

- `type:bug`
- `type:feature`
- `type:chore`
- `type:docs`
- `type:security`
- `type:refactor`

Release labels:

- `release:r0-foundation`
- `release:r1-read-only-copilot`
- `release:r2-skills-guidance`
- `release:r3-incident-triage`
- `release:r4-gated-actions`
- `release:r5-hardening`

## Milestone Scheme

Use milestones aligned to the implementation backlog:

- `R0 - Platform Foundation`
- `R1 - Read-Only Operations Copilot`
- `R2 - Skills and Grounded Guidance`
- `R3 - Incident Triage and Collaboration`
- `R4 - Approval-Gated Bounded Actions`
- `R5 - Hardening and External Consumption`

For larger execution windows, add optional support milestones such as:

- `Repo Governance`
- `Platform Bootstrap`

## Ownership Alignment

`CODEOWNERS` should mirror the workspace boundary model:

- `operator-portal` owned by frontend or UX maintainers
- `agent-platform` owned by runtime or orchestration maintainers
- `policy-center` and `identity-broker` owned by security or control-plane maintainers
- `platform-gateway` owned by platform security maintainers
- `tool-gateway` owned by integrations maintainers
- `execution-runtime` owned by automation maintainers
- shared modules owned by core platform maintainers

Replace placeholder teams in `.github/CODEOWNERS` with real GitHub teams before enabling strict required-review policies.

## Initial Manual Setup Checklist

1. create the GitHub teams or map `CODEOWNERS` entries to real users
2. enable branch protection on `main`
3. create the area, type, and release labels
4. create milestones for `R0` through `R5`
5. enable secret scanning and dependency alerts
6. add repository description and topics

## Suggested Repository Description And Topics

Description:

- `Enterprise-grade agentic AIOps workspace with product-oriented boundaries, policy-aware control, and staged release planning.`

Topics:

- `aiops`
- `agents`
- `agentscope`
- `kubernetes`
- `platform-engineering`
- `sso`
- `policy-engine`
- `mcp`
- `monorepo`

## Final Recommendation

Keep the repository governance lightweight but explicit at the start.

That gives the workspace enough structure for safe collaboration without over-automating before the first release slices exist.
