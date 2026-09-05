"""SPEC-051 R-1/R-2/R-6: session-scoped browser-flow authority and context.

Pins the two per-process stores that back the platform-enforced flow-unlock
(one HITL gate per mutating browser flow): ``FlowContextStore`` reflects the
gateway-owned flow binding and yields the R-6 card headline plus the R-1 flow
identity; ``FlowApprovalStore`` records the operator's approval of a mutating
flow's first parked write, TTL-bounded and identity-scoped. Both fail safe —
a dropped/expired authority or a rebind means the next write re-parks.
"""

from __future__ import annotations

import time
import unittest

from agent_service.services import flow_approvals
from agent_service.services.flow_approvals import (
    BROWSER_WRITE_TOOLS,
    FLOW_APPROVALS,
    FLOW_CONTEXTS,
    FlowApproval,
    FlowApprovalStore,
    FlowContext,
    FlowContextStore,
)


def _flow_dict(**overrides):
    """A gateway ``FlowState.to_dict()``-shaped flow payload."""
    flow = {
        "skill_id": "samples/password-reset",
        "origin": "http://admin.local",
        "title": "Reset User Password",
        "description": "Reset a user's password in the admin portal",
        "flow_intent": "Submit the password reset for the user.",
        "risk_class": "write",
        "steps_used": 3,
        "max_steps": 20,
    }
    flow.update(overrides)
    return flow


def _approval(**overrides):
    kwargs = dict(
        session_id="ses-1",
        confirm_id="conf-1",
        owner_user_id="alice",
        decider_user_id="bob",
        skill_id="samples/password-reset",
        origin="http://admin.local",
        ttl=900.0,
    )
    kwargs.update(overrides)
    return FlowApproval(**kwargs)


class FlowContextTests(unittest.TestCase):
    def test_identity_is_skill_and_origin(self) -> None:
        context = FlowContext(
            session_id="ses-1", skill_id="skill-a", origin="http://x",
        )
        self.assertEqual(context.identity(), ("skill-a", "http://x"))

    def test_summary_carries_headline_fields(self) -> None:
        context = FlowContext(
            session_id="ses-1",
            skill_id="skill-a",
            origin="http://x",
            title="Reset Password",
            description="Reset a user's password",
            flow_intent="Submit the password reset for the user.",
            risk_class="write",
        )
        self.assertEqual(
            context.summary(),
            {
                "skill_id": "skill-a",
                "origin": "http://x",
                "title": "Reset Password",
                "description": "Reset a user's password",
                "flow_intent": "Submit the password reset for the user.",
                "risk_class": "write",
            },
        )

    def test_summary_keeps_empty_headline_defaults(self) -> None:
        """An empty title/description/flow_intent survive as empty strings so
        the portal can fall back gracefully rather than dropping the keys."""
        context = FlowContext(
            session_id="ses-1", skill_id="skill-a", origin="http://x",
        )
        summary = context.summary()
        self.assertEqual(summary["title"], "")
        self.assertEqual(summary["description"], "")
        self.assertEqual(summary["flow_intent"], "")
        self.assertEqual(summary["risk_class"], "read")


class FlowContextStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FlowContextStore()

    def test_record_and_get(self) -> None:
        context = self.store.record("ses-1", _flow_dict())
        self.assertIs(self.store.get("ses-1"), context)
        self.assertEqual(context.skill_id, "samples/password-reset")
        self.assertEqual(context.origin, "http://admin.local")
        self.assertEqual(context.title, "Reset User Password")
        self.assertEqual(context.flow_intent, "Submit the password reset for the user.")
        self.assertEqual(context.risk_class, "write")
        self.assertEqual(context.steps_used, 3)
        self.assertEqual(context.max_steps, 20)

    def test_record_overwrites_previous_identity(self) -> None:
        """A rebind to a different skill/origin replaces the identity — this
        is how the R-1 guard detects a flow change and re-parks the next
        write."""
        self.store.record("ses-1", _flow_dict())
        rebound = self.store.record(
            "ses-1",
            _flow_dict(skill_id="other/skill", origin="http://other.local"),
        )
        self.assertEqual(
            self.store.get("ses-1").identity(),
            ("other/skill", "http://other.local"),
        )
        self.assertNotEqual(rebound.identity(), ("samples/password-reset", "http://admin.local"))

    def test_record_from_partial_flow_dict_defaults(self) -> None:
        """Missing keys degrade to safe defaults rather than raising; a
        partial flow still yields a usable identity and empty headline."""
        context = self.store.record("ses-1", {"skill_id": "s", "origin": "o"})
        self.assertEqual(context.identity(), ("s", "o"))
        self.assertEqual(context.title, "")
        self.assertEqual(context.description, "")
        self.assertEqual(context.flow_intent, "")
        self.assertEqual(context.risk_class, "read")
        self.assertEqual(context.steps_used, 0)
        self.assertEqual(context.max_steps, 0)

    def test_record_coerces_numeric_fields(self) -> None:
        context = self.store.record(
            "ses-1", _flow_dict(steps_used="7", max_steps=None),
        )
        self.assertEqual(context.steps_used, 7)
        self.assertEqual(context.max_steps, 0)

    def test_get_unknown_session_returns_none(self) -> None:
        self.assertIsNone(self.store.get("nope"))

    def test_clear_removes_only_that_session(self) -> None:
        self.store.record("ses-1", _flow_dict())
        self.store.record("ses-2", _flow_dict(origin="http://two"))
        self.store.clear("ses-1")
        self.assertIsNone(self.store.get("ses-1"))
        self.assertIsNotNone(self.store.get("ses-2"))

    def test_clear_all(self) -> None:
        self.store.record("ses-1", _flow_dict())
        self.store.record("ses-2", _flow_dict())
        self.store.clear_all()
        self.assertIsNone(self.store.get("ses-1"))
        self.assertIsNone(self.store.get("ses-2"))


class FlowApprovalExpiryTests(unittest.TestCase):
    def test_identity_is_skill_and_origin(self) -> None:
        self.assertEqual(
            _approval().identity(),
            ("samples/password-reset", "http://admin.local"),
        )

    def test_not_expired_within_ttl(self) -> None:
        self.assertFalse(_approval(ttl=900.0).is_expired())

    def test_expired_when_ttl_zero_disables_unlock(self) -> None:
        """ttl <= 0 disables flow-unlock (the pre-fix posture): every write
        parks, so the authority is always expired."""
        self.assertTrue(_approval(ttl=0).is_expired())

    def test_expired_when_ttl_negative(self) -> None:
        self.assertTrue(_approval(ttl=-1).is_expired())

    def test_expired_after_ttl_lapse(self) -> None:
        """Backdate ``approved_at`` past the TTL — deterministic, no sleep."""
        stale = _approval(ttl=10.0, approved_at=time.monotonic() - 11.0)
        self.assertTrue(stale.is_expired())
        fresh = _approval(ttl=10.0, approved_at=time.monotonic() - 1.0)
        self.assertFalse(fresh.is_expired())


class FlowApprovalStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FlowApprovalStore()

    def _record(self, session_id="ses-1", **overrides):
        kwargs = dict(
            confirm_id="conf-1",
            owner_user_id="alice",
            decider_user_id="bob",
            skill_id="samples/password-reset",
            origin="http://admin.local",
            ttl=900.0,
        )
        kwargs.update(overrides)
        return self.store.record(session_id, **kwargs)

    def test_record_and_get(self) -> None:
        approval = self._record()
        self.assertIs(self.store.get("ses-1"), approval)
        self.assertEqual(approval.confirm_id, "conf-1")
        self.assertEqual(approval.decider_user_id, "bob")

    def test_has_approval_true_when_live(self) -> None:
        self._record()
        self.assertTrue(self.store.has_approval("ses-1"))

    def test_has_approval_false_when_absent(self) -> None:
        self.assertFalse(self.store.has_approval("nope"))

    def test_get_returns_none_when_expired(self) -> None:
        """An expired authority reads as absent so the caller fails safe."""
        self._record(ttl=0)
        self.assertIsNone(self.store.get("ses-1"))

    def test_has_approval_false_when_expired(self) -> None:
        self._record(ttl=0)
        self.assertFalse(self.store.has_approval("ses-1"))

    def test_record_overwrites_previous(self) -> None:
        self._record(confirm_id="conf-1")
        second = self._record(confirm_id="conf-2", decider_user_id="carol")
        self.assertEqual(self.store.get("ses-1").confirm_id, "conf-2")
        self.assertEqual(self.store.get("ses-1").decider_user_id, "carol")
        self.assertIs(self.store.get("ses-1"), second)

    def test_clear_removes_only_that_session(self) -> None:
        self._record("ses-1")
        self._record("ses-2")
        self.store.clear("ses-1")
        self.assertIsNone(self.store.get("ses-1"))
        self.assertIsNotNone(self.store.get("ses-2"))

    def test_clear_all(self) -> None:
        self._record("ses-1")
        self._record("ses-2")
        self.store.clear_all()
        self.assertFalse(self.store.has_approval("ses-1"))
        self.assertFalse(self.store.has_approval("ses-2"))


class BrowserWriteToolsTests(unittest.TestCase):
    def test_mutating_browser_tools_are_members(self) -> None:
        for name in (
            "web.click",
            "web.type",
            "web.select",
            "web.press_key",
            "web.upload_file",
            "web.evaluate",
        ):
            self.assertIn(name, BROWSER_WRITE_TOOLS)

    def test_read_tier_browser_tools_are_absent(self) -> None:
        """Read-tier probes ride the separate auto-allow path and must never
        appear in the write set, or they would wrongly arm flow-unlock."""
        for name in (
            "web.navigate",
            "web.snapshot",
            "web.screenshot",
            "web.fill_credential",
            "web.extract",
            "web.wait_for",
            "web.hover",
            "web.scroll",
            "web.switch_frame",
        ):
            self.assertNotIn(name, BROWSER_WRITE_TOOLS)

    def test_non_browser_tools_are_absent(self) -> None:
        self.assertNotIn("k8s.restart_service", BROWSER_WRITE_TOOLS)
        self.assertNotIn("k8s.delete_pod", BROWSER_WRITE_TOOLS)


class ModuleSingletonTests(unittest.TestCase):
    def test_process_wide_singletons_are_store_instances(self) -> None:
        self.assertIsInstance(FLOW_CONTEXTS, FlowContextStore)
        self.assertIsInstance(FLOW_APPROVALS, FlowApprovalStore)

    def test_as_int_coercion_helper(self) -> None:
        self.assertEqual(flow_approvals._as_int("12"), 12)
        self.assertEqual(flow_approvals._as_int(3.9), 3)
        self.assertEqual(flow_approvals._as_int(None), 0)
        self.assertEqual(flow_approvals._as_int("nope"), 0)


if __name__ == "__main__":
    unittest.main()
