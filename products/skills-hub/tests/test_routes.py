"""HTTP route tests for skills-hub (SPEC-014 R-2/R-3).

Drives the real FastAPI app through TestClient with one local source on a
temp directory; the sync loop performs the first cycle during lifespan, so
tests poll the auth-exempt status endpoint until the snapshot is served.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from skills_hub.app import create_app
from skills_hub.core.config import get_settings

QUERY_CLIENTS = "tool-gateway=tg-secret"

DOC_POD = """---
title: KubePodNotReady
description: Pod stuck not ready — triage steps.
tags: [kubernetes, KubePodNotReady]
---

Check pod events and container status.
"""

DOC_NODE = """---
title: NodeDebugging
description: Node level debugging guide.
---

Start with node conditions.
"""


def _basic(client_id: str, secret: str) -> str:
    raw = f"{client_id}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class SkillsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "KubePodNotReady.md").write_text(DOC_POD)
        (self.root / "NodeDebugging.md").write_text(DOC_NODE)

        sources = json.dumps(
            [{"source_id": "sre-alerting", "type": "local", "path": str(self.root)}]
        )
        self._patcher = patch.dict(
            os.environ,
            {
                "SKILLS_STORE_BACKEND": "memory",
                "SKILLS_SOURCES": sources,
                "SKILLS_QUERY_CLIENTS": QUERY_CLIENTS,
                "SKILLS_SYNC_INTERVAL_SECONDS": "3600",
            },
        )
        self._patcher.start()
        get_settings.cache_clear()
        self._client_cm = TestClient(create_app())
        self.client = self._client_cm.__enter__()
        self._wait_synced()

    def tearDown(self) -> None:
        self._client_cm.__exit__(None, None, None)
        get_settings.cache_clear()
        self._patcher.stop()
        self._tmp.cleanup()

    def _wait_synced(self, expected: int = 2, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            body = self.client.get("/api/v1/skills/status").json()
            for source in body["sources"]:
                if source["accepted"] >= expected or source["last_error"]:
                    return
            time.sleep(0.05)
        raise AssertionError("source did not sync in time")

    @property
    def auth(self) -> dict[str, str]:
        return {"authorization": _basic("tool-gateway", "tg-secret")}

    # --- List -------------------------------------------------------------

    def test_list_requires_auth(self) -> None:
        response = self.client.get("/api/v1/skills")
        self.assertEqual(response.status_code, 401)

    def test_list_rejects_bad_credential(self) -> None:
        response = self.client.get(
            "/api/v1/skills",
            headers={"authorization": _basic("tool-gateway", "wrong")},
        )
        self.assertEqual(response.status_code, 401)

    def test_list_returns_summaries_without_body(self) -> None:
        response = self.client.get("/api/v1/skills", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        ids = [s["skill_id"] for s in body["skills"]]
        self.assertEqual(
            ids,
            ["sre-alerting/kubepodnotready", "sre-alerting/nodedebugging"],
        )
        self.assertNotIn("body", body["skills"][0])
        self.assertEqual(body["skills"][0]["source_id"], "sre-alerting")

    def test_list_filters_by_tag(self) -> None:
        response = self.client.get(
            "/api/v1/skills?tag=kubepodnotready", headers=self.auth
        )
        self.assertEqual(response.json()["total"], 1)

    def test_list_rejects_out_of_range_limit(self) -> None:
        response = self.client.get("/api/v1/skills?limit=101", headers=self.auth)
        self.assertEqual(response.status_code, 400)

    def test_list_rejects_negative_offset(self) -> None:
        response = self.client.get("/api/v1/skills?offset=-1", headers=self.auth)
        self.assertEqual(response.status_code, 400)

    # --- Search -------------------------------------------------------------

    def test_search_ranks_and_carries_provenance(self) -> None:
        response = self.client.get(
            "/api/v1/skills/search?q=KubePodNotReady", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        hit = body["matches"][0]
        self.assertEqual(hit["skill_id"], "sre-alerting/kubepodnotready")
        self.assertEqual(hit["source_id"], "sre-alerting")
        self.assertEqual(hit["source_path"], "KubePodNotReady.md")
        self.assertEqual(hit["source_ref"], "local")
        self.assertIn("updated_at", hit)
        self.assertIn("excerpt", hit)
        self.assertLessEqual(len(hit["excerpt"]), 401)
        self.assertNotIn("body", hit)

    def test_search_empty_result_is_success(self) -> None:
        response = self.client.get(
            "/api/v1/skills/search?q=zzz-not-a-skill", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["matches"], [])
        self.assertEqual(body["total"], 0)

    def test_search_requires_q(self) -> None:
        response = self.client.get("/api/v1/skills/search?q=", headers=self.auth)
        self.assertEqual(response.status_code, 400)

    def test_search_rejects_out_of_range_limit(self) -> None:
        response = self.client.get(
            "/api/v1/skills/search?q=pod&limit=21", headers=self.auth
        )
        self.assertEqual(response.status_code, 400)

    def test_search_requires_auth(self) -> None:
        response = self.client.get("/api/v1/skills/search?q=pod")
        self.assertEqual(response.status_code, 401)

    # --- Get ----------------------------------------------------------------

    def test_get_returns_full_record_with_body(self) -> None:
        response = self.client.get(
            "/api/v1/skills/sre-alerting/kubepodnotready", headers=self.auth
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "KubePodNotReady")
        self.assertIn("Check pod events", body["body"])

    def test_get_unknown_id_returns_404(self) -> None:
        response = self.client.get(
            "/api/v1/skills/sre-alerting/nope", headers=self.auth
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SKILL_NOT_FOUND")

    # --- Status / health ------------------------------------------------------

    def test_status_is_auth_exempt_and_reports_source(self) -> None:
        response = self.client.get("/api/v1/skills/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["store_backend"], "memory")
        (source,) = body["sources"]
        self.assertEqual(source["source_id"], "sre-alerting")
        self.assertEqual(source["accepted"], 2)
        self.assertEqual(source["rejections"], [])
        self.assertEqual(source["ref"], "local")

    def test_health_live(self) -> None:
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_ready_reports_store(self) -> None:
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["skill_count"], 2)
        self.assertEqual(body["source_count"], 1)


if __name__ == "__main__":
    unittest.main()
