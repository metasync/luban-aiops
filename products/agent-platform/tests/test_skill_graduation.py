"""SPEC-055 R-4: skill graduation from a session's authoring trace.

Covers the route-level posture of the graduation surface, which mirrors
SPEC-044's skill-draft route: ownership re-checked server-side so a
foreign or unknown session answers the structural 404, a deterministic
refusal rather than a 500 for a trace that cannot graduate, and an
artifact that is validated on skills-hub's own ingestion path before it
reaches the operator (never auto-published).

It also covers the surface R-4 depends on and SPEC-044 had no analogue
for: the **declared target**. A develop-as-you-go session names the web
target it works against *before* mutating anything, which is what makes
the declaration an authorization scope rather than a post-hoc claim about
the past — graduation emits it as the draft's ``web_target``, the security
parameter a replayed flow binds its origin guard and step budget to, and
R-2's per-step observations corroborate every captured mutation against
it. There are two paths to that declaration: at session birth (the primary
one, where nothing can have been captured yet) and through a standalone
endpoint afterwards, for a *development* session opened unscoped — SPEC-056
R-2/R-3 made the birth target optional, and neither path re-types anything,
since ``session_type`` is fixed at birth. Both are first-wins, both report
the target actually in force rather than echoing the request, and both run
one validator that holds the scope as origin and path with any query or
fragment dropped.

The service underneath the route is covered here too, because it is where
R-4's substance lives. ``revalidate_blast_radius`` re-applies at graduation
the guards the tool-gateway applies at replay, and its refusals are the
operator's only explanation of why a session they spent an hour on cannot
become a skill — so each guard is asserted individually, and so is the
property that a trace failing several guards is told about all of them at
once. ``build_executable_flow_draft`` is asserted deterministic over a fixed
trace: it is a rendering of what a human already approved, never a synthesis,
and a document that differs between two runs would make a re-graduation a
different artifact from the one already reviewed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_service.api.v2 import routes as v2_routes
from agent_service.app import create_app
from agent_service.runtime_settings import RuntimeSettings
from agent_service.services.authoring_trace import (
    AUTHORING_TRACE_STORE,
    TRACE_DISCARDED,
    TRACE_DRAFT,
    TRACE_GRADUATED,
    make_trace_step,
)
from agent_service.services.operation_documents import OPERATION_DOCUMENT_STORE
from agent_service.services.secret_params import (
    TRACE_CREDENTIAL_PLACEHOLDER,
    parameterize_for_trace,
)
from agent_service.services.session_store import SESSION_STORE
from agent_service.services.skill_draft import MAX_BODY_BYTES
from agent_service.services.skill_graduation import (
    DEFAULT_MAX_GRADUATION_STEPS,
    DECLARATION_INDETERMINATE,
    DECLARATION_POSTDATED,
    DECLARATION_PRECEDED,
    MAX_STEPS_BYTES,
    MODE_GRADUATED,
    build_executable_flow_draft,
    revalidate_blast_radius,
)

TARGET = "https://admin.internal/login"
# A stamp safely before any declaration this process makes: the store stamps
# ``declared_at`` from the real clock, so a test that wants a *postdated*
# declaration moves the step stamps into the past rather than patching a clock.
PAST = "2020-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _clean_stores():
    """Isolate the process-wide session, trace and document singletons.

    All three are module-level singletons, so a session, a target declaration
    or a published document leaked from another test would make a first-wins
    or a never-published assertion here read state this test never wrote.
    """
    spaces = [
        getattr(SESSION_STORE, "_sessions", None),
        getattr(SESSION_STORE, "_last_accessed", None),
        getattr(AUTHORING_TRACE_STORE, "_by_session", None),
        getattr(AUTHORING_TRACE_STORE, "_targets", None),
        getattr(OPERATION_DOCUMENT_STORE, "_by_document_id", None),
    ]
    for space in spaces:
        if space is not None:
            space.clear()
    yield
    for space in spaces:
        if space is not None:
            space.clear()


def _make_session(client: TestClient, user: str) -> str:
    response = client.post("/api/v2/sessions", headers={"X-User-ID": user})
    assert response.status_code == 201
    return response.json()["session_id"]


def _create(client: TestClient, body: dict, user: str = "alice"):
    return client.post("/api/v2/sessions", headers={"X-User-ID": user}, json=body)


def _declare(client: TestClient, session_id: str, target: str, user: str = "alice"):
    return client.post(
        f"/api/v2/sessions/{session_id}/skill-target",
        headers={"X-User-ID": user},
        json={"target": target},
    )


# --- The declared target (SPEC-055 R-4) -------------------------------------


class TestDeclareSkillTarget:
    TARGET = "https://admin.internal/login"

    def test_declaring_a_target_stores_it_for_the_session(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, self.TARGET)

        assert response.status_code == 200
        assert response.json() == {
            "session_id": session_id,
            "target": self.TARGET,
            "already_declared": False,
        }
        # Stored as declared: the operator's path narrowing is part of the
        # scope and must survive into the draft's ``web_target``. Normalizing
        # to a bare origin here would silently widen the graduated skill to
        # every path on the host.
        assert AUTHORING_TRACE_STORE.trace_target(session_id) == self.TARGET

    def test_the_first_declaration_wins(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        assert _declare(client, session_id, self.TARGET).status_code == 200

        second = _declare(client, session_id, "https://elsewhere.internal/admin")

        assert second.status_code == 200
        body = second.json()
        # The response reports the target actually in force, never an echo of
        # the request: a scope an operator could move after the fact would
        # corroborate nothing, and a UI that showed the request back would let
        # them believe they had moved one they cannot move.
        assert body["target"] == self.TARGET
        assert body["already_declared"] is True
        assert AUTHORING_TRACE_STORE.trace_target(session_id) == self.TARGET

    def test_a_foreign_session_answers_structural_404(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, self.TARGET, user="bob")

        assert response.status_code == 404
        # Nothing was stored under the owner's session by the failed call.
        assert AUTHORING_TRACE_STORE.trace_target(session_id) is None

    def test_an_unknown_session_answers_404(self) -> None:
        client = TestClient(create_app())

        assert _declare(client, "ses-missing", self.TARGET).status_code == 404

    def test_a_caller_without_identity_answers_401(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = client.post(
            f"/api/v2/sessions/{session_id}/skill-target",
            json={"target": self.TARGET},
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "target",
        [
            # No normalizable origin ⇒ nothing to corroborate the captured
            # steps against ⇒ refused at the point of input rather than
            # surviving to an opaque refusal at graduation.
            "admin.internal/login",
            "/login",
            "file:///etc/passwd",
            "ftp://admin.internal/x",
            "javascript:alert(1)",
            "   ",
        ],
    )
    def test_a_target_with_no_origin_is_refused(self, target: str) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, target)

        assert response.status_code == 422
        assert AUTHORING_TRACE_STORE.trace_target(session_id) is None

    def test_a_target_whose_credentials_were_its_whole_netloc_is_refused(
        self,
    ) -> None:
        """``https://u:p@/path`` has an origin as typed and none once scoped.

        The shape check judges the value that will actually be stored rather
        than the paste, so this is refused: admitting it would persist a scope
        with no origin, which no observed step can ever corroborate and which
        graduation could only refuse opaquely, later, after the operator had
        done the work.
        """
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, "https://u:p@/path")

        assert response.status_code == 422
        assert AUTHORING_TRACE_STORE.trace_target(session_id) is None

    def test_a_url_that_urlparse_itself_rejects_answers_422_not_500(
        self,
    ) -> None:
        """Scoping runs before the shape check, so a malformed URL meets
        ``urlparse`` inside ``skill_target_scope`` first. An uncaught
        ``ValueError`` there would answer a 500 to what is an operator input
        error, and would read as a platform fault in the portal."""
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        # An unterminated IPv6 literal: ``urlparse`` raises "Invalid IPv6 URL".
        response = _declare(client, session_id, "https://[::1")

        assert response.status_code == 422
        assert AUTHORING_TRACE_STORE.trace_target(session_id) is None

    def test_a_well_formed_ipv6_target_is_accepted(self) -> None:
        """The refusal above is about the malformed literal, not IPv6: a
        bracketed host is a legitimate target and its brackets must survive
        scoping, or the origin comparison would never match."""
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, "https://[::1]:8443/admin?x=1")

        assert response.status_code == 200
        assert response.json()["target"] == "https://[::1]:8443/admin"

    def test_a_blank_target_is_refused_by_the_body_contract(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        # ``min_length=1`` on the schema, so this is a 422 from the contract
        # before the route runs.
        response = client.post(
            f"/api/v2/sessions/{session_id}/skill-target",
            headers={"X-User-ID": "alice"},
            json={"target": ""},
        )

        assert response.status_code == 422

    def test_an_overlong_target_is_refused_by_the_body_contract(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        # Capped at the skill contract's own ``web_target`` bound (2048), so
        # a target this route accepts can always be emitted into a draft.
        response = _declare(
            client, session_id, "https://admin.internal/" + "a" * 2048
        )

        assert response.status_code == 422

    def test_surrounding_whitespace_is_trimmed_before_storing(self) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, f"  {self.TARGET}  ")

        assert response.status_code == 200
        assert response.json()["target"] == self.TARGET

    def test_declarations_are_session_scoped(self) -> None:
        client = TestClient(create_app())
        first = _make_session(client, "alice")
        second = _make_session(client, "alice")
        _declare(client, first, self.TARGET)

        _declare(client, second, "https://other.internal/console")

        assert AUTHORING_TRACE_STORE.trace_target(first) == self.TARGET
        assert (
            AUTHORING_TRACE_STORE.trace_target(second)
            == "https://other.internal/console"
        )

    def test_declaring_needs_no_skills_hub_validation_leg(self) -> None:
        """A declaration scopes a session; it produces no artifact to validate.

        Refusing it because an unrelated downstream is unconfigured would
        block an operator from scoping their session for no reason — the 503
        belongs at graduation, where the draft actually meets the ingestion
        rules. Asserted structurally: the route holds no validation
        dependency at all, so there is nothing to be unconfigured.
        """
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, self.TARGET)

        assert response.status_code == 200

    def test_a_port_and_uppercase_host_normalize_for_corroboration(self) -> None:
        """The declaration is stored as declared, but what graduation compares
        is its origin — so a target whose host case or explicit port differs
        from the gateway's normalization must still corroborate.

        Pins the twin relationship with the tool-gateway's ``origin_of``: a
        divergence would make a coherent trace look like a drift.
        """
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(
            client, session_id, "https://Admin.Internal:8443/Login"
        )

        assert response.status_code == 200
        # Stored as declared, so the operator's path narrowing survives...
        assert response.json()["target"] == "https://Admin.Internal:8443/Login"
        # ...and its origin is what the per-step observations are compared to.
        from agent_service.services.authoring_trace import origin_of_url

        assert origin_of_url(response.json()["target"]) == (
            "https://admin.internal:8443"
        )

    @pytest.mark.parametrize(
        ("declared", "stored"),
        [
            # A query is inert at replay — ``bind_flow`` reads origin and path
            # only — so persisting one would advertise a narrowing that does
            # not exist, and an address-bar paste is where a credential rides.
            (
                "https://admin.internal/login?token=hunter2",
                "https://admin.internal/login",
            ),
            (
                "https://admin.internal/login#results",
                "https://admin.internal/login",
            ),
            (
                "https://admin.internal/login?next=/admin#results",
                "https://admin.internal/login",
            ),
            # The path narrowing survives the strip: dropping it would widen
            # the graduated skill to every path on the host.
            (
                "https://admin.internal/console/users?page=2",
                "https://admin.internal/console/users",
            ),
            # Embedded credentials are the other place a paste carries a
            # secret, and they are unusable besides: ``origin_of_url`` keeps
            # the netloc verbatim, so a userinfo origin could never equal the
            # credential-free one the gateway reports a browser landed on.
            (
                "https://alice:hunter2@admin.internal/login",
                "https://admin.internal/login",
            ),
            # Nothing to strip is stored unchanged.
            ("https://admin.internal/login", "https://admin.internal/login"),
        ],
    )
    def test_only_the_bound_scope_reaches_the_store(
        self, declared: str, stored: str
    ) -> None:
        """A declared target is held as origin and path, never with a query or
        embedded credentials.

        The declaration reaches this store from the operator's own input
        rather than through the gateway's result redaction, so nothing
        upstream has masked a credential in it — and the row outlives every
        execution receipt (ADR-0009) and is named in the ``skill_graduated``
        audit payload.
        """
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")

        response = _declare(client, session_id, declared)

        assert response.status_code == 200
        # The response reports what is in force, so an operator sees the scope
        # that was actually stored rather than the string they pasted.
        assert response.json()["target"] == stored
        assert AUTHORING_TRACE_STORE.trace_target(session_id) == stored


# --- The birth declaration (SPEC-055 R-4) -----------------------------------


class TestDeclareAtSessionBirth:
    """``skill_target`` on session create — the primary declaration path.

    Declaring at birth is what makes the target an authorization scope rather
    than a claim fitted to the trace afterwards: the session does not exist to
    mutate until the create returns, so no captured step can predate it. The
    standalone endpoint cannot offer that, which is why graduation checks the
    ordering instead of assuming it.
    """

    TARGET = "https://admin.internal/login"

    def test_creating_a_session_with_a_target_declares_it(self) -> None:
        client = TestClient(create_app())

        response = _create(client, {"skill_target": self.TARGET})

        assert response.status_code == 201
        session_id = response.json()["session_id"]
        assert AUTHORING_TRACE_STORE.trace_target(session_id) == self.TARGET
        # The structural property, observable: the scope is in force while the
        # trace is still empty, so nothing was captured before it was declared.
        assert AUTHORING_TRACE_STORE.load_for_session(session_id) == []

    def test_a_named_session_can_be_born_scoped(self) -> None:
        """SPEC-015 R-3 named sessions are develop-as-you-go sessions too."""
        client = TestClient(create_app())

        response = _create(
            client, {"session_id": "ses-dev-checkout", "skill_target": self.TARGET}
        )

        assert response.status_code == 201
        assert response.json()["session_id"] == "ses-dev-checkout"
        assert (
            AUTHORING_TRACE_STORE.trace_target("ses-dev-checkout") == self.TARGET
        )

    def test_a_session_created_without_a_target_has_no_declaration(self) -> None:
        """The historical shape is untouched: an ordinary chat session carries
        no scope, and graduation will see no declaration and refuse."""
        client = TestClient(create_app())

        response = _create(client, {})

        assert response.status_code == 201
        session_id = response.json()["session_id"]
        assert AUTHORING_TRACE_STORE.trace_target(session_id) is None

    def test_an_unscoped_create_still_omits_the_declaration(self) -> None:
        client = TestClient(create_app())

        response = _create(client, {"skill_target": None})

        assert response.status_code == 201
        assert (
            AUTHORING_TRACE_STORE.trace_target(response.json()["session_id"])
            is None
        )

    @pytest.mark.parametrize(
        "target",
        [
            "admin.internal/login",
            "/login",
            "file:///etc/passwd",
            "   ",
            # The two shapes the scoping step can turn into a target with no
            # origin: credentials that were the whole netloc, and a literal
            # ``urlparse`` rejects outright (a 422, never a 500).
            "https://u:p@/path",
            "https://[::1",
        ],
    )
    def test_an_invalid_target_refuses_the_create_whole(self, target: str) -> None:
        """Shape is checked *before* the session exists.

        A refused target must not leave a half-created session behind: an
        operator whose develop-as-you-go session failed to open should have no
        session at all, not an unscoped one they might start mutating in the
        belief it was the one they asked for.
        """
        client = TestClient(create_app())
        before = len(SESSION_STORE._sessions)

        response = _create(client, {"skill_target": target})

        assert response.status_code == 422
        assert len(SESSION_STORE._sessions) == before
        assert AUTHORING_TRACE_STORE._targets == {}

    def test_an_overlong_target_is_refused_by_the_body_contract(self) -> None:
        client = TestClient(create_app())

        response = _create(
            client, {"skill_target": "https://admin.internal/" + "a" * 2048}
        )

        assert response.status_code == 422
        assert len(SESSION_STORE._sessions) == 0

    def test_a_caller_without_identity_cannot_declare(self) -> None:
        client = TestClient(create_app())

        response = client.post("/api/v2/sessions", json={"skill_target": self.TARGET})

        assert response.status_code == 401
        assert AUTHORING_TRACE_STORE._targets == {}

    def test_recreating_a_named_session_cannot_move_the_scope(self) -> None:
        """``create_named_session`` is idempotent for the owner, so a repeat
        create is a real path to a second declaration attempt — first-wins must
        hold through it, or an operator could widen a scope by re-opening the
        session rather than by declaring again."""
        client = TestClient(create_app())
        body = {"session_id": "ses-dev-scoped", "skill_target": self.TARGET}
        assert _create(client, body).status_code == 201

        again = _create(
            client,
            {
                "session_id": "ses-dev-scoped",
                "skill_target": "https://elsewhere.internal/admin",
            },
        )

        assert again.status_code == 201
        assert again.json()["session_id"] == "ses-dev-scoped"
        assert (
            AUTHORING_TRACE_STORE.trace_target("ses-dev-scoped") == self.TARGET
        )

    def test_a_later_standalone_declaration_cannot_move_a_birth_scope(self) -> None:
        """The two paths share one first-wins invariant: whichever declared
        first holds, and the birth path is normally the one that did."""
        client = TestClient(create_app())
        session_id = _create(client, {"skill_target": self.TARGET}).json()[
            "session_id"
        ]

        response = _declare(
            client, session_id, "https://elsewhere.internal/admin"
        )

        assert response.status_code == 200
        assert response.json()["already_declared"] is True
        assert response.json()["target"] == self.TARGET

    def test_a_birth_scope_can_still_be_read_back_by_the_endpoint(self) -> None:
        """One store, so the standalone endpoint reports a scope declared at
        birth rather than answering as though the session were unscoped."""
        client = TestClient(create_app())
        session_id = _create(client, {"skill_target": self.TARGET}).json()[
            "session_id"
        ]

        response = _declare(client, session_id, self.TARGET)

        assert response.status_code == 200
        assert response.json() == {
            "session_id": session_id,
            "target": self.TARGET,
            # An identical re-declaration is the same scope, so it does not
            # report as a displaced one.
            "already_declared": False,
        }

    def test_a_birth_target_is_scoped_exactly_like_a_standalone_one(self) -> None:
        """Both paths run one validator, so neither can persist a query the
        other would have dropped — a third path added later inherits the same
        shaping by calling it."""
        client = TestClient(create_app())

        response = _create(
            client,
            {"skill_target": "https://admin.internal/login?token=hunter2#top"},
        )

        assert response.status_code == 201
        session_id = response.json()["session_id"]
        assert AUTHORING_TRACE_STORE.trace_target(session_id) == (
            "https://admin.internal/login"
        )


# --- Blast-radius re-validation (SPEC-055 R-4) ------------------------------


def _row(
    position: int,
    tool_name: str = "web.click",
    args: dict | None = None,
    flow_origin: str | None = TARGET,
    captured_at: str = "2026-09-08T10:00:00Z",
) -> dict:
    """One trace row shaped the way ``load_for_session`` returns it.

    Built by hand rather than through the store: these tests assert what the
    re-validation does with a *given* trace, including shapes the live seam
    only produces on a failure path (a NULL ``flow_origin``, a non-JSON
    argument, a step past the budget), and routing each one through the real
    capture path would test the store instead.
    """
    return {
        "session_id": "ses-1",
        "position": position,
        "tool_name": tool_name,
        "args": {"selector": "#submit"} if args is None else args,
        "execution_id": f"exec-{position}",
        "confirm_id": f"cf-{position}",
        "status": TRACE_DRAFT,
        "captured_at": captured_at,
        "flow_origin": flow_origin,
    }


def _browser_trace(count: int = 2) -> list[dict]:
    return [_row(index, flow_origin=TARGET) for index in range(1, count + 1)]


class TestRevalidateBlastRadius:
    """Each of the four guards spec.md R-4 names, asserted on its own.

    They are asserted individually rather than through one "bad trace refuses"
    test because the refusals are the operator's only explanation of why a
    session they spent an hour on cannot become a skill: a guard that stops
    naming its step, or that quietly stops firing, is a regression these tests
    have to catch separately.
    """

    def test_a_clean_browser_trace_is_graduable(self) -> None:
        report = revalidate_blast_radius(_browser_trace(), target=TARGET)

        assert report.graduable is True
        assert report.refusals == ()
        assert report.step_count == 2
        assert report.browser_steps == 2
        assert report.web_target == TARGET
        assert report.unguarded_positions == ()

    def test_an_empty_trace_refuses_with_the_reason(self) -> None:
        report = revalidate_blast_radius([], target=TARGET)

        assert report.graduable is False
        assert report.step_count == 0
        assert len(report.refusals) == 1
        assert "no captured authoring trace" in report.refusals[0]

    def test_the_budget_is_the_replay_budget_not_the_ingestion_ceiling(self) -> None:
        # 20 is the tool-gateway's ``DEFAULT_BROWSER_FLOW_MAX_STEPS``, the
        # budget ``bind_flow`` arms a bound flow with. skills-hub ingests up
        # to 200, so a 21-step flow would ingest cleanly and then die
        # part-way through mutating — the failure R-4 exists to surface
        # before the operator holds the artifact.
        assert DEFAULT_MAX_GRADUATION_STEPS == 20

        at_budget = revalidate_blast_radius(_browser_trace(20), target=TARGET)
        over_budget = revalidate_blast_radius(_browser_trace(21), target=TARGET)

        assert at_budget.graduable is True
        assert over_budget.graduable is False
        assert "21 captured steps exceed the 20-step budget" in over_budget.refusals[0]

    def test_the_budget_is_operator_tunable(self) -> None:
        report = revalidate_blast_radius(
            _browser_trace(21), target=TARGET, max_steps=50
        )

        assert report.graduable is True
        assert report.max_steps == 50

    def test_a_browser_step_with_no_declared_target_refuses(self) -> None:
        report = revalidate_blast_radius(_browser_trace(), target=None)

        assert report.graduable is False
        assert report.web_target is None
        assert any("no declared target" in reason for reason in report.refusals)

    def test_a_drifted_origin_refuses_naming_the_step(self) -> None:
        steps = [
            _row(1, flow_origin=TARGET),
            _row(2, flow_origin="https://elsewhere.internal/admin"),
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        reason = next(
            item for item in report.refusals if "outside the declared target" in item
        )
        assert "step 2 (web.click) landed on https://elsewhere.internal" in reason

    def test_the_origin_is_compared_not_the_whole_url(self) -> None:
        # The declared target is origin *and* path, but the guard is an
        # origin guard: a flow that navigates within the declared host is
        # the normal case, and refusing it would make every multi-page flow
        # un-graduable.
        steps = [
            _row(1, flow_origin="https://admin.internal/login"),
            _row(2, flow_origin="https://admin.internal/console/settings"),
        ]

        assert revalidate_blast_radius(steps, target=TARGET).graduable is True

    def test_a_step_with_no_observed_origin_refuses_as_unverified(self) -> None:
        # NULL is produced by a result that did not succeed, by a payload over
        # the evidence frame's size guard, by a gateway that reported no URL,
        # and by every row written before R-4. Fabricating an origin for one
        # would corroborate a mutation that may never have landed.
        steps = [_row(1, flow_origin=TARGET), _row(2, flow_origin=None)]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        reason = next(item for item in report.refusals if "no observed origin" in item)
        assert "step(s) 2" in reason
        # Unverified is never reported as drift: the two are different facts
        # and only one of them claims to know where the step landed.
        assert not any("outside the declared target" in item for item in report.refusals)

    @pytest.mark.parametrize("tool_name", ["web.read_page", "web.snapshot", "web.get"])
    def test_a_read_tier_browser_step_refuses(self, tool_name: str) -> None:
        # Derived rather than listed: ``web.*`` is the whole browser surface
        # and ``BROWSER_WRITE_TOOLS`` its complete write subset, so a ``web.*``
        # tool outside that set is read-tier by construction. R-2's tier gate
        # already makes one impossible; this is the check that says so if the
        # gate ever leaked.
        steps = [_row(1, tool_name=tool_name)]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        reason = next(item for item in report.refusals if "read-tier" in item)
        assert f"step 1 ({tool_name})" in reason

    def test_a_credential_hole_refuses_naming_the_step_and_argument(self) -> None:
        steps = [_row(1, tool_name="web.type", args={"text": TRACE_CREDENTIAL_PLACEHOLDER})]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        reason = next(
            item for item in report.refusals if "unresolved credential hole" in item
        )
        assert "step 1 (web.type) args.text" in reason
        # The refusal is honest about there being no in-session fix: the hole
        # is stored, nothing resolves it after the fact, and the remedy is to
        # re-author the step. Telling the operator to "resolve" it would send
        # them looking for a control that does not exist.
        assert "nothing resolves a hole already in the trace" in reason
        assert "web.fill_credential" in reason

    def test_a_hole_nested_in_a_mapping_and_a_list_is_named_by_its_path(self) -> None:
        steps = [
            _row(
                1,
                tool_name="web.evaluate",
                args={"rows": [{"password": TRACE_CREDENTIAL_PLACEHOLDER}]},
            )
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any("args.rows[0].password" in item for item in report.refusals)

    def test_a_credential_set_reference_is_not_a_hole(self) -> None:
        # The reference the guard asks for: a named set and field, which is
        # what resolves at replay. Asserted on a *write-tier* tool so the hole
        # guard is what is under test and not the read-tier one beside it.
        steps = [
            _row(
                1,
                args={"selector": "#region", "credential_set": "admin-console",
                      "field": "passphrase"},
            )
        ]

        assert revalidate_blast_radius(steps, target=TARGET).graduable is True

    def test_a_credential_entry_in_a_trace_refuses_as_read_tier(self) -> None:
        """``web.fill_credential`` is read-tier, so a trace never holds one.

        Worth pinning because it looks like a contradiction with the hole
        refusal above, which names this very tool as the remedy. It is not:
        the tool is auto-allowed read-tier
        (``kernel_middleware.DEFAULT_AUTO_ALLOWED_TOOLS``), so R-2's
        ``tools:mutate`` gate never captures it — the remedy is to *re-author*
        the mutating step so the credential is filled by reference rather than
        typed, and a human adds the reference step to the draft at merge time.
        A trace that does contain one therefore means the tier gate leaked,
        and refusing is the check that says so.
        """
        steps = [
            _row(
                1,
                tool_name="web.fill_credential",
                args={"selector": "#password", "credential_set": "admin-console",
                      "field": "password"},
            )
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any("read-tier" in item for item in report.refusals)
        # It is a tier refusal, not a hole refusal: the reference is exactly
        # what the hole guard wants, and the two guards must not be conflated
        # or the operator is told the wrong thing is wrong.
        assert not any(
            "unresolved credential hole" in item for item in report.refusals
        )

    def test_an_oversized_step_list_refuses(self) -> None:
        steps = [_row(1, tool_name="web.evaluate", args={"expression": "x" * 70000})]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any("over the 64 KiB the skill contract allows" in item
                   for item in report.refusals)

    def test_a_non_ascii_step_list_is_measured_on_ingestions_basis(self) -> None:
        """The size twin has to share ingestion's *basis*, not just its number.

        ``json.dumps`` escapes a non-ASCII character to six ``\\uXXXX``
        characters by default where UTF-8 encodes a BMP character in three
        bytes, so a guard summing UTF-8 bytes per step counted the trace below
        at roughly half of what skills-hub counts for the same list. It is
        inside the ceiling in UTF-8 bytes and over it on ingestion's basis —
        the divergence that used to pass here and then be rejected there, which
        the route reports as a 502 "renderer and ingestion disagree" platform
        fault for what is an ordinary oversize trace. ``web.click.selector`` is
        off the credential vocabulary and is not an opaque field, so a real
        capture stores it verbatim and the size is genuinely reachable.
        """
        steps = [_row(index, args={"selector": "字" * 600}) for index in range(1, 21)]
        assert parameterize_for_trace("web.click", steps[0]["args"]) == steps[0]["args"]
        # The premise, asserted rather than assumed: on a UTF-8 byte basis this
        # same list is inside the ceiling, so the old measurement passed it.
        utf8_bytes = sum(
            len(
                json.dumps(
                    {"tool": step["tool_name"], "args": step["args"]},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            for step in steps
        )
        assert utf8_bytes <= MAX_STEPS_BYTES

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any(
            "over the 64 KiB the skill contract allows" in item
            for item in report.refusals
        )

    @pytest.mark.parametrize(
        "value",
        [
            "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcHMifQ.c2lnbmF0dXJlLWJ5dGVz",
            "Bearer Zm9vYmFyYmF6cXV1eA",
            "AKIAIOSFODNN7EXAMPLE",
        ],
        ids=["pem", "jwt", "bearer", "aws-key-id"],
    )
    def test_a_secret_shaped_argument_refuses_rather_than_riding_into_the_document(
        self, value: str
    ) -> None:
        """The frontmatter is the authoritative replay copy and is never scrubbed.

        R-2's capture-time parameterization is *name*-based, and
        ``web.select.value`` is positively allow-listed in ``KNOWN_SAFE_FIELDS``,
        so the value below is stored verbatim — asserted here through the real
        projection rather than assumed. ``postprocess`` then redacts only the
        *body*, so the runbook a reviewer reads by default showed
        ``[REDACTED]`` while the literal rode into the frontmatter they merge
        into a Git repo. Refusing is the only posture that neither changes what
        the flow replays (an in-place scrub would) nor hides the leak from the
        human review the whole design relies on.
        """
        args = {"value": value}
        # The premise: R-2 really would store this verbatim.
        assert parameterize_for_trace("web.select", args) == args
        steps = [_row(1, tool_name="web.select", args=args)]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any(
            "shaped like a secret literal" in item for item in report.refusals
        )
        # Naming the step, like every other guard: a refusal the operator
        # cannot act on is not a refusal.
        assert any("step 1 (web.select)" in item for item in report.refusals)
        # And not conflated with a hole — the two have different remedies, one
        # of which is a merge-time edit and the other a re-author.
        assert not any(
            "unresolved credential hole" in item for item in report.refusals
        )

    def test_a_non_secret_matching_a_shape_is_refused_as_an_over_catch(self) -> None:
        """The guard over-catches, on purpose, and says so rather than lying.

        ``Basic Authentication`` is a plausible *dropdown option* on an admin
        portal's auth-settings page — the exact kind of page this spec targets —
        and it is indistinguishable from a real ``Authorization`` value at this
        layer. The shape vocabulary is not new to R-4: the gateway has always
        redacted this string out of tool output and ``postprocess`` out of a
        draft body, so the over-catch is an accepted trade with two shipped
        consumers. What R-4 changes is the *consequence* — cosmetic redaction
        becomes a refusal with no in-platform remedy — so the refusal has to be
        honest about it. Asserting the wording is what stops a future
        "improvement" from quietly narrowing the pattern: narrowing buys back
        this false positive by opening a false *negative*, and only one of those
        two publishes a credential.
        """
        args = {"selector": "#auth-mode", "value": "Basic Authentication"}
        # The premise again: a KNOWN_SAFE_FIELDS name, so R-2 stores it as-is.
        assert parameterize_for_trace("web.select", args) == args

        report = revalidate_blast_radius(
            [_row(1, tool_name="web.select", args=args)], target=TARGET
        )

        assert report.graduable is False
        refusal = next(
            item for item in report.refusals if "shaped like a secret literal" in item
        )
        # Hedged: it names a shape, never asserts the value *is* a credential.
        assert "The match is by shape" in refusal
        # And it names the over-catch and why the error direction is the safe
        # one, because the operator reading this has done nothing wrong.
        assert "only looks like one" in refusal
        assert "fails safe" in refusal
        # The credential remedy is offered conditionally, not as the only read.
        assert "If it is a credential" in refusal

    def test_the_shape_guard_does_not_swallow_the_other_guards_evidence(self) -> None:
        """One step can fail two guards and the operator has to hear both.

        The function's contract is that a trace failing several guards is told
        about all of them at once, because a refusal that names one problem
        invites a fix that then hits the next. The shape check sits mid-loop, so
        a ``continue`` after it would silently drop everything below — origin
        corroboration, the read-tier check — and the operator would re-author
        the credential and be refused again for a reason they were never told.
        """
        steps = [
            _row(
                1,
                tool_name="web.select",
                args={"value": "Bearer Zm9vYmFyYmF6cXV1eA"},
                flow_origin="https://elsewhere.example",
            )
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        # Both, from one step: the shape match and the origin drift.
        assert any(
            "shaped like a secret literal" in item for item in report.refusals
        )
        assert any(
            "outside the declared target's origin" in item
            for item in report.refusals
        )
        assert any("step 1 (web.select)" in item for item in report.refusals)

    def test_a_non_json_argument_refuses_rather_than_rendering(self) -> None:
        # Not JSON-compatible, so it is not storable in the ``steps`` JSONB
        # column either: refused here rather than rendered into a document
        # ingestion would then reject.
        steps = [_row(1, args={"at": datetime(2026, 9, 8, tzinfo=timezone.utc)})]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any("not JSON-compatible" in item for item in report.refusals)

    def test_an_overlong_tool_name_refuses(self) -> None:
        steps = [_row(1, tool_name="web." + "n" * 200)]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        assert any("tool name the skill contract cannot hold" in item
                   for item in report.refusals)

    def test_a_pure_infra_trace_graduates_without_a_web_target(self) -> None:
        # A ``web_target`` is what ``bind_flow`` binds a browser flow from, so
        # declaring one on a pure-infra flow would advertise a binding the
        # flow never uses. The non-browser steps are reported as unguarded —
        # outside the flow's origin guard by construction, replaying under
        # their own per-action approval — which is a fact, not a refusal.
        steps = [
            _row(1, tool_name="k8s.scale_deployment", args={"replicas": 3},
                 flow_origin=None),
            _row(2, tool_name="k8s.restart_service", args={"namespace": "ops"},
                 flow_origin=None),
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is True
        assert report.web_target is None
        assert report.browser_steps == 0
        assert report.unguarded_positions == (1, 2)

    def test_a_mixed_trace_graduates_and_names_its_unguarded_steps(self) -> None:
        steps = [
            _row(1, tool_name="web.click", flow_origin=TARGET),
            _row(2, tool_name="k8s.restart_service", flow_origin=None),
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is True
        assert report.web_target == TARGET
        assert report.browser_steps == 1
        assert report.unguarded_positions == (2,)

    def test_a_trace_failing_several_guards_reports_all_of_them(self) -> None:
        # ``refusals`` is a tuple, not one message: reporting only the first
        # would send the operator back for a second round-trip to discover
        # the next.
        steps = [
            _row(1, tool_name="web.type", args={"text": TRACE_CREDENTIAL_PLACEHOLDER}),
            _row(2, tool_name="web.read_page", flow_origin=None),
        ] + [
            _row(index, flow_origin="https://elsewhere.internal/x")
            for index in range(3, 24)
        ]

        report = revalidate_blast_radius(steps, target=TARGET)

        assert report.graduable is False
        joined = "\n".join(report.refusals)
        assert "exceed the 20-step budget" in joined
        assert "read-tier" in joined
        assert "unresolved credential hole" in joined
        assert "outside the declared target" in joined
        assert len(report.refusals) >= 4


class TestDeclarationOrder:
    """The ordering report: a fact for the reviewer, never a gate.

    Corroboration is the control. A hard ordering gate would add friction
    without adding safety, so a postdated declaration still graduates — but
    the draft says out loud that the scope was fitted to a trace that had
    already begun, which is the difference between an authorization and a
    claim about the past.
    """

    def test_a_declaration_before_the_first_step_preceded(self) -> None:
        report = revalidate_blast_radius(
            _browser_trace(), target=TARGET, declared_at="2026-09-08T09:00:00Z"
        )

        assert report.declaration == DECLARATION_PRECEDED
        assert report.graduable is True

    def test_a_declaration_after_the_first_step_postdated(self) -> None:
        report = revalidate_blast_radius(
            _browser_trace(), target=TARGET, declared_at="2026-09-08T11:00:00Z"
        )

        assert report.declaration == DECLARATION_POSTDATED
        # Reported, not refused.
        assert report.graduable is True

    def test_a_same_second_declaration_is_indeterminate(self) -> None:
        # Both stamps reach a caller canonicalized to second precision, so the
        # sub-second order is genuinely not knowable — and guessing would
        # report an authorization scope as pre-declared when it may have been
        # fitted to the trace. Nothing gates on this, so it costs a fact.
        report = revalidate_blast_radius(
            _browser_trace(), target=TARGET, declared_at="2026-09-08T10:00:00Z"
        )

        assert report.declaration == DECLARATION_INDETERMINATE

    @pytest.mark.parametrize(
        "declared_at",
        [None, "", "not-a-stamp", "2026-09-08T10:00:00"],
    )
    def test_an_unusable_stamp_is_indeterminate(self, declared_at) -> None:
        # The last case is a *naive* stamp: comparing it against an aware one
        # raises, and a refusal here would cost the operator a graduation over
        # a reporting detail.
        report = revalidate_blast_radius(
            _browser_trace(), target=TARGET, declared_at=declared_at
        )

        assert report.declaration == DECLARATION_INDETERMINATE
        assert report.graduable is True

    def test_a_step_with_no_stamp_is_indeterminate(self) -> None:
        steps = [_row(1, captured_at="")]

        report = revalidate_blast_radius(
            steps, target=TARGET, declared_at="2026-09-08T09:00:00Z"
        )

        assert report.declaration == DECLARATION_INDETERMINATE


# --- The rendered draft (SPEC-055 R-4) --------------------------------------


# Mirrors skills-hub's ``ingestion.ALLOWED_KEYS``. Products never import each
# other, so this is a second copy — but a *test-side* one, and the assertion it
# supports is the one that matters: a key this renderer invents is a document
# the operator's own skills repo rejects, which is the failure the endpoint's
# validation leg exists to prevent and the one a local test can catch without
# a live skills-hub.
INGESTION_ALLOWED_KEYS = {
    "title",
    "description",
    "tags",
    "version",
    "source_url",
    "web_target",
    "risk_class",
    "flow_intent",
    "kind",
    "steps",
}


def _frontmatter_lines(markdown: str) -> list[str]:
    assert markdown.startswith("---\n")
    fence = markdown.split("---\n", 2)[1]
    return fence.splitlines()


def _frontmatter_keys(markdown: str) -> set[str]:
    # Top-level keys only: a step's ``tool`` / ``args`` are indented under
    # ``steps`` and are not frontmatter keys.
    return {
        line.split(":", 1)[0]
        for line in _frontmatter_lines(markdown)
        if line and not line[0].isspace() and ":" in line
    }


class TestBuildExecutableFlowDraft:
    """The rendering half: deterministic, contract-shaped, and honest.

    Determinism is asserted first because it is the property that separates
    this from SPEC-044's generator. A draft is a rendering of steps a human
    already approved, so the same trace must produce the same document — a
    re-graduation that differed from the artifact already reviewed would make
    "the operator holds the file they approved" untrue.
    """

    def _render(self, steps, *, target=TARGET, report=None, **kwargs):
        if report is None:
            report = revalidate_blast_radius(steps, target=target)
        kwargs.setdefault("session_id", "ses-1")
        return build_executable_flow_draft(steps, report=report, **kwargs)

    def test_the_same_trace_renders_the_same_document(self) -> None:
        steps = [
            _row(1, tool_name="web.navigate", args={"url": "https://admin.internal/"}),
            _row(2, tool_name="web.select", args={"selector": "#env", "value": "prod"}),
        ]
        report = revalidate_blast_radius(steps, target=TARGET)

        first, first_slug = build_executable_flow_draft(
            steps, report=report, session_id="ses-1"
        )
        second, second_slug = build_executable_flow_draft(
            steps, report=report, session_id="ses-1"
        )

        assert first == second
        assert first_slug == second_slug

    def test_argument_key_order_does_not_change_the_document(self) -> None:
        # The store returns a JSONB object whose key order is not part of its
        # contract, so the renderer sorts: otherwise two graduations of one
        # trace could differ in bytes and still be "the same" document.
        report = revalidate_blast_radius(
            [_row(1, args={"selector": "#a", "value": "b"})], target=TARGET
        )
        shuffled = revalidate_blast_radius(
            [_row(1, args={"value": "b", "selector": "#a"})], target=TARGET
        )

        first, _ = build_executable_flow_draft(
            [_row(1, args={"selector": "#a", "value": "b"})],
            report=report,
            session_id="ses-1",
        )
        second, _ = build_executable_flow_draft(
            [_row(1, args={"value": "b", "selector": "#a"})],
            report=shuffled,
            session_id="ses-1",
        )

        assert first == second

    def test_the_document_is_a_v2_executable_flow(self) -> None:
        steps = [_row(1, args={"selector": "#submit"})]

        markdown, slug = self._render(steps)

        assert "kind: executable_flow" in markdown
        assert "risk_class: write" in markdown
        assert 'web_target: "https://admin.internal/login"' in markdown
        assert 'tags: ["executable-flow", "graduated"]' in markdown
        assert '  - tool: "web.click"' in markdown
        assert '    args: {"selector": "#submit"}' in markdown
        assert slug == "https-admin-internal-executable-flow"

    def test_no_frontmatter_key_is_invented(self) -> None:
        markdown, _ = self._render(_browser_trace())

        assert _frontmatter_keys(markdown) <= INGESTION_ALLOWED_KEYS
        # The three that make it an executable flow rather than knowledge
        # prose must all be present, or ingestion reads it as the v1 class.
        assert {"kind", "steps", "risk_class"} <= _frontmatter_keys(markdown)

    def test_no_expect_postcondition_is_invented(self) -> None:
        # The trace records what ran, not what anyone expected afterwards.
        # Inventing a post-condition would be exactly the synthesis R-4
        # forbids; a human completing the draft may add one. ``expect`` inside
        # ``args`` is an argument the step really carried and rides through —
        # it is the *step-level* key, which ingestion accepts as a
        # post-condition, that must never appear.
        steps = [_row(1, args={"selector": "#submit", "expect": "a literal arg"})]

        markdown, _ = self._render(steps)

        assert 'args: {"expect": "a literal arg", "selector": "#submit"}' in markdown
        assert not any(
            line.strip().startswith("expect:")
            for line in _frontmatter_lines(markdown)
        )

    def test_the_provenance_block_names_the_session_and_the_mode(self) -> None:
        markdown, _ = self._render(_browser_trace())

        assert "session: ses-1" in markdown
        assert f"mode: {MODE_GRADUATED}" in markdown

    def test_the_session_title_names_the_skill(self) -> None:
        markdown, slug = self._render(_browser_trace(), title="Restart checkout")

        assert 'title: "Restart checkout"' in markdown
        assert slug == "restart-checkout"

    def test_an_untitled_session_falls_back_to_the_declared_scope(self) -> None:
        markdown, slug = self._render(_browser_trace(), title=None)

        # Names the scope rather than a generic string: the operator sees this
        # as a filename and a reviewer as the skill's identity in the repo.
        assert 'title: "https://admin.internal executable flow"' in markdown
        assert slug == "https-admin-internal-executable-flow"

    def test_a_pure_infra_draft_omits_web_target_and_says_why(self) -> None:
        steps = [
            _row(1, tool_name="k8s.scale_deployment", args={"replicas": 3},
                 flow_origin=None)
        ]
        report = revalidate_blast_radius(steps, target=None)

        markdown, slug = build_executable_flow_draft(
            steps, report=report, session_id="ses-1", declared_target=None
        )

        assert not any(
            line.startswith("web_target:") for line in _frontmatter_lines(markdown)
        )
        assert "a non-browser flow needs none" in markdown
        assert slug == "infra-executable-flow"

    def test_a_declared_target_with_no_browser_step_is_named_not_emitted(self) -> None:
        # The scope is a fact the reviewer should see, but emitting it as
        # ``web_target`` would advertise a flow binding the flow never uses.
        steps = [
            _row(1, tool_name="k8s.restart_service", args={"namespace": "ops"},
                 flow_origin=None)
        ]
        report = revalidate_blast_radius(steps, target=TARGET)

        markdown, _ = build_executable_flow_draft(
            steps, report=report, session_id="ses-1", declared_target=TARGET
        )

        assert not any(
            line.startswith("web_target:") for line in _frontmatter_lines(markdown)
        )
        assert "not emitted as `web_target`" in markdown
        assert TARGET in markdown

    def test_the_runbook_restates_every_step_in_replay_order(self) -> None:
        steps = [
            _row(1, tool_name="web.navigate", args={"url": "https://admin.internal/"}),
            _row(2, tool_name="web.click", args={"selector": "#submit"}),
        ]

        markdown, _ = self._render(steps)

        # The preview's rendered view strips the YAML fence, so the step list
        # a reviewer reads by default lives in the body.
        assert "1. `web.navigate`" in markdown
        assert "2. `web.click`" in markdown
        assert markdown.index("1. `web.navigate`") < markdown.index("2. `web.click`")

    def test_the_unguarded_positions_are_named_in_the_body(self) -> None:
        steps = [
            _row(1, tool_name="web.click", flow_origin=TARGET),
            _row(2, tool_name="k8s.restart_service", flow_origin=None),
        ]
        report = revalidate_blast_radius(steps, target=TARGET)

        markdown, _ = build_executable_flow_draft(
            steps, report=report, session_id="ses-1", declared_target=TARGET
        )

        assert "Outside the origin guard: step(s) 2" in markdown

    @pytest.mark.parametrize(
        ("declared_at", "expected"),
        [
            ("2026-09-08T09:00:00Z", "before the first captured step"),
            ("2026-09-08T11:00:00Z", "**after** the first captured step"),
            ("2026-09-08T10:00:00Z", "at an indeterminate point"),
        ],
    )
    def test_the_body_states_where_the_declaration_sat(
        self, declared_at: str, expected: str
    ) -> None:
        # A postdated declaration still graduates, but the draft says out loud
        # that the scope was fitted to a trace that had already begun — the
        # difference between an authorization and a claim about the past.
        report = revalidate_blast_radius(
            _browser_trace(), target=TARGET, declared_at=declared_at
        )

        markdown, _ = build_executable_flow_draft(
            _browser_trace(),
            report=report,
            session_id="ses-1",
            declared_target=TARGET,
        )

        assert expected in markdown

    def test_a_huge_argument_is_elided_in_the_body_but_kept_in_the_frontmatter(
        self,
    ) -> None:
        # The frontmatter is the authoritative copy; the runbook restates it
        # for a human and must not double a huge value into the body's cap.
        expression = "x" * 5000
        steps = [_row(1, tool_name="web.evaluate", args={"expression": expression})]

        markdown, _ = self._render(steps)

        # The full value survives exactly once — in the frontmatter. The
        # body's copy is elided, marked with the ellipsis.
        assert markdown.count(expression) == 1
        assert "…" in markdown

    def test_the_runbook_names_the_binding_step_a_trace_can_never_contain(
        self,
    ) -> None:
        """``web.navigate`` is the only entry point to ``bind_flow`` and is
        never captured, so the operator has to add it — and the document says so
        rather than implying the step list is already a runnable flow.

        The same structural gap as the credential one, and found the same way: a
        read-tier call the flow needs cannot enter a trace R-2 gates on
        ``tools:mutate``. Left unnamed, an operator who follows the runbook
        exactly merges a flow that never binds, so every write parks its own
        card instead of the single one the ``risk_class`` bullet promises.
        """
        markdown, _ = self._render([_row(1), _row(2)])

        guidance = markdown.split("### Before you merge this", 1)[1]
        assert "web.navigate" in guidance
        # The binding is keyed on the skill's identity, which does not exist
        # until the merge assigns it, so the guidance has to say that too.
        assert "skill_id" in guidance

        # And the step list holds no navigate step — that is the gap the
        # guidance exists to close. Asserting both halves is what stops the
        # bullet from decaying into decoration.
        step_list = markdown.split("### Steps", 1)[1].split("### Before", 1)[0]
        assert "web.navigate" not in step_list

    def test_the_document_never_claims_to_carry_no_secret(self) -> None:
        """The one claim a reviewer would trust instead of looking.

        Graduation refuses the secret *shapes* it recognizes, but a literal
        under a name and shape the vocabulary does not know rides through into
        the frontmatter, which is never scrubbed. An unconditional "carries no
        literal secret" would remove the reason to check — and the rendered view
        a reviewer reads by default is the redacted one, so the check has to be
        asked for explicitly.
        """
        markdown, _ = self._render([_row(1), _row(2)])

        assert "carries no literal secret" not in markdown
        guidance = markdown.split("### Before you merge this", 1)[1]
        # The residual is stated as a residual, naming the shapes that *are*
        # refused and the check the operator is asked to perform.
        assert "**not** detectable" in guidance
        assert "read the step arguments" in guidance

    def test_the_body_stays_inside_its_byte_budget(self) -> None:
        """The runbook's own trim holds, and *why* it is belt-and-braces.

        Exercised on a trace that overruns the budget outright: the trace cap is
        operator-tunable with no ceiling, and ``build_executable_flow_draft``
        does not re-check graduality, so a caller can hand it a trace whose
        runbook runs to megabytes. For a trace the guards *passed* the trim is
        unreachable rather than merely unlikely — elision only ever shrinks an
        argument, so the frontmatter costs at least what the runbook does per
        step and the ``steps`` ceiling bounds the body too. The previous version
        of this test asserted that second point with constant arithmetic
        (``20 * 400 < 65536``) which touched no code path at all and still
        passed with the trim deleted.
        """
        steps = [
            _row(index, tool_name="web.evaluate", args={"expression": "y" * 900})
            for index in range(1, 2001)
        ]
        # A raised bound so the report is about the rendering under test rather
        # than the step guard; the trace is over the size ceiling and this test
        # does not claim otherwise.
        report = revalidate_blast_radius(steps, target=TARGET, max_steps=len(steps))

        markdown, _ = self._render(steps, report=report)

        body = markdown.split("---\n\n", 1)[1]
        # Clamped to just under the budget, so the assertion is the trim firing
        # rather than a body that happened to be small.
        assert MAX_BODY_BYTES - 1024 < len(body.encode("utf-8")) <= MAX_BODY_BYTES


# --- The graduation endpoint (SPEC-055 R-4) ---------------------------------


def _stamp(offset_hours: int = 0) -> str:
    """A second-precision stamp ``offset_hours`` from now.

    Offsets rather than a patched clock: the store stamps ``declared_at`` from
    the real clock at declaration time, so the only way to order a declaration
    against a step without reaching into ``_targets`` is to move the *step*.
    """
    moment = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _configured_settings(graduation_max_steps: int | None = None) -> RuntimeSettings:
    kwargs = {} if graduation_max_steps is None else {
        "skill_graduation_max_steps": graduation_max_steps
    }
    return RuntimeSettings(
        skills_service_url="http://skills-hub:8000",
        skills_client_secret="s3cret",
        **kwargs,
    )


def _wire_route(
    monkeypatch,
    *,
    configured: bool = True,
    validation=(True, None),
    graduation_max_steps: int | None = None,
):
    """Stand in the skills-hub validation leg and the settings behind it."""
    monkeypatch.setattr(
        v2_routes,
        "get_settings",
        lambda: _configured_settings(graduation_max_steps),
    )
    monkeypatch.setattr(
        v2_routes, "skills_validation_configured", lambda settings: configured
    )
    calls: dict = {"validate": 0}

    async def _validate(settings, request_id, markdown):
        calls["validate"] += 1
        calls["markdown"] = markdown
        return validation

    monkeypatch.setattr(v2_routes, "validate_skill_draft", _validate)
    return calls


@pytest.fixture
def _audit(monkeypatch):
    """Capture the audit events the route emits."""
    emitted: list[dict] = []
    monkeypatch.setattr(
        v2_routes, "emit_audit_event", lambda settings, event: emitted.append(event)
    )
    return emitted


def _seed_trace(
    session_id: str,
    *,
    count: int = 2,
    tool_name: str = "web.click",
    origin: str | None = TARGET,
    captured_at: str | None = None,
) -> None:
    """Append steps through the real capture seam.

    ``append_step`` at the signing seam, ``record_step_origin`` at the receipt
    seam — the two halves R-2 and stage 6a built, in the order they run. A
    step seeded with ``origin=None`` is the honest unverified case: captured
    and signed, but never corroborated by a result frame.
    """
    for index in range(1, count + 1):
        execution_id = f"exec-{index}"
        appended = AUTHORING_TRACE_STORE.append_step(
            make_trace_step(
                session_id=session_id,
                tool_name=tool_name,
                args={"selector": f"#submit-{index}"},
                captured_at=captured_at or _stamp(),
                execution_id=execution_id,
                confirm_id=f"cf-{index}",
            )
        )
        assert appended is True
        if origin is not None:
            assert AUTHORING_TRACE_STORE.record_step_origin(
                session_id, execution_id, origin
            )


def _graduate(client: TestClient, session_id: str, user: str = "alice"):
    return client.post(
        f"/api/v2/sessions/{session_id}/skill-graduate",
        headers={"X-User-ID": user},
    )


@pytest.mark.parametrize("variant", ["unknown", "late", "conflict", "unavailable", "missing", "stopped", "no_origin", "original"])
def test_graduation_requires_current_evidence_without_inventing_an_origin(monkeypatch, variant):
    client = TestClient(create_app())
    session_id = _make_session(client, "alice")
    AUTHORING_TRACE_STORE.declare_target(session_id, TARGET)
    _seed_trace(session_id, count=1, origin=None if variant == "no_origin" else TARGET)
    calls = _wire_route(monkeypatch)
    projection = {"execution_id": "exec-1", "tool_name": "web.click", "availability": "available",
        "state": "outcome_unknown" if variant == "unknown" else "result_recorded",
        "integrity_conflict": variant == "conflict", "run_stopped": variant == "stopped",
        "observe_by": "2026-09-24T10:00:00Z",
        "receipt": {"status": "succeeded", "completed_at": "2026-09-24T10:00:01Z" if variant == "late" else "2026-09-24T10:00:00Z"}}
    reads = []
    def read(sid, owner):
        reads.append((sid, owner))
        return {"availability": "unavailable" if variant == "unavailable" else "available",
                "executions": [] if variant == "missing" else [projection]}
    monkeypatch.setattr(v2_routes, "read_owner_recovery_page", read)
    before = AUTHORING_TRACE_STORE.load_for_session(session_id)
    response = _graduate(client, session_id)
    assert reads == [(session_id, "alice")]
    assert response.status_code == (200 if variant == "original" else 409)
    assert calls["validate"] == (1 if variant == "original" else 0)
    if variant != "original":
        assert AUTHORING_TRACE_STORE.load_for_session(session_id) == before
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT


class TestGraduateRoute:
    def test_a_scoped_session_graduates_into_a_validated_draft(
        self, monkeypatch, _audit
    ) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        calls = _wire_route(monkeypatch)
        # The develop-as-you-go order: declare the target at birth, *then*
        # mutate. The step stamps are an hour ahead of the real clock so the
        # declaration provably precedes them.
        assert _declare(client, session_id, TARGET).status_code == 200
        _seed_trace(session_id, captured_at=_stamp(1))

        response = _graduate(client, session_id)

        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == MODE_GRADUATED
        assert body["validation"] == "passed"
        assert body["step_count"] == 2
        assert body["web_target"] == TARGET
        assert body["declaration"] == DECLARATION_PRECEDED
        assert body["suggested_filename"].endswith(".md")
        assert body["markdown"].startswith("---\n")
        assert "kind: executable_flow" in body["markdown"]
        # The draft went through skills-hub's own ingestion path before it
        # reached the operator, and exactly once: there is no regeneration
        # loop here, because there is nothing to regenerate.
        assert calls["validate"] == 1
        assert calls["markdown"] == body["markdown"]

    def test_the_step_bound_comes_from_settings_not_the_module_default(
        self, monkeypatch, _audit
    ) -> None:
        """An operator who raises the gateway replay budget raises this twin.

        Asserted through the route rather than against
        ``revalidate_blast_radius``, which already honours ``max_steps``: what
        is under test is that the route *passes* the resolved value. A
        regression to the module default would be invisible to every other
        test in this file, because they all seed traces far shorter than 20.
        Both directions are pinned and the trace is identical, so the outcome
        cannot be attributed to anything but the bound — a session over the
        default graduates under a raised bound, and refuses under the default.
        """
        client = TestClient(create_app())
        over_default = DEFAULT_MAX_GRADUATION_STEPS + 5

        raised = _make_session(client, "alice")
        calls = _wire_route(monkeypatch, graduation_max_steps=over_default + 1)
        assert _declare(client, raised, TARGET).status_code == 200
        _seed_trace(raised, count=over_default, captured_at=_stamp(1))

        response = _graduate(client, raised)

        assert response.status_code == 200, response.text
        assert response.json()["step_count"] == over_default
        assert calls["validate"] == 1

        default = _make_session(client, "alice")
        _wire_route(monkeypatch)
        assert _declare(client, default, TARGET).status_code == 200
        _seed_trace(default, count=over_default, captured_at=_stamp(1))

        refused = _graduate(client, default)

        assert refused.status_code == 409
        assert (
            f"{over_default} captured steps exceed the "
            f"{DEFAULT_MAX_GRADUATION_STEPS}-step budget"
        ) in refused.json()["detail"]

    def test_graduation_emits_the_audit_event(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)

        assert _graduate(client, session_id).status_code == 200

        events = [event for event in _audit if event["event_type"] == "skill_graduated"]
        assert len(events) == 1
        details = events[0]["details"]
        assert details["session_id"] == session_id
        assert details["mode"] == MODE_GRADUATED
        assert details["validation"] == "passed"
        assert details["step_count"] == 2
        # The scoped declaration rather than the whole target row: it is what a
        # reviewer reads to know which origin the graduated flow is bound to.
        assert details["web_target"] == TARGET
        assert details["declaration"] in {
            DECLARATION_PRECEDED,
            DECLARATION_POSTDATED,
            DECLARATION_INDETERMINATE,
        }

    def test_graduation_flips_the_lifecycle_and_never_publishes(
        self, monkeypatch, _audit
    ) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT

        assert _graduate(client, session_id).status_code == 200

        # Terminal: no later approval appends to a graduated trace and the
        # idle-GC never reclaims it, so the artifact and the trace it came
        # from cannot drift apart.
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_GRADUATED
        # Never auto-published. The platform drafts, humans merge — preserved
        # here because this artifact is higher-trust than a knowledge draft.
        assert not getattr(OPERATION_DOCUMENT_STORE, "_by_document_id", {})

    def test_a_re_graduation_is_an_idempotent_re_export(
        self, monkeypatch, _audit
    ) -> None:
        # What an operator who lost the download needs: the identical document,
        # audited again because it is another act producing an executable
        # artifact.
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)

        first = _graduate(client, session_id)
        second = _graduate(client, session_id)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["markdown"] == first.json()["markdown"]
        assert (
            len([e for e in _audit if e["event_type"] == "skill_graduated"]) == 2
        )
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_GRADUATED

    def test_a_session_with_no_trace_answers_409(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)

        response = _graduate(client, session_id)

        assert response.status_code == 409
        assert "no captured authoring trace" in response.json()["detail"]
        assert _audit == []

    def test_an_unverified_step_blocks_the_endpoint(self, monkeypatch, _audit) -> None:
        # Captured and signed, but no result frame ever corroborated where it
        # landed. Graduating it would assert a mutation landed on the declared
        # target on no evidence at all.
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id, count=1, origin=TARGET)
        _seed_trace(session_id, count=1, origin=None)

        response = _graduate(client, session_id)

        assert response.status_code == 409
        assert "no observed origin" in response.json()["detail"]

    def test_a_refusal_leaves_the_trace_open(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id, count=1, origin=None)

        assert _graduate(client, session_id).status_code == 409

        # A refusal must not strand the session: the operator may still fix the
        # trace, and the idle-GC still treats it as the work product it is.
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT

    def test_a_discarded_trace_is_refused(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)
        assert AUTHORING_TRACE_STORE.close_trace(session_id, TRACE_DISCARDED) is True

        response = _graduate(client, session_id)

        assert response.status_code == 409
        assert "discarded" in response.json()["detail"]
        # A deliberately dropped candidate is never resurrected.
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DISCARDED
        assert _audit == []

    def test_a_validation_failure_is_a_502_and_leaves_the_trace_open(
        self, monkeypatch, _audit
    ) -> None:
        # Re-validation already passed, so a rejection here means the renderer
        # and ingestion disagree — a platform fault, not a judgement about the
        # operator's session. The lifecycle does not flip: a session stranded
        # as graduated with no draft to show for it is the worst of both.
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        calls = _wire_route(monkeypatch, validation=(False, "steps must be a list"))
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)

        response = _graduate(client, session_id)

        assert response.status_code == 502
        assert "steps must be a list" in response.json()["detail"]
        assert calls["validate"] == 1
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT
        assert _audit == []

    def test_validation_not_configured_is_a_503(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch, configured=False)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)

        response = _graduate(client, session_id)

        assert response.status_code == 503
        # Fail-closed before any draft is built: an unvalidated executable
        # artifact is never returned.
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT

    def test_foreign_session_answers_structural_404(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _declare(client, session_id, TARGET)
        _seed_trace(session_id)

        response = _graduate(client, session_id, user="bob")

        assert response.status_code == 404
        assert _audit == []
        # The failed call touched nothing: the owner's trace is still open.
        assert AUTHORING_TRACE_STORE.trace_status(session_id) == TRACE_DRAFT

    def test_unknown_session_answers_404(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        _wire_route(monkeypatch)

        assert _graduate(client, "ses-missing").status_code == 404

    def test_a_caller_without_identity_answers_401(self, monkeypatch, _audit) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)

        response = client.post(f"/api/v2/sessions/{session_id}/skill-graduate")

        assert response.status_code == 401

    def test_a_postdated_declaration_still_graduates_and_says_so(
        self, monkeypatch, _audit
    ) -> None:
        # Reported, never gated: corroboration is the control, and a hard
        # ordering gate would add friction without adding safety. The step
        # stamps are in the past, so the declaration provably postdates them.
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _seed_trace(session_id, captured_at=PAST)
        assert _declare(client, session_id, TARGET).status_code == 200

        response = _graduate(client, session_id)

        assert response.status_code == 200
        assert response.json()["declaration"] == DECLARATION_POSTDATED
        assert "**after** the first captured step" in response.json()["markdown"]

    def test_a_pure_infra_session_graduates_without_a_web_target(
        self, monkeypatch, _audit
    ) -> None:
        client = TestClient(create_app())
        session_id = _make_session(client, "alice")
        _wire_route(monkeypatch)
        _seed_trace(
            session_id,
            count=2,
            tool_name="k8s.scale_deployment",
            origin=None,
        )

        response = _graduate(client, session_id)

        assert response.status_code == 200
        body = response.json()
        assert body["web_target"] is None
        assert body["step_count"] == 2
        assert "web_target:" not in body["markdown"]
        # The non-browser steps are outside the flow's origin guard by
        # construction and the draft says so, rather than implying a guard
        # covers them.
        assert "Outside the origin guard" in body["markdown"]
