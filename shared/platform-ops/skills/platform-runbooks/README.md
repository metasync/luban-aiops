# platform-runbooks — sample skill source (SPEC-014)

Sample source standing in for a platform team's Kubernetes troubleshooting
wiki. Note the deliberate overlap with `sre-alerting` on pod
troubleshooting: ids are namespaced (`platform-runbooks/...` vs
`sre-alerting/...`), and deterministic scoring ranks both so the agent can
cite each team's take.

Content adapted from the
[Kubernetes documentation troubleshooting guides](https://kubernetes.io/docs/tasks/debug/debug-application/)
(CC-BY-4.0, `kubernetes/website`); see `NOTICE` for attribution.

## Contributing a skill

1. One Markdown file per guide under `guides/`, named after the problem it
   solves.
2. Add YAML frontmatter per `shared/shared-contracts/skill-format.md`:
   `title` and `description` are required; set `source_url` for adapted
   upstream content.
3. A browser web-check skill (SPEC-049) additionally sets `web_target`
   (the allowlisted origin the check runs against) and `risk_class` (`read`
   for snapshot-only probes, `write` when the flow clicks or types, which
   requires the HITL gate). This library ships no web-check runbook: the
   worked examples live under `samples/acme-admin/` (a bound browser
   `web_target` reset flow and a card-free `http.get` API-level health
   check), keeping SPEC-050 R-11's tutorial→platform dependency direction —
   a *platform* runbook does not point at a *sample* app.
4. Pre-flight locally before opening a PR:

   ```sh
   python -m skills_hub.validate shared/platform-ops/skills/platform-runbooks
   ```

   Exit code 0 means the source is safe to publish.

## Rules

- No secrets, hostnames, or customer data in skill bodies.
- Keep bodies under 64 KiB; split long guides.
- Duplicate file slugs within this source are rejected — rename instead.
