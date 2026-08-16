# sre-alerting — sample skill source (SPEC-014)

Sample source standing in for an SRE team's alerting-runbook repository.
Skills are keyed by Prometheus alert name and tagged with it, so an
alert → runbook lookup (search by alert name) works out of the box.

Content adapted from the community runbooks of
[prometheus-operator/runbooks](https://github.com/prometheus-operator/runbooks)
(Apache-2.0); see `NOTICE` for attribution.

## Contributing a skill

1. One Markdown file per runbook, placed under `alerts/` and named after
   the alert it answers.
2. Add YAML frontmatter per `shared/shared-contracts/skill-format.md`:
   `title` and `description` are required; tag the skill with its alert
   name; set `source_url` for adapted upstream content.
3. Pre-flight locally before opening a PR:

   ```sh
   python -m skills_hub.validate shared/platform-ops/skills/sre-alerting
   ```

   Exit code 0 means the source is safe to publish.

## Rules

- No secrets, hostnames, or customer data in skill bodies.
- Keep bodies under 64 KiB; split long runbooks.
- Duplicate file slugs within this source are rejected — rename instead.
