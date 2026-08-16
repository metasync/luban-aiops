"""Deterministic scorer tests (SPEC-014 R-3).

Weighting must be fixed and explainable (title > tags > body, body
occurrences saturating) and ordering byte-identical across runs (ties by
skill_id ascending).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from skills_hub.schemas.skill import Skill
from skills_hub.services.scoring import excerpt, rank, score

NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


def _skill(skill_id: str, title: str = "T", tags=None, body: str = "") -> Skill:
    return Skill(
        skill_id=skill_id,
        source_id=skill_id.split("/")[0],
        source_path=f"{skill_id}.md",
        source_ref="local",
        title=title,
        description="summary",
        tags=tags,
        updated_at=NOW,
        body=body,
    )


class ScoreTests(unittest.TestCase):
    def test_title_match_scores_three(self) -> None:
        skill = _skill("a/pod", title="Pod Troubleshooting", body="")
        self.assertEqual(score("pod", skill), 3.0)

    def test_tag_match_scores_two(self) -> None:
        skill = _skill("a/pod", title="Other", tags=["kubernetes"], body="")
        self.assertEqual(score("kubernetes", skill), 2.0)

    def test_body_occurrences_score_one_and_saturate(self) -> None:
        skill = _skill("a/pod", title="Other", body="pod " * 3)
        self.assertEqual(score("pod", skill), 3.0)  # 3 occurrences
        long_body = _skill("a/long", title="Other", body="pod " * 100)
        self.assertEqual(score("pod", long_body), 5.0)  # saturating cap

    def test_weights_compose_per_token(self) -> None:
        skill = _skill(
            "a/full",
            title="KubePodNotReady",
            tags=["KubePodNotReady"],
            body="kubepodnotready kubepodnotready",
        )
        # title 3 + tag 2 + body 2 = 7
        self.assertEqual(score("KubePodNotReady", skill), 7.0)

    def test_zero_when_no_token_matches(self) -> None:
        skill = _skill("a/pod", title="Pod", body="pod")
        self.assertEqual(score("dns", skill), 0.0)

    def test_empty_query_scores_zero(self) -> None:
        self.assertEqual(score("", _skill("a/pod", title="Pod")), 0.0)
        self.assertEqual(score("!!!", _skill("a/pod", title="Pod")), 0.0)


class RankTests(unittest.TestCase):
    def test_zero_score_records_excluded(self) -> None:
        hits = rank(
            "pod",
            [_skill("a/match", title="Pod"), _skill("a/other", title="Node")],
            limit=5,
        )
        self.assertEqual([h.skill.skill_id for h in hits], ["a/match"])

    def test_ties_break_by_skill_id_ascending(self) -> None:
        records = [
            _skill("b/doc", title="Pod"),
            _skill("a/doc", title="Pod"),
            _skill("c/doc", title="Pod"),
        ]
        hits = rank("pod", records, limit=5)
        self.assertEqual(
            [h.skill.skill_id for h in hits], ["a/doc", "b/doc", "c/doc"]
        )

    def test_ranking_is_deterministic_across_input_order(self) -> None:
        records = [
            _skill("a/only-tags", tags=["pod"]),
            _skill("a/in-title", title="Pod"),
            _skill("a/only-body", body="pod"),
        ]
        forward = [h.skill.skill_id for h in rank("pod", records, limit=5)]
        backward = [
            h.skill.skill_id for h in rank("pod", list(reversed(records)), limit=5)
        ]
        self.assertEqual(forward, backward)
        self.assertEqual(forward, ["a/in-title", "a/only-tags", "a/only-body"])

    def test_limit_caps_results(self) -> None:
        records = [_skill(f"a/doc{i}", title="Pod") for i in range(5)]
        self.assertEqual(len(rank("pod", records, limit=2)), 2)


class ExcerptTests(unittest.TestCase):
    def test_excerpt_starts_at_first_body_match(self) -> None:
        skill = _skill(
            "a/pod", body="leading text " + "filler " * 20 + "pod crash details"
        )
        snippet = excerpt("pod", skill)
        self.assertTrue(snippet.startswith("pod crash details"))
        self.assertLessEqual(len(snippet), 401)

    def test_excerpt_bounded_to_cap(self) -> None:
        skill = _skill("a/pod", body="pod" + "x" * 1000)
        self.assertLessEqual(len(excerpt("pod", skill)), 401)

    def test_excerpt_falls_back_to_description(self) -> None:
        skill = _skill("a/pod", title="Pod", body="no match tokens here")
        self.assertEqual(excerpt("pod", skill), "summary")


if __name__ == "__main__":
    unittest.main()
