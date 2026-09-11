"""Credential masking for chat prose (SPEC-049 R-5 posture, fifth application).

The carrier no tool-side redactor ever sees
-------------------------------------------
An operator resets a password by *typing it into the chat*. From there the
value travels four ways. Three were already covered: into a tool argument
(``secret_params.redact_evidence_parameters``), into a change-request card
(``secret_params.redact_parameters``), and into a minted session title
(``session_service.mark_session_turn``). The fourth was not: the model reads
the value in its own prompt and writes it back out in prose.

A live run of the ad-hoc reset sample ended its first turn with "worth
flagging: the temporary password ``TempPass123!`` is now in this chat
transcript" — a reply the transcript panel then rendered verbatim while the
sidebar title above it read ``... to ***``. The defect is that incoherence:
two projections of one conversation disagreeing about whether the value is
secret. This module masks both prose projections — the durable transcript
(``session_transcript.extract_transcript``) and the live stream
(``runtime_kernel.stream_events`` / ``resume_confirmation``).

Detection runs on user-authored text only
-----------------------------------------
The four masking layers split into two kinds, and the split is the whole
design. Three are *name- or shape-anchored*: the pinned secret shapes
(PEM/JWT/Bearer-Basic/AKIA), a secret-named ``key=value`` pair, and a
secret-named URL query parameter. The fourth is a *heuristic*: with a secret
name present somewhere in the text, mask any token that looks like a typed
credential.

The heuristic is safe on user-authored text and unsafe on model output,
because ``SECRET_PARAM_SUBSTRINGS`` includes ``token``, ``session_id`` and
``signature`` — ordinary words in an operations reply. Run it over assistant
prose and "the delegated token for ses-c8171f20 refreshed" masks the session
id, which is precisely the evidence-destroying false positive
``secret_params.is_secret_value`` documents rejecting. The same objection
kills the ``key=value`` layer on prose: "signature: mismatch" becomes
"signature: ***".

So the split is:

* ``redact_user_text`` — all four layers. Applied to the operator's own
  message, where a false positive costs readability and a false negative
  publishes a credential. This is exactly the cost curve the title projection
  already accepted, which is why the machinery moved here rather than being
  re-declared.
* ``redact_assistant_text`` — the pinned shapes, the URL query layer, and an
  **exact match** against literals harvested from user text. No heuristic, no
  ``key=value`` layer. A false positive is impossible for the literal layer by
  construction: the string matched is one the operator typed.

``session_service`` records that its title predicate "must never be promoted
to a tool-output or trace redactor". That still holds — this is neither. It is
a display projection of user-authored chat text, which is the scope the
predicate was written for.

Known accepted limits, stated rather than hidden
------------------------------------------------
* An all-alphabetic password with no punctuation (``CorrectHorse``) has one
  character class and is not detected. Inherited from the title layer.
* Literals shorter than ``CREDENTIAL_MIN_CHARS`` are not harvested, so a
  sub-8-character password echoed bare in prose survives. The user's own turn
  still masks (its layers are not length-gated for ``key=value``/query), and
  a URL query masks at any length.
* Literal matching is case-sensitive. The model restating a password in a
  different case is not caught by the literal layer.
* ``StreamingProseRedactor`` guarantees its hold for harvested literals, for
  shape matches already present in its buffer, for a pinned shape still
  arriving — held by its ``SHAPE_ANCHORS`` prefix, up to ``SHAPE_HOLD_MAX_CHARS``
  back — and for a URL that has not finished arriving; see that class. Past the
  anchor cap a very long shape (a large multi-line PEM key) is best-effort in
  the stream and falls back to the durable transcript for the unbounded
  guarantee. A ``key=value`` secret that is neither a harvested literal nor
  inside a URL is not held, because the ``key=value`` layer deliberately does
  not run on model output.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import unquote, urlsplit

from agent_service.services.secret_params import (
    MASK,
    SECRET_PARAM_SUBSTRINGS,
    is_secret_param,
    redact_secret_query,
)


# Resolved once, on first call, into this cache: the pinned tuple is immutable
# for the process lifetime, and ``_secret_shape_patterns`` is reached three
# times per streamed delta (``_shape_hold``, ``_match_spans`` and
# ``redact_assistant_text``), so re-running the deferred import each time is
# overhead with no upside. A module global rather than a default argument so
# the deferral is preserved — the first call still lands at runtime, where the
# import cycle below is inert.
_SECRET_SHAPE_PATTERNS: tuple[re.Pattern[str], ...] | None = None


def _secret_shape_patterns() -> tuple[re.Pattern[str], ...]:
    """The pinned secret-shape vocabulary (PEM/JWT/Bearer-Basic/AKIA).

    Read from ``skill_draft`` rather than re-declared: the shapes are pinned as
    exactly two copies across products and ``validate_secret_vocabulary.py``
    fails the build on divergence, naming ``skill_draft.REDACTION_VALUE_PATTERNS``
    as the agent-platform side — so a third caller must import that one.

    The import is deferred because the dependency graph really is circular:
    this module needs the shapes, ``skill_draft`` needs ``shift_summary``,
    which needs ``session_transcript``, which needs ``redact_transcript`` from
    here. Moving the vocabulary is not an option (the validator pins its file
    path) and dropping the ``session_transcript`` edge would make masking
    opt-in per caller instead of a property of the projection, so the import
    moves to call time — where every module is loaded and the cycle is inert.
    The first call caches the tuple in ``_SECRET_SHAPE_PATTERNS`` and later
    calls return it directly.
    """
    global _SECRET_SHAPE_PATTERNS
    if _SECRET_SHAPE_PATTERNS is None:
        from agent_service.services.skill_draft import REDACTION_VALUE_PATTERNS

        _SECRET_SHAPE_PATTERNS = REDACTION_VALUE_PATTERNS
    return _SECRET_SHAPE_PATTERNS


# --- Detection vocabulary (shared with the session-title projection) ---
#
# Three of the four layers reuse a pinned vocabulary: the secret-*shape*
# patterns (PEM/JWT/Bearer-Basic/AKIA, shared with the gateway and the skill
# draft), the secret-*name* substrings applied to a ``key=value`` pair, and
# the same substrings applied to a URL query via ``redact_secret_query``.
# None of those matches a bare password literal in prose — "reset the
# password for alice to TempPass123!" has no shape, no key and no query — so
# the fourth layer masks a credential-*looking* token, fired only when the
# text already names a secret.
SECRET_NAME_ALTERNATION = "|".join(
    sorted(
        {re.escape(name) for name in SECRET_PARAM_SUBSTRINGS},
        key=lambda item: (-len(item), item),
    )
)
# ``password: TempPass123!`` / ``newpw=TempPass123!`` in prose. The value
# stops at ``&``/``;``/quotes so an already-masked URL query keeps its
# non-secret params visible instead of swallowing the rest of the string.
KEY_VALUE_SECRET = re.compile(
    rf"\b([\w.-]*(?:{SECRET_NAME_ALTERNATION})[\w.-]*)(\s*[=:]\s*)([^\s&;,\"']+)",
    re.IGNORECASE,
)
SECRET_NAME_HINT = re.compile(SECRET_NAME_ALTERNATION, re.IGNORECASE)
WHITESPACE_TOKEN = re.compile(r"\S+")
CREDENTIAL_MIN_CHARS = 8

# A URL inside prose. A scheme (or ``www.``) is required so an ordinary
# question in a sentence is not read as a query; a scheme-less URL's secret is
# still caught by ``KEY_VALUE_SECRET``, since a query parameter is already in
# ``key=value`` form. The scheme is any RFC-3986 scheme, not just ``http(s)``:
# a database DSN (``postgres://admin:pw@db/app``) carries its credential in the
# userinfo and sails straight through an ``https?``-only match. The greedy tail
# also matches a URL that has not finished arriving, running to the end of
# whatever buffer it is given — which is what lets ``StreamingProseRedactor``
# hold it rather than split it. The tail is ``*`` rather than ``+`` for the same
# reason: a buffer ending exactly at ``https://`` is a URL still arriving, and a
# ``+`` would not see it as one and would publish the scheme before the rest
# turned up. A bare scheme has no query, so every layer that consumes a match
# leaves it unchanged.
URL_TOKEN = re.compile(
    r"(?:\b[a-z][a-z0-9+.\-]*://|\bwww\.)[^\s<>\"']*", re.IGNORECASE
)

# The schemes ``URL_TOKEN`` can open with. A stream splits inside the scheme
# itself — ``... to htt`` then ``ps://...`` — and once the first half is
# emitted no later buffer can match, so the redactor holds back any tail that
# is still a prefix of one of these.
URL_SCHEME_STARTS = ("https://", "http://", "www.")
URL_SCHEME_MAX_CHARS = max(len(scheme) for scheme in URL_SCHEME_STARTS)

# The literal prefix every pinned secret shape (``skill_draft.
# REDACTION_VALUE_PATTERNS`` — PEM header, JWT ``eyJ``, ``Bearer``/``Basic``
# auth, AWS ``AKIA`` key id) opens with. A stream splits inside a shape the
# same way it splits inside a URL scheme, and once the head is emitted no later
# buffer re-forms the match, so ``StreamingProseRedactor`` holds a tail that is
# an anchor (or a prefix of one) whose pattern has not matched yet. These are
# the leading literals of the pinned patterns, not a third vocabulary —
# ``test_streaming_holds_every_pinned_shape`` streams one canonical example of
# each shape and fails if an anchor here goes stale against a pattern there.
SHAPE_ANCHORS = ("-----BEGIN", "eyJ", "AKIA", "Bearer", "Basic")

# How far back ``StreamingProseRedactor`` holds for a shape anchor whose
# pattern has not completed. A real single-token credential (JWT, Bearer token,
# AKIA id) is comfortably under this; a shape longer than the cap — a large
# multi-line PEM key — is best-effort in the stream and falls back to the
# durable transcript for the unbounded guarantee, exactly as the class
# docstring's "not finished arriving" limit already states. The cap also bounds
# how long a *false* anchor (``Bearer token expired``, where ``token`` is too
# short to match) stalls the stream before it resumes with a bounded lag.
SHAPE_HOLD_MAX_CHARS = 512

# Punctuation a token may carry from the sentence around it rather than from
# the credential itself. Harvesting the stripped form is what makes an exact
# match work when the model restates the value with different surrounding
# punctuation — and stripping is conservative in the right direction: the
# stripped form is a *prefix* of the raw token, so matching it can only mask
# more, never less.
TOKEN_EDGE_PUNCTUATION = ".,;:!?()[]{}<>\"'`"

# A harvested literal below this length is more likely to be an ordinary word
# than a credential, and an exact match on a short string would mask it
# wherever it appears in a reply. The heuristic layer already gates on this
# via ``is_credential_literal``; the name-anchored layers adopt it here so a
# ``pwd=x1`` pair cannot put a two-character string on the literal list.
LITERAL_MIN_CHARS = 8


def is_credential_literal(token: str) -> bool:
    """True when a whitespace-delimited token looks like a typed credential."""
    # Gate on the token as written, before stripping sentence punctuation. A
    # credential the operator typed with a trailing ``!``/``.`` that belongs to
    # the sentence (``Secret1!``) is 8 characters as written; stripping the
    # edge punctuation first would drop it to 7, below
    # ``CREDENTIAL_MIN_CHARS``, and leak a valid credential. The stripped core
    # is still what the character-class test below runs on, so surrounding
    # punctuation never counts toward the class budget.
    if len(token.strip()) < CREDENTIAL_MIN_CHARS:
        return False
    candidate = token.strip(TOKEN_EDGE_PUNCTUATION)
    # An address or anything carrying a path separator is an identifier or a
    # URL, not a password — and a URL's secret is the query layer's job,
    # which has already run by the time this is consulted.
    if "@" in candidate or "/" in candidate or "\\" in candidate:
        return False
    has_alpha = any(char.isalpha() for char in candidate)
    has_digit = any(char.isdigit() for char in candidate)
    classes = sum((
        any(char.islower() for char in candidate),
        any(char.isupper() for char in candidate),
        has_digit,
        any(not char.isalnum() for char in candidate),
    ))
    # Mixed alnum (``TempPass123``) or three-plus character classes
    # (``Crrct!Horse``). Requiring one of the two is what keeps the hyphenated
    # and dotted identifiers this product is full of — ``browser-check-target``,
    # ``dev-luban-aiops``, ``web-ui`` — out of the match: they carry two
    # classes at most (lowercase plus punctuation) and no digit.
    return (has_alpha and has_digit) or classes >= 3


def redact_user_text(text: str) -> str:
    """User-authored text with credential material masked.

    All four layers, most-deterministic first; each is idempotent on the
    previous one's output (``MASK`` is too short and too plain to re-match).
    """
    if not text:
        return text
    masked = text
    for pattern in _secret_shape_patterns():
        masked = pattern.sub(MASK, masked)
    masked = _redact_secret_queries(masked)
    masked = KEY_VALUE_SECRET.sub(rf"\1\2{MASK}", masked)
    if SECRET_NAME_HINT.search(masked):
        masked = WHITESPACE_TOKEN.sub(
            lambda match: (
                MASK if is_credential_literal(match.group(0))
                else match.group(0)
            ),
            masked,
        )
    return masked


def _redact_secret_queries(text: str) -> str:
    """``redact_secret_query`` applied to each URL in ``text``, not to ``text``.

    ``urlsplit`` reads the first ``?`` in a *sentence* as a query delimiter and
    everything after it as that query's last parameter, so calling it on prose
    masks ``newpw=Secret123! and confirm`` whole — swallowing words that were
    never secret, and handing the harvest below a literal with a sentence
    attached to it. Bounding the parse to a whitespace-delimited URL removes
    both. The title projection previously accepted that over-mask on the
    reasoning that deciding where a URL ends inside a sentence was the only
    alternative; whitespace decides it, so the trade is no longer needed.
    """
    return URL_TOKEN.sub(
        lambda match: redact_secret_query(match.group(0)), text
    )


def _secret_query_values(text: str) -> Iterable[str]:
    """Secret URL credentials in ``text`` — query values and DSN userinfo.

    Mirrors ``redact_secret_query``'s own parsing, per URL, so the harvested
    literals are exactly the values that layer masks. Both the quoted and the
    unquoted form of a query value matter: the unquoted one is what the model
    restates in prose, the quoted one is what it restates inside a URL it
    echoes back. A DSN carries its credential in the userinfo instead
    (``scheme://user:password@host``), frequently with no query at all, so that
    password is harvested on the same footing — otherwise an assistant
    restating it bare would miss the literal layer.
    """
    values: list[str] = []
    for match in URL_TOKEN.finditer(text):
        try:
            parsed = urlsplit(match.group(0))
        except ValueError:
            continue
        if parsed.password:
            values.append(parsed.password)
            values.append(unquote(parsed.password))
        if not parsed.query:
            continue
        for segment in parsed.query.split("&"):
            key, sep, value = segment.partition("=")
            if sep and is_secret_param(unquote(key)):
                values.append(value)
                values.append(unquote(value))
    return values


def _harvest(found: set[str], value: str) -> None:
    """Add a literal and its punctuation-stripped form, length permitting."""
    for candidate in (value, value.strip(TOKEN_EDGE_PUNCTUATION)):
        candidate = candidate.strip()
        if len(candidate) < LITERAL_MIN_CHARS or MASK in candidate:
            continue
        found.add(candidate)


def credential_literals(text: str) -> frozenset[str]:
    """Concrete credential values appearing in USER-authored text.

    These are the strings ``redact_assistant_text`` may match exactly. The
    heuristic layer contributes only when the text names a secret, so an
    ordinary operations request harvests nothing and the assistant side of
    that conversation is left completely alone.

    Known accepted false positive, inherited from the title layer: a
    mixed-alnum identifier the operator typed in a message that also names a
    secret (``ses-c8171f20`` beside the word "token") is harvested, and the
    model restating that identifier has it masked. The blast radius is one
    session's own prose, and the operator is the one who put it there.
    """
    if not text:
        return frozenset()
    found: set[str] = set()
    for match in KEY_VALUE_SECRET.finditer(text):
        _harvest(found, match.group(3))
    for value in _secret_query_values(text):
        _harvest(found, value)
    if SECRET_NAME_HINT.search(text):
        for match in WHITESPACE_TOKEN.finditer(text):
            token = match.group(0)
            # A ``key=value`` token is already harvested value-first by the
            # KEY_VALUE_SECRET pass above. Harvesting the whole token here too
            # would put the secret *name* on the literal list, so an assistant
            # restating ``newpw=<value>`` collapses the informative key along
            # with the value (``the newpw=*** field`` -> ``the *** field``).
            # Skip it; the value side is already covered.
            if KEY_VALUE_SECRET.search(token):
                continue
            if is_credential_literal(token):
                _harvest(found, token)
    return frozenset(found)


def _ordered_literals(literals: Iterable[str]) -> tuple[str, ...]:
    """Longest first, so a harvested raw token wins over its stripped prefix.

    ``credential_literals`` adds both forms; replacing the longer one first is
    what turns ``TempPass-2026!.`` into ``***`` instead of ``***!.``.
    """
    return tuple(
        sorted(
            {literal for literal in literals if literal and MASK not in literal},
            key=lambda item: (-len(item), item),
        )
    )


def redact_assistant_text(text: str, literals: Iterable[str] = ()) -> str:
    """Model-authored text with credential material masked.

    Deliberately narrower than ``redact_user_text``: the pinned shapes and
    the URL query layer (both name- or shape-anchored, so a false positive
    requires the reply to actually carry that shape), plus an exact match
    against literals the operator typed. Neither the heuristic token layer
    nor the ``key=value`` layer runs here — see the module docstring for the
    prose they would eat.
    """
    if not text:
        return text
    masked = text
    for pattern in _secret_shape_patterns():
        masked = pattern.sub(MASK, masked)
    masked = _redact_secret_queries(masked)
    for literal in _ordered_literals(literals):
        if literal in masked:
            masked = masked.replace(literal, MASK)
    return masked


def redact_structure(value: Any, literals: Iterable[str] = ()) -> Any:
    """``redact_assistant_text`` applied to every string in a frame payload.

    A normalized stream frame carries the model's text twice: once in the
    top-level ``delta`` the v2 contract forwards, and again inside ``payload``
    (the raw serialized AgentScope event). v2 drops ``payload`` as an
    "AgentScope internal" — ``test_contract_adapter`` asserts it never
    reaches a client — but the frame is the kernel's own output, so the copy
    is masked rather than left as a latent plaintext for any future consumer.
    """
    if isinstance(value, str):
        return redact_assistant_text(value, literals)
    if isinstance(value, (list, tuple)):
        return [redact_structure(item, literals) for item in value]
    if isinstance(value, dict):
        return {
            key: redact_structure(item, literals)
            for key, item in value.items()
        }
    return value


def redact_transcript(turns: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """A transcript copy with credential material masked, both roles.

    Two passes, and the order matters: the operator's message is the only
    place the value is *introduced*, so every user turn is harvested first
    and the resulting literal set is then applied to the whole conversation.
    That is what catches a cross-turn echo — the model restating in turn five
    a password typed in turn one.

    Both roles mask. The user's own turn is masked with the full four layers
    (it is user-authored text, so the heuristic is in scope), and the
    assistant's with the narrower ``redact_assistant_text``. Masking the
    operator's own message back to them is a small readability cost for a
    projection whose whole purpose is to not carry the value.

    Other keys on a turn (``created_at``) pass through untouched.
    """
    materialized = list(turns)
    literals: set[str] = set()
    for turn in materialized:
        if turn.get("role") == "user":
            literals |= credential_literals(turn.get("content") or "")
    frozen = frozenset(literals)
    redacted: list[dict[str, str]] = []
    for turn in materialized:
        content = turn.get("content") or ""
        if turn.get("role") == "user":
            content = redact_user_text(content)
        else:
            content = redact_assistant_text(content, frozen)
        redacted.append({**turn, "content": content})
    return redacted


class StreamingProseRedactor:
    """Incremental prose redaction for a live assistant stream.

    A delta boundary can fall inside a credential — token-level streaming
    routinely splits ``TempPass-2026!`` across three deltas — so masking each
    chunk independently would emit the pieces and never see the whole. This
    holds back a tail instead: ``feed`` returns only the text that cannot be
    part of an unfinished match, and ``flush`` returns the rest.

    **The caller must flush.** The portal accumulates deltas
    (``turn.replyText += frame.text``) and has no handler that overwrites
    them from a complete-message frame, so a held-back tail that is never
    flushed is silently dropped from the live view rather than merely
    delayed. ``runtime_kernel`` flushes at every stream exit: the
    ``message_end`` frame, a HITL park, and the post-loop drain.

    Guarantees, stated precisely:

    * A harvested literal is never emitted, whole or in part. The hold is
      ``max(len(literal)) - 1``, and a cut that would land inside a match is
      pulled back to that match's start, so a straddling literal waits.
    * A pinned shape already present in the buffer is never split by a cut,
      by the same pull-back.
    * A URL is never split either, so its query layer always sees a whole
      token. This is the case the literal hold alone misses: with nothing
      harvested the hold is zero, and a URL carrying ``newpw=...`` split
      across two deltas publishes the second half — the first chunk has no
      ``?`` yet and the second has lost the scheme. The scheme itself is held
      too, since a boundary can fall inside ``https://``.
    * A shape still arriving is held by its anchor (``SHAPE_ANCHORS``) up to
      ``SHAPE_HOLD_MAX_CHARS`` back, so a JWT/Bearer/AKIA/PEM split across
      deltas is not published in pieces that no later buffer re-forms. Past
      that cap a very long shape is best-effort here; the durable transcript,
      which masks complete text, is the projection carrying the unbounded
      guarantee.

    Degraded case: a match starting at the head of the buffer holds the cut
    at zero until it completes, so nothing is emitted meanwhile. That is the
    safe direction, and it self-limits — the pull-back condition
    (``start < cut < end``) goes false as soon as the match ends.
    """

    def __init__(self, literals: Iterable[str] = ()) -> None:
        self._literals = _ordered_literals(literals)
        longest = max((len(item) for item in self._literals), default=1)
        self._hold = max(longest - 1, 0)
        self._pending = ""

    @property
    def literals(self) -> tuple[str, ...]:
        """The harvested literals, longest first."""
        return self._literals

    def feed(self, delta: str) -> str:
        """The part of the stream so far that is safe to emit now."""
        if not delta:
            return ""
        self._pending += delta
        cut = self._safe_cut(max(len(self._pending) - self._hold, 0))
        # A tail that could still grow into a URL scheme waits too, or the
        # scheme is published in pieces and the URL is never recognised.
        cut = min(cut, len(self._pending) - self._scheme_hold())
        # Likewise a tail that is (or opens with) a pinned shape anchor still
        # arriving — a JWT split across deltas is otherwise emitted in pieces
        # that no later buffer re-forms into a match.
        cut = min(cut, len(self._pending) - self._shape_hold())
        head, self._pending = self._pending[:cut], self._pending[cut:]
        if not head:
            return ""
        return redact_assistant_text(head, self._literals)

    def flush(self) -> str:
        """The held-back tail, masked. Idempotent: a second call returns ""."""
        tail, self._pending = self._pending, ""
        if not tail:
            return ""
        return redact_assistant_text(tail, self._literals)

    def _scheme_hold(self) -> int:
        """Chars at the buffer's end that could still become a URL scheme.

        Longest match wins, and the longest possible is
        ``URL_SCHEME_MAX_CHARS``, so the hold is bounded and self-limiting: it
        dissolves as soon as the tail stops being a scheme prefix, whether
        that is because a URL started (and ``_match_spans`` takes over the
        hold) or because the characters turned out to be ordinary prose.
        """
        longest = min(URL_SCHEME_MAX_CHARS, len(self._pending))
        for length in range(longest, 0, -1):
            # ``.lower()``: ``URL_TOKEN`` is ``re.IGNORECASE`` so ``HTTPS://``
            # is a URL the match layer redacts, but ``URL_SCHEME_STARTS`` is
            # lowercase — comparing the raw tail would miss an uppercase scheme
            # and publish ``HTTP`` before ``S://`` arrived.
            tail = self._pending[-length:].lower()
            if any(
                scheme.startswith(tail) for scheme in URL_SCHEME_STARTS
            ):
                return length
        return 0

    def _shape_hold(self) -> int:
        """Chars at the buffer's end that could still grow into a pinned shape.

        Two cases, mirroring ``_scheme_hold``:

        * the boundary fell *inside* an anchor (``...ey``, ``-----BEG``), so
          the tail is a proper prefix of one — hold that prefix; and
        * an anchor arrived whole but its pattern has not matched yet (a JWT
          still streaming segments), so a credential is in progress — hold
          from the anchor toward the buffer's end, capped at
          ``SHAPE_HOLD_MAX_CHARS``. ``_safe_cut`` takes over once the shape
          completes; ``flush`` releases it if it never does.

        Anchors already inside a completed match are skipped — that match is
        ``_safe_cut``'s job, not a shape still arriving.
        """
        text = self._pending
        if not text:
            return 0
        completed = [
            match.span()
            for pattern in _secret_shape_patterns()
            for match in pattern.finditer(text)
        ]
        hold = 0
        for anchor in SHAPE_ANCHORS:
            # Case A: the tail is a proper prefix of the anchor.
            for length in range(min(len(anchor) - 1, len(text)), 0, -1):
                if text.endswith(anchor[:length]):
                    hold = max(hold, length)
                    break
            # Case B: a whole anchor not inside a completed match — a shape
            # still arriving. Hold from it, bounded by the cap.
            start = text.find(anchor)
            while start != -1:
                if not any(lo <= start < hi for lo, hi in completed):
                    hold = max(
                        hold, min(len(text) - start, SHAPE_HOLD_MAX_CHARS)
                    )
                    break
                start = text.find(anchor, start + 1)
        return hold

    def _safe_cut(self, cut: int) -> int:
        """Pull ``cut`` back to the start of any match it would split.

        ``<=`` on the upper bound, not ``<``. A match running to the buffer's
        end has an unknown extent — the next delta may continue it — so cutting
        *at* that end publishes a prefix of something still arriving, which is
        exactly the split-URL case. For a completed interior match the two
        conditions agree, so the literal and shape holds are unchanged.
        """
        for start, end in self._match_spans(self._pending):
            if start < cut <= end:
                cut = start
        return cut

    def _match_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for pattern in _secret_shape_patterns():
            spans.extend(match.span() for match in pattern.finditer(text))
        for literal in self._literals:
            index = text.find(literal)
            while index != -1:
                spans.append((index, index + len(literal)))
                index = text.find(literal, index + 1)
        # URLs join the span list so a secret query parameter is held until its
        # token terminates; an unterminated one ends at the buffer's end and so
        # holds the cut there until the rest arrives.
        spans.extend(match.span() for match in URL_TOKEN.finditer(text))
        return spans
