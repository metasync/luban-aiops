"""Credential masking for chat prose (SPEC-049 R-5 applied to a conversation).

The operator types a password into the chat, the model reads it in its own
prompt, and it can write it back out in prose. A live run of the ad-hoc reset
sample ended its first turn with "worth flagging: the temporary password
``TempPass123!`` is now in this chat transcript" — rendered verbatim in the
transcript panel underneath a sidebar title reading ``... to ***``.

Two things are pinned here, and the second matters as much as the first:

1. **Masking.** The value the operator typed does not survive into the durable
   transcript or the live stream, including when it arrives one token at a
   time.
2. **Scope.** The heuristic that recognises a credential-*looking* token never
   runs on model output. ``SECRET_PARAM_SUBSTRINGS`` contains ``token``,
   ``session_id`` and ``signature``, which are ordinary words in operations
   prose, so promoting it would mask the session ids and pod names a reply is
   supposed to carry. That asymmetry is asserted in both directions rather
   than left as a comment.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from agentscope.event import RequireUserConfirmEvent
from agentscope.message import ToolCallBlock

from agent_service.runtime_kernel import AgentKernel
from agent_service.runtime_settings import DEFAULT_SYSTEM_PROMPT, RuntimeSettings
from agent_service.services import session_transcript
from agent_service.services.agent_state_store import InMemoryAgentStateStore
from agent_service.services.hitl_confirmations import CONFIRMATION_REGISTRY
from agent_service.services.prose_redaction import (
    StreamingProseRedactor,
    credential_literals,
    redact_assistant_text,
    redact_structure,
    redact_transcript,
    redact_user_text,
)

# The ad-hoc sample's own Step 3 prompt: a bare password in prose, with no
# pinned shape, no ``key=value`` pair and no URL query to catch it.
AD_HOC_PROMPT = (
    "Ad-hoc, without binding a flow, reset the password for "
    "alice@example.com to TempPass-2026! in the admin portal."
)
PASSWORD = "TempPass-2026!"
LITERALS = credential_literals(AD_HOC_PROMPT)

# What the live run actually produced, paraphrased: the model flags the leak
# and prints the value in the same sentence.
ECHO = (
    "Done. worth flagging: the temporary password `TempPass-2026!` is now "
    "in this chat transcript."
)

PARK_CALL = ToolCallBlock(
    id="call-1", name="k8s.restart_service", input='{"namespace": "ops"}'
)


# --- Fakes -----------------------------------------------------------------


class FakeUserMsg:
    def __init__(self, name, content):
        self.name = name
        self.content = content


class FakeMsg:
    """One agent-context message, as ``_user_text_literals`` reads it."""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class FakeState:
    def __init__(self, context: list | None = None) -> None:
        self.context = context or []

    def model_dump_json(self) -> str:
        return "{}"


class FakeAgent:
    def __init__(self, events: list | None = None, context: list | None = None,
                 reply: str = "") -> None:
        self.events = events or []
        self.toolkit = None
        self.state = FakeState(context)
        self.reply = reply
        self.inputs: list = []

    async def reply_stream(self, inputs):
        self.inputs.append(inputs)
        for event in self.events:
            yield event

    async def reply(self, msg, structured_schema=None):
        self.inputs.append(msg)
        return SimpleNamespace(content=self.reply)


def _kernel() -> AgentKernel:
    return AgentKernel(settings=RuntimeSettings(api_key="test-key"))


def _patch(monkeypatch, kernel: AgentKernel, agent: FakeAgent) -> None:
    async def fake_ensure_agent(
        session_id, bearer_token=None, model_id=None, read_only=False
    ):
        return agent, FakeUserMsg, model_id or kernel.settings.provider

    monkeypatch.setattr(kernel, "ensure_agent", fake_ensure_agent)
    monkeypatch.setattr(
        kernel, "_snapshot_state", lambda session_id, agent: None
    )


def _drain(async_iter) -> list:
    async def _collect():
        return [frame async for frame in async_iter]

    return asyncio.run(_collect())


def _stream(kernel: AgentKernel, message: str) -> list:
    return _drain(
        kernel.stream_events(
            message=message,
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
        )
    )


def _deltas(frames: list) -> str:
    """The reply text a client accumulates: every delta, in order."""
    return "".join(
        frame["delta"]
        for frame in frames
        if isinstance(frame.get("delta"), str)
    )


def _kind(frame: dict) -> str:
    """A frame's event name, whichever key carries it.

    Confirmation frames key on ``type`` and normalized AgentScope events on
    ``event``; the portal's decoder reads ``type || event``, so this does too.
    """
    return str(frame.get("event") or frame.get("type") or "")


def _delta_events(text: str, size: int) -> list:
    return [
        {"type": "TEXT_BLOCK_DELTA", "delta": text[i : i + size]}
        for i in range(0, len(text), size)
    ]


@pytest.fixture(autouse=True)
def _clean_registry():
    CONFIRMATION_REGISTRY._by_session.clear()
    yield
    CONFIRMATION_REGISTRY._by_session.clear()


# --- Harvesting: what user-authored text contributes ------------------------


def test_harvests_the_typed_password_from_the_sample_prompt():
    """Both the raw token and its punctuation-stripped form.

    The stripped form is what makes an exact match robust: the model may
    restate the value with different surrounding punctuation, and a shorter
    literal can only mask more, never less.
    """
    assert PASSWORD in LITERALS
    assert "TempPass-2026" in LITERALS


def test_harvests_nothing_from_an_ordinary_operations_request():
    """No secret name in the text, so the heuristic gate never opens.

    This is what keeps an ordinary session's assistant replies completely
    untouched: with no literals harvested, the literal layer has nothing to
    match and the reply is returned byte for byte.
    """
    ordinary = "check the web-ui pod in dev-luban-aiops and report restarts"
    assert credential_literals(ordinary) == frozenset()
    assert redact_assistant_text(ordinary, credential_literals(ordinary)) == ordinary


def test_harvests_a_key_anchored_value_and_both_forms_of_a_url_query():
    keyed = credential_literals("rotate the db password=hunter2secret today")
    assert "hunter2secret" in keyed

    queried = credential_literals(
        "open https://target/reset?user=alice&newpw=TempPass123%21 and confirm"
    )
    # The unquoted form is what the model restates in prose; the raw form is
    # what it restates inside a URL it echoes back.
    assert "TempPass123!" in queried
    assert "TempPass123%21" in queried


def test_a_url_harvest_does_not_swallow_the_prose_after_it():
    """The over-capture this pins. ``urlsplit`` reads the first ``?`` in a
    *sentence* as a query delimiter, so the whole-sentence parse harvested
    ``TempPass123! and confirm`` as one literal — which both ate three words
    of any reply repeating them and missed the bare credential the model
    actually restates. Bounding the parse to the URL fixes both halves.
    """
    prompt = (
        "open https://target/reset?user=alice&newpw=TempPass123%21 and confirm"
    )
    literals = credential_literals(prompt)
    assert "TempPass123! and confirm" not in literals

    masked = redact_user_text(prompt)
    assert "newpw=***" in masked
    assert "user=alice" in masked
    assert masked.endswith(" and confirm")

    # The bare value is now harvestable, so a reply that never repeats the URL
    # is still caught — which the whole-sentence parse missed.
    assert redact_assistant_text(
        "the password TempPass123! is live", literals
    ) == "the password *** is live"


def test_never_harvests_the_address_or_the_identifiers_beside_the_secret():
    """The prompt names a secret, so the heuristic gate is open — and even
    then the address and the hyphenated identifiers survive it. Harvesting
    one of those would exact-match it out of every subsequent reply."""
    prompt = (
        "reset the password using runbook browser-check-target on "
        "dev-luban-aiops for alice@example.com"
    )
    literals = credential_literals(prompt)
    assert "alice@example.com" not in literals
    assert "browser-check-target" not in literals
    assert "dev-luban-aiops" not in literals
    assert literals == frozenset()


def test_a_short_key_value_is_not_harvested_as_a_literal():
    """Below ``LITERAL_MIN_CHARS`` a value is more likely to be an ordinary
    word than a credential, and an exact match on it would mask that word
    wherever a reply happened to use it. The user's own turn still masks it
    (``redact_user_text`` has no length floor on this layer)."""
    assert credential_literals("set pwd=x1 now") == frozenset()
    assert "***" in redact_user_text("set pwd=x1 now")


# --- Scope: what harvested literals may do to model output ------------------


def test_assistant_text_masks_an_exact_literal_the_operator_typed():
    masked = redact_assistant_text(ECHO, LITERALS)
    assert "TempPass" not in masked
    assert "***" in masked
    # Surgical: the rest of the sentence, including the flag itself, survives.
    assert masked.startswith("Done. worth flagging: the temporary password")
    assert "is now in this chat transcript." in masked


def test_assistant_text_keeps_the_identifiers_a_reply_is_made_of():
    """The scoping guarantee, and the reason the heuristic stays off this side.

    Every one of these is ordinary operations prose that also contains a
    secret *name*, which is exactly the condition that opens the heuristic
    gate on user text. Run it here and the session ids, pod names and error
    text disappear from the reply.
    """
    preserved = (
        "the delegated token for ses-c8171f20 refreshed",
        "the pod web-ui-676bfb5d67-fqcqw restarted 2 times",
        "signature: mismatch on the receipt",
        "error: token expired for session_id ses-99a1b2c3",
        "the credential set admin-portal supplied the password field",
    )
    for text in preserved:
        assert redact_assistant_text(text, LITERALS) == text, text


def test_the_same_sentence_masks_as_user_text_and_not_as_assistant_text():
    """Pins the asymmetry in both directions, so neither side can be widened
    or narrowed quietly. ``token`` opens the heuristic gate on user text;
    ``ses-c8171f20`` is mixed-alnum and long enough to look like a credential.
    The assistant side is handed literals from an *ordinary* operator message,
    which is the real wiring — harvesting from the reply itself would be
    circular and would mask everything by construction.
    """
    text = "the delegated token for ses-c8171f20 refreshed"
    assert credential_literals("check the web-ui pod and report restarts") == (
        frozenset()
    )
    assert redact_user_text(text) == "the delegated token for *** refreshed"
    assert redact_assistant_text(
        text, credential_literals("check the web-ui pod and report restarts")
    ) == text


def test_an_identifier_the_operator_typed_beside_a_secret_name_is_masked():
    """The accepted false positive, pinned so it stays a decision.

    When the operator's own message names a secret *and* carries a
    mixed-alnum identifier, the heuristic harvests that identifier and every
    later reply restating it renders ``***``. The blast radius is one
    session's prose and the operator is the one who put it there; the
    alternative (narrowing the heuristic) reopens the bare-password miss this
    module exists to close.
    """
    operator = "the delegated token for ses-c8171f20 expired, reset the password"
    literals = credential_literals(operator)
    assert "ses-c8171f20" in literals
    assert redact_assistant_text(
        "the delegated token for ses-c8171f20 refreshed", literals
    ) == "the delegated token for *** refreshed"


def test_assistant_text_still_masks_pinned_shapes_and_secret_queries():
    """The two name/shape-anchored layers do run on model output: a false
    positive needs the reply to actually carry that shape."""
    shaped = redact_assistant_text(
        "call it with Bearer abcdefgh12345678 for payments", LITERALS
    )
    assert "abcdefgh12345678" not in shaped

    queried = redact_assistant_text(
        "GET https://target/reset?user=alice&newpw=Someword123!", LITERALS
    )
    assert "newpw=***" in queried
    assert "user=alice" in queried


def test_redact_structure_masks_every_string_in_a_payload():
    payload = {
        "type": "TEXT_BLOCK_DELTA",
        "delta": ECHO,
        "metadata": {"notes": ["no secret here", PASSWORD]},
        "count": 3,
        "flag": None,
    }
    masked = redact_structure(payload, LITERALS)
    assert "TempPass" not in json.dumps(masked)
    # Shape preserved: non-strings pass through untouched.
    assert masked["count"] == 3
    assert masked["flag"] is None
    assert masked["type"] == "TEXT_BLOCK_DELTA"


# --- The durable transcript projection -------------------------------------


def test_transcript_masks_both_roles():
    turns = [
        {"role": "user", "content": AD_HOC_PROMPT},
        {"role": "assistant", "content": ECHO},
    ]
    redacted = redact_transcript(turns)
    assert "TempPass" not in json.dumps(redacted)
    assert "to ***" in redacted[0]["content"]
    assert "***" in redacted[1]["content"]
    # The input is not mutated: callers hold the store's own copy.
    assert turns[1]["content"] == ECHO


def test_transcript_masks_a_cross_turn_echo():
    """The literal is introduced in turn one and restated in turn five, so
    harvesting has to run over the whole conversation before any of it is
    masked — a per-turn pass would miss this."""
    turns = [
        {"role": "user", "content": AD_HOC_PROMPT},
        {"role": "assistant", "content": "Parking the reset for approval."},
        {"role": "user", "content": "approved, carry on"},
        {"role": "assistant", "content": "Reset done."},
        {"role": "user", "content": "thanks — what did you set it to?"},
        {"role": "assistant", "content": f"I set it to {PASSWORD} as asked."},
    ]
    redacted = redact_transcript(turns)
    assert "TempPass" not in json.dumps(redacted)
    assert redacted[-1]["content"] == "I set it to *** as asked."


def test_transcript_preserves_order_and_the_other_turn_fields():
    turns = [
        {"role": "user", "content": AD_HOC_PROMPT, "created_at": "2026-09-11T10:00:00Z"},
        {"role": "assistant", "content": ECHO, "created_at": "2026-09-11T10:00:04Z"},
    ]
    redacted = redact_transcript(turns)
    assert [turn["role"] for turn in redacted] == ["user", "assistant"]
    assert [turn["created_at"] for turn in redacted] == [
        "2026-09-11T10:00:00Z",
        "2026-09-11T10:00:04Z",
    ]


def test_extract_transcript_masks_before_the_turns_leave_the_module(monkeypatch):
    """End to end through the projection the session read path actually uses,
    so masking is a property of ``extract_transcript`` rather than something
    each caller has to remember to do."""
    store = InMemoryAgentStateStore()
    monkeypatch.setattr(session_transcript, "AGENT_STATE_STORE", store)
    store.save_state(
        "ses-1",
        json.dumps({
            "session_id": "ses-1",
            "context": [
                {"role": "user", "content": AD_HOC_PROMPT},
                {"role": "assistant", "content": [{"type": "text", "text": ECHO}]},
                {"role": "system", "content": "deployment config, never projected"},
            ],
        }),
    )

    available, turns = session_transcript.extract_transcript("ses-1")

    assert available is True
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert "TempPass" not in json.dumps(turns)


# --- The streaming redactor ------------------------------------------------


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 13, 14, 15, 40, 10_000])
def test_streaming_never_leaks_a_literal_split_across_deltas(size):
    """Chunk size 5 splits ``TempPass-2026!`` into three deltas and 13 splits
    it into two, so this is the case a per-chunk mask fails. The output is
    compared against redacting the whole message, which also pins that nothing
    is dropped, duplicated or reordered on the way through."""
    redactor = StreamingProseRedactor(LITERALS)
    chunks = [ECHO[i : i + size] for i in range(0, len(ECHO), size)]
    emitted = "".join(
        [redactor.feed(chunk) for chunk in chunks] + [redactor.flush()]
    )
    assert "TempPass" not in emitted
    assert emitted == redact_assistant_text(ECHO, LITERALS)


def test_streaming_holds_back_only_a_short_tail():
    """The hold is ``max(len(literal)) - 1`` characters, so ordinary prose
    streams out immediately and only the tail waits. Pinning the exact number
    is what stops the hold from quietly growing into buffering the whole
    reply, which would look identical to a passing leak test."""
    text = "Done. The reset for alice@example.com completed at 10:04."
    redactor = StreamingProseRedactor(LITERALS)

    emitted = redactor.feed(text)
    tail = redactor.flush()

    assert len(emitted) == len(text) - (max(len(x) for x in LITERALS) - 1)
    assert text.startswith(emitted)
    assert emitted + tail == text


def test_flush_releases_a_literal_at_the_very_end_of_the_stream():
    """The stream's last characters are the ones most likely to be swallowed,
    because the portal accumulates deltas and has no complete-message frame to
    overwrite them with."""
    redactor = StreamingProseRedactor(LITERALS)
    emitted = redactor.feed("the password I set was ") + redactor.feed(PASSWORD)
    tail = redactor.flush()
    assert "TempPass" not in emitted + tail
    assert (emitted + tail).endswith("***")


def test_flush_is_idempotent_so_every_exit_point_can_call_it():
    """``runtime_kernel`` flushes at the terminal frame, at a park and again
    after the loop; only the first may produce text or a tail would be
    emitted twice."""
    redactor = StreamingProseRedactor(LITERALS)
    redactor.feed(f"set to {PASSWORD}")
    assert redactor.flush() != ""
    assert redactor.flush() == ""


def test_no_harvested_literals_means_no_hold_and_no_change():
    """An ordinary session streams exactly as it did before this existed."""
    text = "the web-ui pod restarted 2 times in the last hour"
    redactor = StreamingProseRedactor(credential_literals(
        "check the web-ui pod in dev-luban-aiops"
    ))
    assert redactor.feed(text) == text
    assert redactor.flush() == ""


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 8, 13, 29, 10_000])
def test_streaming_never_splits_a_url_whose_secret_was_never_typed(size):
    """The case the literal hold cannot cover, and the reason URLs join the
    span list. Nothing was harvested — the model produced this URL itself — so
    the hold is zero and only the URL span keeps ``newpw=`` from arriving in
    two pieces. Size 3 splits inside ``https://``, which is why the scheme is
    held as well: once ``htt`` is emitted no later buffer can match a URL.
    """
    text = (
        "redirect to https://target/reset?user=alice&newpw=Someword123! "
        "then stop"
    )
    redactor = StreamingProseRedactor(())
    emitted = "".join(
        [redactor.feed(text[i : i + size]) for i in range(0, len(text), size)]
        + [redactor.flush()]
    )
    assert "Someword123" not in emitted
    assert emitted == redact_assistant_text(text, ())


def test_a_scheme_prefix_at_the_buffer_end_is_held_not_published():
    """Pins the hold directly rather than through its effect, so a future
    change to ``URL_TOKEN`` cannot silently drop the scheme-prefix case."""
    redactor = StreamingProseRedactor(())
    assert redactor.feed("redirect to htt") == "redirect to "
    # The scheme completes into a URL, which is held until it terminates and
    # then masked on flush.
    assert redactor.feed("ps://t/r?newpw=x1y2z3!") == ""
    assert redactor.flush() == "https://t/r?newpw=***"


# --- Kernel wiring ---------------------------------------------------------


def test_normalize_event_masks_the_delta_and_the_payload_copy():
    kernel = _kernel()
    redactor = StreamingProseRedactor(LITERALS)

    frame = kernel.normalize_event(
        {"type": "TEXT_BLOCK_DELTA", "delta": ECHO},
        request_id="req-1",
        session_id="ses-1",
        redactor=redactor,
    )

    assert "TempPass" not in json.dumps(frame, default=str)
    assert frame["delta"]
    assert frame["payload"]["delta"] != ECHO


def test_normalize_event_omits_delta_when_the_whole_chunk_was_held_back():
    """An empty delta is omitted rather than sent as "": that is the shape
    this already produces for a text-block start carrying no text, and the
    portal's decoder gates on a truthy delta either way."""
    kernel = _kernel()
    redactor = StreamingProseRedactor(LITERALS)

    frame = kernel.normalize_event(
        {"type": "TEXT_BLOCK_DELTA", "delta": PASSWORD},
        request_id="req-1",
        session_id="ses-1",
        redactor=redactor,
    )

    assert "delta" not in frame
    # Held, not dropped.
    assert redactor.flush().endswith("***")


def test_normalize_event_without_a_redactor_is_unchanged():
    """The other callers — and every existing test — pass no redactor."""
    kernel = _kernel()

    frame = kernel.normalize_event(
        {"type": "TEXT_BLOCK_DELTA", "delta": "STREAM OK"},
        request_id="req-1",
        session_id="ses-1",
    )

    assert frame["delta"] == "STREAM OK"
    assert frame["payload"]["delta"] == "STREAM OK"


@pytest.mark.parametrize("size", [1, 3, 5, 13, 10_000])
def test_stream_events_masks_a_password_arriving_one_token_at_a_time(
    monkeypatch, size
):
    """The live path, end to end: literals harvested from the operator's own
    message and from the context, applied to a stream that splits the value
    across deltas."""
    kernel = _kernel()
    agent = FakeAgent(
        events=_delta_events(ECHO, size)
        + [{"type": "message_end", "message": "complete"}],
        context=[FakeMsg("user", AD_HOC_PROMPT)],
    )
    _patch(monkeypatch, kernel, agent)

    frames = _stream(kernel, AD_HOC_PROMPT)

    assert "TempPass" not in json.dumps(frames, default=str)
    assert "***" in _deltas(frames)


def test_stream_events_releases_the_tail_before_the_terminal_frame(monkeypatch):
    """Ordering, not just presence: the portal settles the turn at the
    terminal frame and never rewrites ``replyText`` afterwards, so a tail
    emitted later would be dropped rather than merely late."""
    kernel = _kernel()
    agent = FakeAgent(
        events=_delta_events(ECHO, 4)
        + [{"type": "message_end", "message": "complete"}],
        context=[FakeMsg("user", AD_HOC_PROMPT)],
    )
    _patch(monkeypatch, kernel, agent)

    frames = _stream(kernel, AD_HOC_PROMPT)
    kinds = [_kind(frame) for frame in frames]

    assert kinds[-1] == "message_end"
    assert kinds[-2] == "message_delta"
    assert _deltas(frames).endswith("is now in this chat transcript.")
    # Model attribution still rides the terminal frame (SPEC-024 R-3).
    assert frames[-1]["model"] == kernel.settings.provider


def test_a_parked_stream_releases_the_tail_before_the_card(monkeypatch):
    """A park ends the stream with no terminal frame, so the flush before the
    confirmation frame is the only chance the held-back tail gets. This is the
    ad-hoc sample's own shape: the model narrates, then parks a write."""
    kernel = _kernel()
    agent = FakeAgent(
        events=_delta_events("Resetting alice to TempPass-2026! now.", 6)
        + [RequireUserConfirmEvent(reply_id="reply-1", tool_calls=[PARK_CALL])],
        context=[FakeMsg("user", AD_HOC_PROMPT)],
    )
    _patch(monkeypatch, kernel, agent)

    frames = _stream(kernel, AD_HOC_PROMPT)
    kinds = [_kind(frame) for frame in frames]

    assert kinds[-1] == "confirmation_request"
    assert kinds[-2] == "message_delta"
    assert "TempPass" not in json.dumps(frames, default=str)
    assert _deltas(frames).endswith("now.")


def test_a_stream_that_ends_without_a_terminal_frame_still_releases_the_tail(
    monkeypatch,
):
    """A provider that closes right after the last delta is a documented
    legacy shape, so the post-loop flush has to cover it."""
    kernel = _kernel()
    agent = FakeAgent(
        events=_delta_events(f"The password is {PASSWORD}", 4),
        context=[FakeMsg("user", AD_HOC_PROMPT)],
    )
    _patch(monkeypatch, kernel, agent)

    frames = _stream(kernel, AD_HOC_PROMPT)

    assert not any(frame.get("event") == "message_end" for frame in frames)
    assert "TempPass" not in json.dumps(frames, default=str)
    assert _deltas(frames).endswith("***")


def test_stream_events_harvests_from_earlier_context_turns(monkeypatch):
    """The current message is not the only carrier: a password typed in turn
    one is still harvestable in turn five, which is when the model is most
    likely to restate it."""
    kernel = _kernel()
    agent = FakeAgent(
        events=_delta_events(f"Confirming it is set to {PASSWORD}.", 4)
        + [{"type": "message_end", "message": "complete"}],
        context=[
            FakeMsg("user", AD_HOC_PROMPT),
            FakeMsg("assistant", "Parking the reset for approval."),
        ],
    )
    _patch(monkeypatch, kernel, agent)

    # This turn's own message names no secret at all.
    frames = _stream(kernel, "thanks — what did you set it to?")

    assert "TempPass" not in json.dumps(frames, default=str)
    assert _deltas(frames) == "Confirming it is set to ***."


def test_kernel_fallback_messages_mask_the_interpolated_user_text():
    """A third carrier: both fallback strings interpolate the operator's own
    message into kernel-authored prose, so they carry a typed credential
    exactly as the prompt did."""
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))
    kernel._last_error = "model rejected the request"

    unconfigured = kernel.build_unconfigured_message(AD_HOC_PROMPT, "ses-1")
    provider_error = kernel.build_provider_error_message(
        AD_HOC_PROMPT, "ses-1", "deepseek-v4-flash"
    )

    for built in (unconfigured, provider_error):
        assert "TempPass" not in built
        assert "Received '" in built
        assert "***" in built
    # The rest of the message is untouched, so it still says what happened.
    assert "not configured for session ses-1" in unconfigured
    assert "Last error: model rejected the request" in provider_error


def test_reply_text_masks_the_returned_reply(monkeypatch):
    """The blocking turn has no streaming, so its reply masks whole."""
    kernel = _kernel()
    agent = FakeAgent(
        context=[FakeMsg("user", AD_HOC_PROMPT)], reply=ECHO
    )
    _patch(monkeypatch, kernel, agent)

    reply, structured = asyncio.run(
        kernel.reply_text(AD_HOC_PROMPT, "ses-1", "alice")
    )

    assert "TempPass" not in reply
    assert structured is None


def test_unconfigured_stream_masks_the_fallback_delta(monkeypatch):
    """The unconfigured path builds its message before any agent exists, so
    it has no context to harvest from — the user-text layer is what covers
    it."""
    kernel = AgentKernel(settings=RuntimeSettings(api_key=None))

    frames = _drain(
        kernel.stream_events(
            message=AD_HOC_PROMPT,
            request_id="req-1",
            session_id="ses-1",
            user_name="alice",
        )
    )

    assert "TempPass" not in json.dumps(frames, default=str)
    assert [frame["event"] for frame in frames] == [
        "message_start",
        "message_delta",
        "message_end",
    ]


# --- C: prompt guidance (defense in depth, not the control) -----------------


def test_system_prompt_forbids_restating_a_credential():
    """Lowering incidence, not guaranteeing anything: the live run that
    produced this fix had the model *recognise* the leak, flag it in prose,
    and print the value anyway. The projection masking above is the control;
    this is why the model should not need it."""
    assert "Never restate a credential" in DEFAULT_SYSTEM_PROMPT
    assert "defeats the flag" in DEFAULT_SYSTEM_PROMPT
