"""Skill store tests (SPEC-014 R-2/R-3).

Exercises the in-memory store (per-source atomic swap, get/list/search with
filters, pagination) and the Postgres adapter against a fake driver double.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from skills_hub.core.config import SkillsSettings
from skills_hub.schemas.skill import Skill
from skills_hub.services.skill_store import (
    InMemorySkillStore,
    PostgresSkillStore,
    StoreError,
    build_skill_store,
)

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


def _skill(
    skill_id: str,
    tags=None,
    body: str = "body",
    title="T",
    web_target=None,
    risk_class=None,
) -> Skill:
    return Skill(
        skill_id=skill_id,
        source_id=skill_id.split("/")[0],
        source_path=f"{skill_id.split('/')[-1]}.md",
        source_ref="local",
        title=title,
        description="summary",
        tags=tags,
        web_target=web_target,
        risk_class=risk_class,
        updated_at=NOW,
        body=body,
    )


class InMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemorySkillStore()

    def test_replace_source_swaps_atomically(self) -> None:
        _run(self.store.replace_source("a", [_skill("a/one")]))
        _run(self.store.replace_source("a", [_skill("a/two"), _skill("a/three")]))
        self.assertEqual(_run(self.store.count()), 2)
        self.assertIsNone(_run(self.store.get("a/one")))
        self.assertIsNotNone(_run(self.store.get("a/two")))

    def test_replace_source_isolates_sources(self) -> None:
        _run(self.store.replace_source("a", [_skill("a/one")]))
        _run(self.store.replace_source("b", [_skill("b/one")]))
        _run(self.store.replace_source("a", []))  # source a fails sync -> empty
        self.assertEqual(_run(self.store.count()), 1)
        self.assertIsNotNone(_run(self.store.get("b/one")))

    def test_cross_source_duplicate_slugs_are_legal(self) -> None:
        _run(self.store.replace_source("a", [_skill("a/runbook")]))
        _run(self.store.replace_source("b", [_skill("b/runbook")]))
        self.assertEqual(_run(self.store.count()), 2)

    def test_list_orders_by_skill_id_and_paginates(self) -> None:
        _run(
            self.store.replace_source(
                "a", [_skill("a/c"), _skill("a/a"), _skill("a/b")]
            )
        )
        page, total = _run(self.store.list(0, 2))
        self.assertEqual([s.skill_id for s in page], ["a/a", "a/b"])
        self.assertEqual(total, 3)
        page, _ = _run(self.store.list(2, 2))
        self.assertEqual([s.skill_id for s in page], ["a/c"])

    def test_list_filters_by_source_and_tag(self) -> None:
        _run(
            self.store.replace_source(
                "a",
                [_skill("a/one", tags=["Alert"]), _skill("a/two")],
            )
        )
        _run(self.store.replace_source("b", [_skill("b/one", tags=["alert"])]))
        page, total = _run(self.store.list(0, 100, source="b"))
        self.assertEqual(total, 1)
        # Tag filter is case-insensitive.
        page, total = _run(self.store.list(0, 100, tag="alert"))
        self.assertEqual(total, 2)

    def test_search_ranks_and_excludes_zero_scores(self) -> None:
        _run(
            self.store.replace_source(
                "a",
                [
                    _skill("a/hit", title="Pod Troubleshooting"),
                    _skill("a/miss", title="Node Debugging"),
                ],
            )
        )
        hits = _run(self.store.search("pod", 5))
        self.assertEqual([h.skill.skill_id for h in hits], ["a/hit"])

    def test_get_unknown_returns_none(self) -> None:
        self.assertIsNone(_run(self.store.get("a/nope")))

    def test_ready_and_close_are_noops(self) -> None:
        self.assertTrue(_run(self.store.ready()))
        self.assertIsNone(_run(self.store.close()))

    def test_prune_sources_drops_unconfigured_sources(self) -> None:
        _run(self.store.replace_source("a", [_skill("a/one")]))
        _run(self.store.replace_source("b", [_skill("b/one"), _skill("b/two")]))
        removed = _run(self.store.prune_sources(["b"]))
        self.assertEqual(removed, 1)
        self.assertIsNone(_run(self.store.get("a/one")))
        self.assertEqual(_run(self.store.count()), 2)

    def test_prune_sources_with_empty_config_clears_the_store(self) -> None:
        _run(self.store.replace_source("a", [_skill("a/one")]))
        removed = _run(self.store.prune_sources([]))
        self.assertEqual(removed, 1)
        self.assertEqual(_run(self.store.count()), 0)


class PostgresStoreAdapterTests(unittest.TestCase):
    """SQL shape against a fake psycopg driver (audit-service pattern)."""

    def _fake_connect(self, calls: list[dict], rows=None):
        class FakeCursor:
            rowcount = 1

            async def execute(self, sql, params=None):
                calls.append({"sql": sql, "params": params})

            async def fetchall(self):
                return rows or []

            async def fetchone(self):
                return (rows[0] if rows else None)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            async def commit(self):
                return None

            async def close(self):
                return None

        @asynccontextmanager
        async def connect():
            yield FakeConn()

        return connect

    def test_replace_source_deletes_then_inserts_in_one_connection(self) -> None:
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        replaced = _run(
            store.replace_source("a", [_skill("a/one"), _skill("a/two")])
        )
        self.assertEqual(replaced, 2)
        self.assertIn("DELETE FROM skills", calls[0]["sql"])
        self.assertEqual(calls[0]["params"], {"source_id": "a"})
        self.assertEqual(calls[1]["sql"].lstrip()[:6], "INSERT")
        self.assertEqual(calls[1]["params"]["skill_id"], "a/one")
        self.assertEqual(calls[1]["params"]["tags"], None)
        self.assertEqual(len(calls), 3)

    def test_replace_source_persists_web_flow_declaration(self) -> None:
        # SPEC-049 R-3: web_target/risk_class must survive the Postgres
        # round-trip — the gateway binds flows from the detail response.
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls)
        )
        _run(
            store.replace_source(
                "a",
                [
                    _skill(
                        "a/check",
                        web_target="http://target:8080/",
                        risk_class="write",
                    )
                ],
            )
        )
        self.assertIn("web_target", calls[1]["sql"])
        self.assertEqual(calls[1]["params"]["web_target"], "http://target:8080/")
        self.assertEqual(calls[1]["params"]["risk_class"], "write")

    def test_get_maps_web_flow_columns(self) -> None:
        calls: list[dict] = []
        row = (
            "a/check", "a", "check.md", "local", "T", "summary",
            None, None, None, NOW, "body",
            "http://target:8080/", "write",
        )
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[row])
        )
        skill = _run(store.get("a/check"))
        self.assertIsNotNone(skill)
        self.assertEqual(skill.web_target, "http://target:8080/")
        self.assertEqual(skill.risk_class, "write")

    def test_search_uses_full_text_prefilter(self) -> None:
        calls: list[dict] = []
        row = (
            "a/hit", "a", "hit.md", "local", "Pod", "summary",
            ["pod"], None, None, NOW, "pod body", None, None,
        )
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[row])
        )
        hits = _run(store.search("pod", 5))
        self.assertIn("to_tsquery", calls[0]["sql"])
        self.assertEqual(calls[0]["params"]["query"], "pod")
        self.assertEqual([h.skill.skill_id for h in hits], ["a/hit"])

    def test_search_joins_multi_word_queries_with_or(self) -> None:
        """OR semantics keep partial matches for the shared scorer;
        plainto_tsquery would AND the words and return nothing."""
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        hits = _run(store.search("kubernetes incident", 5))
        self.assertEqual(hits, [])
        self.assertEqual(calls[0]["params"]["query"], "kubernetes | incident")

    def test_search_without_tokens_skips_the_query(self) -> None:
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        hits = _run(store.search("!!!", 5))
        self.assertEqual(hits, [])
        self.assertEqual(calls, [])

    def test_list_applies_source_filter(self) -> None:
        calls: list[dict] = []
        # No page rows: the count query consumes the fake result, so the
        # recorded SQL still shows the WHERE clause shape.
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        _run(store.list(0, 10, source="a"))
        self.assertTrue(
            any("source_id = %(source)s" in call["sql"] for call in calls)
        )

    def test_tag_filter_uses_exact_case_insensitive_match(self) -> None:
        """ILIKE would treat the parameter as a pattern ('kube%' matching
        wildcards) and diverge from the in-memory backend; exact
        case-insensitive equality keeps the backends byte-identical."""
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        _run(store.list(0, 10, tag="kube%"))
        tag_calls = [
            call
            for call in calls
            if call["params"] and call["params"].get("tag") == "kube%"
        ]
        self.assertTrue(tag_calls)
        self.assertIn("lower(t) = lower(%(tag)s)", tag_calls[0]["sql"])
        self.assertNotIn("ILIKE", tag_calls[0]["sql"])

    def test_prune_sources_deletes_unconfigured_source_rows(self) -> None:
        calls: list[dict] = []
        store = PostgresSkillStore(
            "postgresql://fake", connect=self._fake_connect(calls, rows=[])
        )
        removed = _run(store.prune_sources(["a", "b"]))
        self.assertEqual(removed, 1)  # fake cursor rowcount
        self.assertIn("DELETE FROM skills", calls[0]["sql"])
        self.assertIn("NOT (source_id = ANY(%(keep)s))", calls[0]["sql"])
        self.assertEqual(calls[0]["params"], {"keep": ["a", "b"]})


class BuildSkillStoreTests(unittest.TestCase):
    def test_defaults_to_memory_backend(self) -> None:
        store = build_skill_store(SkillsSettings())
        self.assertIsInstance(store, InMemorySkillStore)

    def test_postgres_backend_requires_db_url(self) -> None:
        with self.assertRaises(StoreError):
            build_skill_store(SkillsSettings(store_backend="postgres", db_url=""))

    def test_postgres_backend_selected_with_url(self) -> None:
        store = build_skill_store(
            SkillsSettings(store_backend="postgres", db_url="postgresql://x")
        )
        self.assertIsInstance(store, PostgresSkillStore)


if __name__ == "__main__":
    unittest.main()
