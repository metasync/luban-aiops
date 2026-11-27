"""SPEC-080 R-6: the platform-owned ``AskUserParams`` projection unit net.

``ConfirmationCoordinator._project_ask_user_questions`` is the platform-owned
mapping of agentscope's ``AskUserParams`` onto the v14 ``clarification_request``
wire questions; ``_clarification_output_prose`` / ``_clarification_result_metadata``
shape the owner's answer back into the resumed turn. These pins assert the
projector *mirrors the builtin's own constraints* (questions 1-4, header <=12,
options 2-4, ``multi_select`` default false, ``context`` optional) and NEVER
carries ``preview`` — no preview field exists in v14, in either direction.

The frame-level integration pin lives in ``test_hitl_confirmations.py``
(``test_build_clarification_frame_projects_ask_user_minus_preview``); this file
exercises the projector's bounds directly so each constraint is pinned on its
own rather than through one happy-path frame.
"""

from __future__ import annotations

import json

from agentscope.tool import AskUser, AskUserAnswer, AskUserMetadata

from agent_service.services.kernel_confirmations import (
    CLARIFICATION_HEADER_MAX,
    CLARIFICATION_OPTIONS_MAX,
    CLARIFICATION_OPTIONS_MIN,
    CLARIFICATION_QUESTIONS_MAX,
    ConfirmationCoordinator,
)

# The projector is a pure @staticmethod seam — call it off the class.
_project = ConfirmationCoordinator._project_ask_user_questions
_prose = ConfirmationCoordinator._clarification_output_prose
_metadata = ConfirmationCoordinator._clarification_result_metadata

_TWO_OPTIONS = [
    {"label": "prod", "description": "Production"},
    {"label": "stage", "description": "Staging"},
]


def _q(question: str = "Which cluster?", header: str = "Cluster", **extra):
    """A minimal valid question (2 options) with optional field overrides."""
    options = extra.pop("options", None)
    base = {
        "question": question,
        "header": header,
        "options": options if options is not None else list(_TWO_OPTIONS),
    }
    base.update(extra)
    return base


def _wrap(questions) -> dict:
    return {"questions": questions}


# --- The bounds are agentscope's, not hand-picked ---------------------------


def test_projection_bounds_mirror_the_live_askuser_schema() -> None:
    """R-6 keystone: the projector's bounds equal the constraints agentscope's
    own ``AskUser.input_schema`` declares, so a v14 frame can never carry a
    shape the builtin would reject. Pinning the constant against the live
    schema (rather than a literal) is what makes "mirrors the constraints"
    non-vacuous — a future agentscope tightening fails here first."""
    schema = AskUser().input_schema
    defs = schema["$defs"]
    questions = schema["properties"]["questions"]
    question_props = defs["_Question"]["properties"]
    options = question_props["options"]

    assert questions["minItems"] == 1
    assert CLARIFICATION_QUESTIONS_MAX == questions["maxItems"] == 4
    assert CLARIFICATION_HEADER_MAX == question_props["header"]["maxLength"] == 12
    assert CLARIFICATION_OPTIONS_MIN == options["minItems"] == 2
    assert CLARIFICATION_OPTIONS_MAX == options["maxItems"] == 4
    assert question_props["multi_select"]["default"] is False
    # ``preview`` is an OPTIONAL, single-select-only field on ``_Option`` — the
    # exact field R-6 withholds from v14 — while label/description are required.
    assert defs["_Option"]["required"] == ["label", "description"]
    assert "preview" in defs["_Option"]["properties"]


# --- The request projection: full shape minus preview -----------------------


def test_projects_full_shape_and_strips_preview() -> None:
    """R-6: a fully-populated question projects question/header/context/
    multi_select/options, and every option keeps EXACTLY {label, description} —
    the single-select-only ``preview`` is never read onto the wire."""
    raw = _wrap([
        _q(
            question="Which cluster should I inspect?",
            header="Cluster",
            context="prod is degraded",
            multi_select=True,
            options=[
                {"label": "prod", "description": "Production", "preview": "MOCKUP"},
                {"label": "stage", "description": "Staging", "preview": "SNIPPET"},
            ],
        )
    ])
    projected = _project(raw)

    assert len(projected) == 1
    entry = projected[0]
    assert entry["question"] == "Which cluster should I inspect?"
    assert entry["header"] == "Cluster"
    assert entry["context"] == "prod is degraded"
    assert entry["multi_select"] is True
    assert entry["options"] == [
        {"label": "prod", "description": "Production"},
        {"label": "stage", "description": "Staging"},
    ]
    for option in entry["options"]:
        assert set(option) == {"label", "description"}
    blob = json.dumps(projected)
    assert "preview" not in blob
    assert "MOCKUP" not in blob and "SNIPPET" not in blob


def test_questions_capped_at_four() -> None:
    raw = _wrap([_q(question=f"Q{i}?", header=f"H{i}") for i in range(6)])
    projected = _project(raw)
    assert len(projected) == CLARIFICATION_QUESTIONS_MAX == 4
    assert [e["question"] for e in projected] == ["Q0?", "Q1?", "Q2?", "Q3?"]


def test_header_truncated_to_twelve_chars() -> None:
    raw = _wrap([_q(header="0123456789ABCDEF")])  # 16 chars -> builtin max 12
    projected = _project(raw)
    assert projected[0]["header"] == "0123456789AB"
    assert len(projected[0]["header"]) == CLARIFICATION_HEADER_MAX == 12


def test_options_capped_at_four() -> None:
    opts = [{"label": f"l{i}", "description": f"d{i}"} for i in range(6)]
    projected = _project(_wrap([_q(options=opts)]))
    assert len(projected[0]["options"]) == CLARIFICATION_OPTIONS_MAX == 4
    assert [o["label"] for o in projected[0]["options"]] == ["l0", "l1", "l2", "l3"]


def test_question_dropped_when_fewer_than_two_valid_options() -> None:
    """The builtin requires 2-4 options; a question projecting fewer valid
    options is dropped whole (never emitted as an unanswerable card)."""
    assert _project(_wrap([_q(options=[{"label": "only", "description": "one"}])])) == []
    assert _project(_wrap([_q(options=[])])) == []
    # Two raw options but one malformed -> one valid -> below the floor -> drop.
    assert _project(_wrap([_q(options=[
        {"label": "ok", "description": "fine"},
        {"label": "missing-desc"},
    ])])) == []
    # Per-question leniency: a valid sibling survives the dropped one.
    projected = _project(_wrap([
        _q(question="bad?", options=[{"label": "only", "description": "one"}]),
        _q(question="good?", header="Good"),
    ]))
    assert [e["question"] for e in projected] == ["good?"]


def test_multi_select_defaults_false_and_coerces_to_bool() -> None:
    assert _project(_wrap([_q()]))[0]["multi_select"] is False       # absent
    assert _project(_wrap([_q(multi_select=True)]))[0]["multi_select"] is True
    # A non-bool is coerced through ``bool()``, never passed through raw.
    assert _project(_wrap([_q(multi_select="yes")]))[0]["multi_select"] is True
    assert _project(_wrap([_q(multi_select=0)]))[0]["multi_select"] is False


def test_context_kept_only_when_a_nonempty_string() -> None:
    assert "context" not in _project(_wrap([_q()]))[0]              # absent
    assert "context" not in _project(_wrap([_q(context="")]))[0]     # empty
    assert "context" not in _project(_wrap([_q(context=None)]))[0]   # null
    assert "context" not in _project(_wrap([_q(context=42)]))[0]     # non-string
    assert _project(_wrap([_q(context="look here")]))[0]["context"] == "look here"


def test_malformed_questions_are_dropped_not_raised() -> None:
    """The projector is lenient by design: a malformed question is dropped
    rather than raising. Each malformed shape projects to [] on its own — kept
    to a single question per call so the 4-question cap is never the operative
    constraint (the cap has its own pin above)."""
    malformed = [
        "not-a-dict",
        {"header": "No question", "options": list(_TWO_OPTIONS)},
        {"question": "No header", "options": list(_TWO_OPTIONS)},
        {"question": 42, "header": "Bad", "options": list(_TWO_OPTIONS)},
        {"question": "Bad", "header": 7, "options": list(_TWO_OPTIONS)},
        {"question": "Opts", "header": "Bad", "options": "not-a-list"},
    ]
    for raw_question in malformed:
        assert _project(_wrap([raw_question])) == [], raw_question

    # Per-question leniency within one park (all within the cap): the valid
    # survivor is kept while its malformed siblings drop.
    projected = _project(_wrap([
        "not-a-dict",
        {"question": "No header", "options": list(_TWO_OPTIONS)},
        _q(question="survives?", header="Yes"),
    ]))
    assert [e["question"] for e in projected] == ["survives?"]


def test_malformed_options_are_dropped_within_a_question() -> None:
    # Four raw options (within the cap) — two malformed, two valid — so the
    # drop is attributable to the malformed shape, not the options cap.
    raw = _wrap([_q(options=[
        "not-a-dict",
        {"label": "no-desc"},
        {"label": "a", "description": "A"},
        {"label": "b", "description": "B"},
    ])])
    assert _project(raw)[0]["options"] == [
        {"label": "a", "description": "A"},
        {"label": "b", "description": "B"},
    ]


def test_accepts_json_string_or_dict_and_rejects_everything_else() -> None:
    """The model fills ``AskUser.input`` as a raw JSON string; a dict is
    accepted too. Anything else (or unparseable JSON) projects to []."""
    payload = _wrap([_q()])
    assert _project(json.dumps(payload)) == _project(payload)   # str == dict
    assert _project(payload) != []
    assert _project("not json") == []
    assert _project(None) == []
    assert _project(42) == []
    assert _project([1, 2, 3]) == []
    # Parsed JSON whose ``questions`` is not a list -> [].
    assert _project(json.dumps({"questions": "nope"})) == []
    assert _project({"questions": None}) == []
    assert _project({}) == []


# --- The answer seam: prose + AskUserMetadata round-trip --------------------


def test_output_prose_restates_selections_and_other_deterministically() -> None:
    """The model-visible half restates only the question, the selected labels,
    and any free-text "Other" — deterministic and secret-free."""
    answers = [
        {"question": "Which cluster?", "selected": ["prod"]},
        {"question": "Which features?", "selected": ["a", "b"], "other": "custom"},
        {"question": "Empty?", "selected": []},
    ]
    assert _prose(answers) == (
        "Which cluster? -> prod\n"
        "Which features? -> a, b; Other: custom\n"
        "Empty? -> (no selection)"
    )
    assert _prose([]) == "The user answered the clarification."
    # Malformed answers are skipped, not raised.
    assert _prose(["not-a-dict", {"question": "Q?", "selected": ["x"]}]) == "Q? -> x"


def test_result_metadata_roundtrips_through_askusermetadata() -> None:
    """The structured half is built THROUGH agentscope's model, so the metadata
    the resumed reply receives is exactly what ``AskUser`` declares."""
    answers = [
        {"question": "Which cluster?", "selected": ["prod"]},
        {"question": "Which features?", "selected": ["a", "b"], "other": "custom"},
    ]
    metadata = _metadata(answers)
    expected = AskUserMetadata(answers=[
        AskUserAnswer(question="Which cluster?", selected=["prod"]),
        AskUserAnswer(question="Which features?", selected=["a", "b"], other="custom"),
    ]).model_dump()
    assert metadata == expected
    assert set(metadata) == {"answers"}
    for answer in metadata["answers"]:
        assert set(answer) == {"question", "selected", "other"}
    # ``other`` is present-but-None when absent (agentscope's optional field).
    assert metadata["answers"][0]["other"] is None
    assert metadata["answers"][1]["other"] == "custom"


def test_result_metadata_drops_and_coerces_malformed_answers() -> None:
    answers = [
        "not-a-dict",
        {"selected": ["x"]},                              # missing question
        {"question": 42, "selected": ["x"]},              # non-str question
        {"question": "ok?", "selected": "not-a-list"},    # selected -> []
        {"question": "good?", "selected": ["a"], "other": 7},  # other -> None
    ]
    kept = _metadata(answers)["answers"]
    assert [a["question"] for a in kept] == ["ok?", "good?"]
    assert kept[0]["selected"] == []
    assert kept[0]["other"] is None
    assert kept[1]["selected"] == ["a"]
    assert kept[1]["other"] is None


def test_no_preview_field_in_the_answer_seam() -> None:
    """R-6 wire guarantee in the answer direction: ``preview`` never exists in
    v14 — not on the parked request questions (asserted above) and not on the
    answered result metadata or prose, even if a caller smuggles it in."""
    answers = [{"question": "Q?", "selected": ["a"], "preview": "MUST-NOT-RIDE"}]
    metadata = _metadata(answers)
    prose = _prose(answers)
    assert "preview" not in json.dumps(metadata)
    assert "MUST-NOT-RIDE" not in json.dumps(metadata)
    assert "preview" not in prose
    assert "MUST-NOT-RIDE" not in prose
