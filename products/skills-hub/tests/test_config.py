"""Settings parsing tests (SPEC-014 R-2).

Malformed federation entries must fail startup fast with structured errors —
they may never surface later as silent sync failures.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from skills_hub.core.config import (
    SettingsError,
    SkillsSettings,
    parse_git_tokens,
    parse_query_clients,
    parse_sources,
)


class ParseSourcesTests(unittest.TestCase):
    def test_empty_yields_no_sources(self) -> None:
        self.assertEqual(parse_sources(""), tuple())

    def test_local_source(self) -> None:
        (source,) = parse_sources(
            '[{"source_id": "sre-alerting", "type": "local", "path": "/skills/a"}]'
        )
        self.assertEqual(source.source_id, "sre-alerting")
        self.assertEqual(source.type, "local")
        self.assertEqual(source.path, "/skills/a")

    def test_git_source_defaults_ref_to_head(self) -> None:
        (source,) = parse_sources(
            '[{"source_id": "team-a", "type": "git", '
            '"url": "https://example.com/team-a.git"}]'
        )
        self.assertEqual(source.type, "git")
        self.assertEqual(source.ref, "HEAD")

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources("not-json")

    def test_rejects_non_list(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources('{"source_id": "a"}')

    def test_rejects_bad_source_id(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources('[{"source_id": "Team_A", "type": "local", "path": "/x"}]')

    def test_rejects_duplicate_source_id(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources(
                '[{"source_id": "a", "type": "local", "path": "/x"},'
                '{"source_id": "a", "type": "local", "path": "/y"}]'
            )

    def test_rejects_unknown_type(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources('[{"source_id": "a", "type": "svn", "path": "/x"}]')

    def test_rejects_local_without_path(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources('[{"source_id": "a", "type": "local"}]')

    def test_rejects_git_without_url(self) -> None:
        with self.assertRaises(SettingsError):
            parse_sources('[{"source_id": "a", "type": "git", "ref": "main"}]')


class ParseGitTokensTests(unittest.TestCase):
    def test_parses_map(self) -> None:
        tokens = parse_git_tokens('{"team-a": "tok-1"}')
        self.assertEqual(tokens, {"team-a": "tok-1"})

    def test_rejects_non_object(self) -> None:
        with self.assertRaises(SettingsError):
            parse_git_tokens("[1, 2]")


class ParseQueryClientsTests(unittest.TestCase):
    def test_parses_pairs(self) -> None:
        clients = parse_query_clients("tool-gateway=s1,other=s2")
        self.assertEqual(
            [(c.client_id, c.secret) for c in clients],
            [("tool-gateway", "s1"), ("other", "s2")],
        )

    def test_skips_incomplete_entries(self) -> None:
        self.assertEqual(parse_query_clients("no-secret=,=no-id,,"), tuple())


class FromEnvTests(unittest.TestCase):
    def test_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = SkillsSettings.from_env()
        self.assertEqual(settings.sync_interval_seconds, 300)
        self.assertEqual(settings.data_path, "/var/lib/skills-hub")
        self.assertEqual(settings.store_backend, "memory")
        self.assertEqual(settings.workload_audience, "skills-hub")
        self.assertEqual(settings.sources, tuple())

    def test_reads_environment(self) -> None:
        env = {
            "SKILLS_SOURCES": '[{"source_id": "a", "type": "local", "path": "/s"}]',
            "SKILLS_SYNC_INTERVAL_SECONDS": "60",
            "SKILLS_STORE_BACKEND": "Postgres",
            "SKILLS_DB_URL": "postgresql://x",
            "SKILLS_QUERY_CLIENTS": "tool-gateway=secret",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = SkillsSettings.from_env()
        self.assertEqual(len(settings.sources), 1)
        self.assertEqual(settings.sync_interval_seconds, 60)
        self.assertEqual(settings.store_backend, "postgres")
        self.assertEqual(settings.query_clients[0].client_id, "tool-gateway")


if __name__ == "__main__":
    unittest.main()
