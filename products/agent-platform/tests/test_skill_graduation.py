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
endpoint afterwards, for a session that becomes a development session
later. Both are first-wins, both report the target actually in force
rather than echoing the request, and both run one validator that holds the
scope as origin and path with any query or fragment dropped.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.services.authoring_trace import AUTHORING_TRACE_STORE
from agent_service.services.session_store import SESSION_STORE


@pytest.fixture(autouse=True)
def _clean_stores():
    """Isolate the process-wide session and authoring-trace singletons.

    Both backends are module-level singletons, so a session or a target
    declaration leaked from another test would make a first-wins assertion
    here read a scope this test never declared.
    """
    spaces = [
        getattr(SESSION_STORE, "_sessions", None),
        getattr(SESSION_STORE, "_last_accessed", None),
        getattr(AUTHORING_TRACE_STORE, "_by_session", None),
        getattr(AUTHORING_TRACE_STORE, "_targets", None),
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
