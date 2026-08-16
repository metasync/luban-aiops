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
3. Pre-flight locally before opening a PR:

   ```sh
   python -m skills_hub.validate shared/platform-ops/skills/platform-runbooks
   ```

   Exit code 0 means the source is safe to publish.

## Rules

- No secrets, hostnames, or customer data in skill bodies.
- Keep bodies under 64 KiB; split long guides.
- Duplicate file slugs within this source are rejected — rename instead.
