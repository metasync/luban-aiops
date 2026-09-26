"""Deliberately unsafe test-only senders; safety assertions must reject them."""
from __future__ import annotations

import os

import httpx


def assert_single_dispatch(gateway, target):
    assert gateway["attempt"] <= 1, "duplicate worker dispatch detected"
    assert target["accepted"] <= 1, "duplicate target acceptance detected"
    assert target["effect"] <= 1, "duplicate non-idempotent effect detected"


def assert_honest_no_effect(state, target):
    assert not (state == "not_dispatched" and target["effect"]), "false no-effect certainty"


def assert_no_replay_release(releases):
    assert releases == 0, "replay released a held secret"


def bypass_claim(url, token, ready, send):
    """Each process knowingly ignores any claim. Not imported by runtime code."""
    ready.set()
    if not send.wait(15):
        raise TimeoutError("negative-control send watchdog expired")
    with httpx.Client(trust_env=False, timeout=10, follow_redirects=False) as client:
        response = client.post(url + "/api/v2/tools/invoke",
                               headers={"Authorization": f"Bearer {token}"},
                               json={"tool_name": "test.increment", "parameters": {},
                                     "request_id": f"control-{os.getpid()}"})
        response.raise_for_status()
