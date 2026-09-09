"""Operations document proxy tests (SPEC-039 R-1/R-2/R-7, SPEC-043 R-3).

Covers the gateway-side gates for the document repository surface:
documents:create/documents:read policy enforcement, the SPEC-043
dual-action gate for incident reports (documents:create +
incident:read), the derived ``X-Foreign-Coverage`` capability on
create, upstream payload passthrough, error mapping (4xx passthrough
with the agent's structured detail, 502/503 passthrough, other 5xx and
transport to 502), and the owner session rename proxy behind
``session:update``.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from platform_gateway.app import create_app
from platform_gateway.core.config import PlatformGatewaySettings, get_settings
from platform_gateway.schemas.api import IdentityContext
from platform_gateway.services.policy_engine import (
    ACTION_DOCUMENTS_CREATE,
    ACTION_INCIDENT_READ,
    reset_policy_state,
)

DOCUMENTS_PATH = "/api/v1/documents"
CREATE_PATCH = "platform_gateway.services.gateway_service.agent_client.create_document"
ENFORCE_PATCH = "platform_gateway.api.routes.documents.enforce_policy"
LIST_PATCH = "platform_gateway.services.gateway_service.agent_client.list_documents"
FETCH_PATCH = "platform_gateway.services.gateway_service.agent_client.fetch_document"
PUBLISH_PATCH = "platform_gateway.services.gateway_service.agent_client.publish_document"
DELETE_PATCH = "platform_gateway.services.gateway_service.agent_client.delete_document"
TITLE_PATCH = (
    "platform_gateway.services.gateway_service.agent_client.update_session_title"
)
SKILL_DRAFT_PATCH = (
    "platform_gateway.services.gateway_service.agent_client.create_skill_draft"
)
SKILL_TARGET_PATCH = (
    "platform_gateway.services.gateway_service.agent_client.declare_skill_target"
)
INCIDENT_SKILL_DRAFT_PATCH = (
    "platform_gateway.services.gateway_service."
    "agent_client.create_incident_skill_draft"
)

CREATE_BODY = {
    "document_type": "shift_summary",
    "session_ids": ["ses-1", "ses-2"],
    "label": "night shift 2026-08-26",
    "include_prose": False,
}
INCIDENT_CREATE_BODY = {
    "document_type": "incident_report",
    "incident_id": "inc-abc123",
    "label": "payment latency post-mortem",
    "include_prose": False,
}
INCIDENT_DOCUMENT_PAYLOAD = {
    "document_id": "doc-9",
    "document_type": "incident_report",
    "state": "draft",
    "owner_user_id": "operator.user",
    "label": "payment latency post-mortem",
    "created_at": "2026-08-28T10:00:00Z",
    "provenance": {"incident_id": "inc-abc123", "sessions": []},
    "digest": {"incident": {"incident_id": "inc-abc123"}},
    "prose_status": "not_requested",
}
DOCUMENT_PAYLOAD = {
    "document_id": "doc-1",
    "document_type": "shift_summary",
    "state": "draft",
    "owner_user_id": "operator.user",
    "label": "night shift 2026-08-26",
    "created_at": "2026-08-26T22:00:00Z",
    "provenance": {"sessions": []},
    "digest": {"session_count": 2},
    "prose_status": "not_requested",
}
LIST_PAYLOAD = {"documents": [DOCUMENT_PAYLOAD]}


def _identity(role: str) -> IdentityContext:
    return IdentityContext(
        subject=f"user-{role}",
        username=f"{role}.user",
        roles=[role],
    )


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://agent-service/api/v2/documents")
    return httpx.HTTPStatusError(
        "upstream error", request=request, response=httpx.Response(status_code)
    )


def _status_error_json(status_code: int, payload: dict) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://agent-service/api/v2/documents")
    return httpx.HTTPStatusError(
        "upstream error",
        request=request,
        response=httpx.Response(status_code, json=payload, request=request),
    )


class DocumentsProxyBase(unittest.TestCase):
    def setUp(self) -> None:
        reset_policy_state()
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: PlatformGatewaySettings(
            require_auth=True
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_policy_state()

    def _patch_identity(self, role: str, route_module: str = "documents"):
        identity = _identity(role)

        async def fake_identity(settings, request, request_id):
            return identity

        return patch(
            f"platform_gateway.api.routes.{route_module}.resolve_request_identity",
            fake_identity,
        )


class CreateDocumentProxyTests(DocumentsProxyBase):
    def test_operator_create_forwards_denied_foreign_coverage(self) -> None:
        # Operators hold no approvals:list grant, so foreign sessions stay
        # out of reach: the derived coverage header must carry "denied".
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), DOCUMENT_PAYLOAD)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "operator.user")
        self.assertEqual(args[3], CREATE_BODY)
        self.assertEqual(args[4], "denied")

    def test_approver_create_forwards_allowed_foreign_coverage(self) -> None:
        # Approvers hold approvals:list, so the agent may cover foreign
        # sessions with metadata-only digest entries.
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("approver"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 201)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[4], "allowed")

    def test_developer_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("developer"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "documents:create")
        upstream.assert_not_called()

    def test_read_only_observer_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("read-only-observer"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_unknown_document_type_rejected_by_schema(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        body = dict(CREATE_BODY, document_type="runbook")
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=body)
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_upstream_403_passes_through(self) -> None:
        # Foreign-session denial from the agent reaches the caller as-is.
        upstream = AsyncMock(side_effect=_status_error(403))
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the document create"
        )

    def test_upstream_5xx_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "agent service document create failed"
        )

    def test_upstream_503_not_configured_passes_through(self) -> None:
        # SPEC-043: dependency-not-configured keeps its own status and
        # structured detail on the way to the caller.
        upstream = AsyncMock(
            side_effect=_status_error_json(
                503,
                {"detail": "incident service not configured for document assembly"},
            )
        )
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=INCIDENT_CREATE_BODY)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "incident service not configured for document assembly",
        )

    def test_upstream_404_unknown_incident_passes_through(self) -> None:
        # The structural 404 rides the agent's detail verbatim.
        upstream = AsyncMock(
            side_effect=_status_error_json(
                404, {"detail": "unknown incident id: inc-nope"}
            )
        )
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=INCIDENT_CREATE_BODY)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "unknown incident id: inc-nope"
        )

    def test_incident_report_enforces_dual_action_gate(self) -> None:
        # SPEC-043 R-3: incident reports require documents:create AND
        # incident:read; the payload (incident id included) reaches the
        # agent unchanged.
        upstream = AsyncMock(return_value=INCIDENT_DOCUMENT_PAYLOAD)
        enforced: list[str] = []

        def _record(settings, identity, action, request_id):
            enforced.append(action)

        with (
            self._patch_identity("operator"),
            patch(ENFORCE_PATCH, _record),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=INCIDENT_CREATE_BODY)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            enforced, [ACTION_DOCUMENTS_CREATE, ACTION_INCIDENT_READ]
        )
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[3], INCIDENT_CREATE_BODY)

    def test_shift_summary_skips_incident_gate(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        enforced: list[str] = []

        def _record(settings, identity, action, request_id):
            enforced.append(action)

        with (
            self._patch_identity("operator"),
            patch(ENFORCE_PATCH, _record),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(enforced, [ACTION_DOCUMENTS_CREATE])

    def test_incident_gate_denial_reports_incident_read(self) -> None:
        # A denial reports the first failing action in the same
        # structured shape as every other gate.
        upstream = AsyncMock(return_value=INCIDENT_DOCUMENT_PAYLOAD)

        def _deny_incident(settings, identity, action, request_id):
            if action == ACTION_INCIDENT_READ:
                raise HTTPException(
                    status_code=403,
                    detail={"action": action, "decision": "deny"},
                )

        with (
            self._patch_identity("operator"),
            patch(ENFORCE_PATCH, _deny_incident),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=INCIDENT_CREATE_BODY)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], ACTION_INCIDENT_READ)
        upstream.assert_not_called()

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator"),
            patch(CREATE_PATCH, upstream),
        ):
            response = self.client.post(DOCUMENTS_PATH, json=CREATE_BODY)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")


class ListDocumentsProxyTests(DocumentsProxyBase):
    def test_operator_lists_own_documents_with_default_scope(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(DOCUMENTS_PATH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), LIST_PAYLOAD)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "operator.user")
        self.assertEqual(args[3], "mine")

    def test_published_scope_forwards_verbatim(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(f"{DOCUMENTS_PATH}?scope=published")
        self.assertEqual(response.status_code, 200)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[3], "published")

    def test_unknown_scope_rejected_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(f"{DOCUMENTS_PATH}?scope=all")
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_developer_denied_documents_read(self) -> None:
        upstream = AsyncMock(return_value=LIST_PAYLOAD)
        with (
            self._patch_identity("developer"),
            patch(LIST_PATCH, upstream),
        ):
            response = self.client.get(DOCUMENTS_PATH)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "documents:read")
        upstream.assert_not_called()


class FetchDocumentProxyTests(DocumentsProxyBase):
    def test_operator_fetches_document(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("operator"),
            patch(FETCH_PATCH, upstream),
        ):
            response = self.client.get(f"{DOCUMENTS_PATH}/doc-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DOCUMENT_PAYLOAD)

    def test_upstream_404_passes_through(self) -> None:
        # The anti-enumeration 404 for unknown/foreign drafts must reach
        # the caller unchanged, not surface as a gateway 500.
        upstream = AsyncMock(side_effect=_status_error(404))
        with (
            self._patch_identity("operator"),
            patch(FETCH_PATCH, upstream),
        ):
            response = self.client.get(f"{DOCUMENTS_PATH}/doc-1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the document fetch"
        )

    def test_upstream_5xx_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(503))
        with (
            self._patch_identity("operator"),
            patch(FETCH_PATCH, upstream),
        ):
            response = self.client.get(f"{DOCUMENTS_PATH}/doc-1")
        self.assertEqual(response.status_code, 502)


class PublishDeleteProxyTests(DocumentsProxyBase):
    def test_operator_publishes_document(self) -> None:
        published = dict(DOCUMENT_PAYLOAD, state="published")
        upstream = AsyncMock(return_value=published)
        with (
            self._patch_identity("operator"),
            patch(PUBLISH_PATCH, upstream),
        ):
            response = self.client.post(f"{DOCUMENTS_PATH}/doc-1/publish")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "published")

    def test_repeat_publish_conflict_passes_through(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(409))
        with (
            self._patch_identity("operator"),
            patch(PUBLISH_PATCH, upstream),
        ):
            response = self.client.post(f"{DOCUMENTS_PATH}/doc-1/publish")
        self.assertEqual(response.status_code, 409)

    def test_operator_deletes_document(self) -> None:
        upstream = AsyncMock(return_value={"document_id": "doc-1", "deleted": True})
        with (
            self._patch_identity("operator"),
            patch(DELETE_PATCH, upstream),
        ):
            response = self.client.delete(f"{DOCUMENTS_PATH}/doc-1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])

    def test_developer_denied_publish(self) -> None:
        upstream = AsyncMock(return_value=DOCUMENT_PAYLOAD)
        with (
            self._patch_identity("developer"),
            patch(PUBLISH_PATCH, upstream),
        ):
            response = self.client.post(f"{DOCUMENTS_PATH}/doc-1/publish")
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()


class SessionRenameProxyTests(DocumentsProxyBase):
    def test_operator_renames_session_via_upstream(self) -> None:
        payload = {"session_id": "ses-1", "title": "DB failover triage"}
        upstream = AsyncMock(return_value=payload)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title",
                json={"title": "DB failover triage"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "ses-1")
        self.assertEqual(args[3], "operator.user")
        self.assertEqual(args[4], "DB failover triage")

    def test_observer_holds_session_update(self) -> None:
        # SPEC-039 R-7 mirrors session:list grants — the read-only
        # observer keeps the workspace lifecycle including rename.
        payload = {"session_id": "ses-1", "title": "read-only pass"}
        upstream = AsyncMock(return_value=payload)
        with (
            self._patch_identity("read-only-observer", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title", json={"title": "read-only pass"}
            )
        self.assertEqual(response.status_code, 200)

    def test_ungranted_role_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value={})
        with (
            self._patch_identity("auditor", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title", json={"title": "sneaky"}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["action"], "session:update")
        upstream.assert_not_called()

    def test_blank_title_rejected_by_schema(self) -> None:
        upstream = AsyncMock(return_value={})
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title", json={"title": ""}
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_upstream_404_passes_through(self) -> None:
        # Foreign/unknown sessions answer the anti-enumeration 404.
        upstream = AsyncMock(side_effect=_status_error(404))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title", json={"title": "nope"}
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"], "agent service rejected the session rename"
        )

    def test_upstream_5xx_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(TITLE_PATCH, upstream),
        ):
            response = self.client.patch(
                "/api/v1/sessions/ses-1/title", json={"title": "boom"}
            )
        self.assertEqual(response.status_code, 502)


class SkillTargetProxyTests(DocumentsProxyBase):
    """SPEC-055 R-4: skill-development target declaration pass-through behind
    ``session:skill_graduate``.

    The declaration scopes a develop-as-you-go session *before* it mutates
    anything, which is what makes it an authorization scope rather than a
    post-hoc claim. Two properties matter at the gateway and nowhere else:
    the target is relayed verbatim (the operator's path narrowing is part of
    the scope), and the response reports the target actually in force rather
    than echoing the request — a UI that showed the request back would let an
    operator believe they had widened a scope they cannot widen.
    """

    TARGET = "https://admin.internal/login"
    DECLARATION_PAYLOAD = {
        "session_id": "ses-1",
        "target": TARGET,
        "already_declared": False,
    }

    def _post(self, target: str = TARGET, session_id: str = "ses-1"):
        return self.client.post(
            f"/api/v1/sessions/{session_id}/skill-target",
            json={"target": target},
        )

    def test_operator_declares_target_verbatim(self) -> None:
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.DECLARATION_PAYLOAD)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "ses-1")
        self.assertEqual(args[3], "operator.user")
        # Verbatim: no normalization, no truncation. The gateway holds no
        # origin_of_url, so the agent layer is the only place that judges
        # shape — a gateway that lowercased or stripped the path here would
        # silently widen the graduated skill's scope.
        self.assertEqual(args[4], self.TARGET)

    def test_a_path_narrowed_target_survives_the_hop(self) -> None:
        """The verbatim property under a target whose path *is* the scope."""
        narrowed = "https://admin.internal/console/settings"
        upstream = AsyncMock(
            return_value={
                "session_id": "ses-1",
                "target": narrowed,
                "already_declared": False,
            }
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(target=narrowed)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target"], narrowed)
        self.assertEqual(upstream.mock_calls[0][1][4], narrowed)

    def test_the_effective_target_is_relayed_not_echoed(self) -> None:
        """First declaration wins, and the caller sees the winner.

        The request names ``elsewhere.internal``; the response must name the
        target in force. Relaying the upstream body verbatim is what makes
        that true without the gateway holding any declaration state.
        """
        upstream = AsyncMock(
            return_value={
                "session_id": "ses-1",
                "target": self.TARGET,
                "already_declared": True,
            }
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(target="https://elsewhere.internal/admin")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["target"], self.TARGET)
        self.assertTrue(response.json()["already_declared"])

    def test_observer_denied_before_upstream(self) -> None:
        # Graduating a trace into an executable-flow skill is an operational
        # act of a higher trust level than drafting prose: read-only-observer
        # holds no session:skill_graduate grant, and declaring its target is
        # the first half of the same capability.
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("read-only-observer", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["action"], "session:skill_graduate"
        )
        upstream.assert_not_called()

    def test_developer_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("developer", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_approver_and_platform_admin_may_declare(self) -> None:
        """The bundle grants graduation to all three operational roles."""
        for role in ("platform-admin", "approver"):
            with self.subTest(role=role):
                reset_policy_state()
                upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
                with (
                    self._patch_identity(role, route_module="sessions"),
                    patch(SKILL_TARGET_PATCH, upstream),
                ):
                    response = self._post()
                self.assertEqual(response.status_code, 200)
                upstream.assert_called_once()

    def test_upstream_422_no_origin_passes_through_with_detail(self) -> None:
        """A target with no normalizable origin could never be corroborated
        against the session's captured steps, so the agent layer's reasoning
        rides to the operator verbatim rather than being flattened."""
        upstream = AsyncMock(
            side_effect=_status_error_json(
                422,
                {"detail": "skill target must be an absolute http(s) URL"},
            )
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(target="admin.internal/login")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"], "skill target must be an absolute http(s) URL"
        )

    def test_upstream_404_passes_through_with_detail(self) -> None:
        # Foreign/unknown sessions answer the anti-enumeration 404.
        upstream = AsyncMock(
            side_effect=_status_error_json(404, {"detail": "session not found"})
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(session_id="ses-foreign")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "session not found")

    def test_upstream_503_maps_to_502(self) -> None:
        """A deliberate divergence from the skill-draft proxy, in the status
        only.

        There a 503 is a *domain* outcome — skills-hub is not configured, so
        an unvalidated draft is never returned — and rides through verbatim.
        A declaration reaches no downstream validation leg, so a 503 here is
        just an unhealthy upstream and collapses to the house 502 rather than
        implying a validation posture this route does not have. The upstream's
        own reason still rides through ``_upstream_detail``: flattening the
        status must not cost the operator the explanation.
        """
        upstream = AsyncMock(
            side_effect=_status_error_json(
                503, {"detail": "skills service not configured"}
            )
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "skills service not configured"
        )

    def test_an_unlegible_upstream_5xx_falls_back(self) -> None:
        """With no legible body there is nothing to relay, so the house
        fallback names the operation rather than a generic gateway error."""
        upstream = AsyncMock(side_effect=_status_error(503))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "agent service skill target failed"
        )

    def test_upstream_500_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")

    def test_a_blank_target_is_refused_at_the_gateway(self) -> None:
        # The gateway's own body contract, so the upstream is never reached.
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(target="")
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_an_overlong_target_is_refused_at_the_gateway(self) -> None:
        """Capped at the skill contract's own ``web_target`` bound, so a
        target this route accepts can always be emitted into a draft."""
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self._post(target="https://admin.internal/" + "a" * 2048)
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_an_unknown_body_field_is_refused(self) -> None:
        """``extra="forbid"``: a misspelled field must not be silently
        dropped, or an operator would believe they had scoped a session with
        a declaration that never carried the field they meant."""
        upstream = AsyncMock(return_value=self.DECLARATION_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_TARGET_PATCH, upstream),
        ):
            response = self.client.post(
                "/api/v1/sessions/ses-1/skill-target",
                json={"target": self.TARGET, "web_target": self.TARGET},
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()


class SessionBirthTargetProxyTests(DocumentsProxyBase):
    """SPEC-055 R-4: ``skill_target`` on session create — the primary
    declaration path, because at birth nothing can have been captured yet.

    These pin the two things the gateway is responsible for on this path:
    relaying the target verbatim, and mapping the agent's refusal properly.
    The second is not a formality — ``create_session`` carried no error mapping
    before R-4, which was harmless while the upstream could only answer 201,
    but a target with no normalizable origin is refused *by the agent layer*
    and would otherwise have surfaced as an unhandled upstream error, answering
    the operator 500 for a 422 they could have acted on.
    """

    CREATE_PAYLOAD = {"session_id": "ses-1", "user_id": "operator.user"}
    CREATE_PATCH = (
        "platform_gateway.services.gateway_service.agent_client.create_session"
    )

    def test_a_birth_target_is_forwarded_verbatim(self) -> None:
        upstream = AsyncMock(return_value=self.CREATE_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post(
                "/api/v1/sessions",
                json={"skill_target": "https://admin.internal/login"},
            )
        self.assertEqual(response.status_code, 200)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "operator.user")
        self.assertEqual(args[3], "https://admin.internal/login")

    def test_an_unscoped_create_forwards_no_target(self) -> None:
        """The historical call shape: an ordinary chat session declares
        nothing, and the gateway must not invent a scope for it."""
        upstream = AsyncMock(return_value=self.CREATE_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(upstream.mock_calls[0][1][3])

    def test_an_upstream_422_on_create_passes_through(self) -> None:
        """A well-formed, in-bounds target with no normalizable origin is the
        agent layer's judgement, and its reasoning rides to the operator."""
        upstream = AsyncMock(
            side_effect=_status_error_json(
                422,
                {"detail": "skill target must be an absolute http(s) URL"},
            )
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post(
                "/api/v1/sessions", json={"skill_target": "admin.internal/login"}
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"], "skill target must be an absolute http(s) URL"
        )

    def test_an_upstream_500_on_create_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 502)

    def test_a_transport_failure_on_create_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")

    def test_an_overlong_birth_target_is_refused_at_the_gateway(self) -> None:
        upstream = AsyncMock(return_value=self.CREATE_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post(
                "/api/v1/sessions",
                json={"skill_target": "https://admin.internal/" + "a" * 2048},
            )
        self.assertEqual(response.status_code, 422)
        upstream.assert_not_called()

    def test_an_observer_may_scope_their_own_session(self) -> None:
        """Deliberate, and the reason this route is not dual-gated.

        Declaring a scope is inert — it grants nothing and only narrows what a
        later graduation may emit — while dual-gating with
        ``session:skill_graduate`` would refuse *session creation itself* over
        an inert field. Graduation stays gated; this does not.
        """
        upstream = AsyncMock(return_value=self.CREATE_PAYLOAD)
        with (
            self._patch_identity("read-only-observer", route_module="sessions"),
            patch(self.CREATE_PATCH, upstream),
        ):
            response = self.client.post(
                "/api/v1/sessions", json={"skill_target": "https://admin.internal/x"}
            )
        self.assertEqual(response.status_code, 200)
        upstream.assert_called_once()


class SkillDraftProxyTests(DocumentsProxyBase):
    """SPEC-044 R-3/R-4: skill-draft pass-through behind session:skill_draft."""

    SKILL_DRAFT_PAYLOAD = {
        "markdown": "---\ntitle: \"Restart checkout\"\n---\n\nBody\n",
        "mode": "generated",
        "validation": "passed",
        "suggested_filename": "restart-checkout.md",
    }

    def test_operator_drafts_skill_verbatim(self) -> None:
        upstream = AsyncMock(return_value=self.SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.SKILL_DRAFT_PAYLOAD)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "ses-1")
        self.assertEqual(args[3], "operator.user")

    def test_observer_denied_before_upstream(self) -> None:
        # Drafting skills is an operational act: read-only-observer holds
        # no session:skill_draft grant (documents-create pattern).
        upstream = AsyncMock(return_value=self.SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("read-only-observer", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["action"], "session:skill_draft"
        )
        upstream.assert_not_called()

    def test_developer_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=self.SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("developer", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_upstream_404_passes_through_with_detail(self) -> None:
        # Foreign/unknown sessions answer the anti-enumeration 404 with
        # the agent's structured detail.
        upstream = AsyncMock(
            side_effect=_status_error_json(404, {"detail": "session not found"})
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-foreign/skill-draft")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "session not found")

    def test_upstream_503_not_configured_passes_through(self) -> None:
        # An unvalidated draft is never returned; the dependency posture
        # rides verbatim to the caller.
        upstream = AsyncMock(
            side_effect=_status_error_json(
                503,
                {"detail": "skills service not configured for skill-draft validation"},
            )
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "skills service not configured for skill-draft validation",
        )

    def test_upstream_502_validation_unreachable_passes_through(self) -> None:
        upstream = AsyncMock(
            side_effect=_status_error_json(
                502, {"detail": "skills service unreachable"}
            )
        )
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "skills service unreachable")

    def test_upstream_500_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", route_module="sessions"),
            patch(SKILL_DRAFT_PATCH, upstream),
        ):
            response = self.client.post("/api/v1/sessions/ses-1/skill-draft")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")


class IncidentSkillDraftProxyTests(DocumentsProxyBase):
    """SPEC-045 R-2/R-3: incident-anchored skill drafts behind the dual
    ``incident:skill_draft`` + ``incident:read`` gate."""

    INCIDENT_SKILL_DRAFT_PAYLOAD = {
        "markdown": "---\ntitle: \"Triage runbook: Checkout latency\"\n---\n\nBody\n",
        "mode": "generated",
        "validation": "passed",
        "suggested_filename": "triage-runbook-checkout-latency.md",
    }

    def _post(self, incident_id: str = "inc-abc123"):
        return self.client.post(f"/api/v1/incidents/{incident_id}/skill-draft")

    def test_operator_drafts_incident_skill_verbatim(self) -> None:
        upstream = AsyncMock(return_value=self.INCIDENT_SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.INCIDENT_SKILL_DRAFT_PAYLOAD)
        _, args, _ = upstream.mock_calls[0]
        self.assertEqual(args[2], "inc-abc123")
        self.assertEqual(args[3], "operator.user")

    def test_observer_denied_reports_first_failing_action(self) -> None:
        # read-only-observer holds incident:read but not
        # incident:skill_draft; the denial names the first failing
        # action (dual-gate order: incident:skill_draft first).
        upstream = AsyncMock(return_value=self.INCIDENT_SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("read-only-observer", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["action"], "incident:skill_draft"
        )
        upstream.assert_not_called()

    def test_developer_denied_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=self.INCIDENT_SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("developer", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_invalid_incident_id_rejected_before_upstream(self) -> None:
        upstream = AsyncMock(return_value=self.INCIDENT_SKILL_DRAFT_PAYLOAD)
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post(incident_id="not-an-incident")
        self.assertEqual(response.status_code, 400)
        upstream.assert_not_called()

    def test_upstream_409_triage_gate_passes_through(self) -> None:
        # The deterministic 409 names the precondition, not a failure.
        upstream = AsyncMock(
            side_effect=_status_error_json(
                409,
                {
                    "detail": "no validated triage report to draft from "
                    "— run triage first"
                },
            )
        )
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 409)
        self.assertIn("run triage first", response.json()["detail"])

    def test_upstream_404_passes_through_with_detail(self) -> None:
        upstream = AsyncMock(
            side_effect=_status_error_json(404, {"detail": "incident not found"})
        )
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post(incident_id="inc-missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "incident not found")

    def test_upstream_503_not_configured_passes_through(self) -> None:
        upstream = AsyncMock(
            side_effect=_status_error_json(
                503,
                {"detail": "skills service not configured for skill-draft validation"},
            )
        )
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 503)

    def test_upstream_502_validation_unreachable_passes_through(self) -> None:
        upstream = AsyncMock(
            side_effect=_status_error_json(
                502, {"detail": "skills service unreachable"}
            )
        )
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "skills service unreachable")

    def test_upstream_500_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=_status_error(500))
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)

    def test_transport_failure_maps_to_502(self) -> None:
        upstream = AsyncMock(side_effect=httpx.ConnectError("boom"))
        with (
            self._patch_identity("operator", route_module="incidents"),
            patch(INCIDENT_SKILL_DRAFT_PATCH, upstream),
        ):
            response = self._post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "agent service unavailable")


if __name__ == "__main__":
    unittest.main()
