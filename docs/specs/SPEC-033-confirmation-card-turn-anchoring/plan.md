# SPEC-033 Plan: Confirmation Card Turn Anchoring

## Approach

Store the parking turn's ordinal on the durable record at park time, carry
it through the session-detail surface as an additive nullable field, and
anchor seeded cards by it in the portal. Everything additive; the fallback
keeps pre-delivery records rendering exactly as today.

## Backend changes

- `confirmation_records.py`
  - `make_record` gains `turn_index: int | None = None` and writes it into
    the record dict.
  - DDL: `turn_index INTEGER` column in the `CREATE TABLE`, plus an
    idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS turn_index INTEGER`
    executed by `initialize()` so clusters with a pre-spec table migrate in
    place (new rows NULL).
  - `_INSERT_PARKED` gains the column; all four `_LOAD_*` selects gain it
    in the same position; `_row_to_record` maps it (None stays None).
  - In-memory store needs no change (it round-trips the record dict).
- `runtime_kernel.py`
  - `_build_confirmation_frame` gains a `turn_index: int` parameter; both
    call sites (chat stream ~L918, resume stream ~L1163) already compute
    `turn_index = self._count_user_turns(agent)` in scope and pass it
    through to `make_record`.
- `schemas/v2.py`
  - `ConfirmationRecordModel` gains `turn_index: int | None = None`
    (additive, not required — inbox rows built by hand keep working).

## Contract change

- `shared/shared-contracts/schemas/agent-session.schema.json`: add
  `"turn_index": {"type": ["integer", "null"]}` to the confirmation record
  item properties (not added to `required`); extend the field description
  sentence with the SPEC-033 note.

## Portal changes

- `api/sessions.ts`: `ConfirmationRecord` gains `turn_index?: number | null`.
- `chat/transcript.ts` `attachConfirmations`: when
  `typeof record.turn_index === "number"` and
  `0 <= turn_index < turns.length`, anchor the card to
  `turns[record.turn_index]`; otherwise fall back to the existing
  newest-turn/synthetic-turn anchoring. `confirmationPending` marking
  follows the anchored target unchanged.

## Test plan

- pytest (`products/agent-platform`):
  - record store round-trip keeps `turn_index` (memory + fake-driver
    Postgres paths); legacy row shape (no column value) loads as None.
  - kernel park writes the record with the current turn ordinal (extend the
    existing `_build_confirmation_frame` tests).
  - session-detail payload includes `turn_index` for parked records.
- vitest (`web-ui/app`):
  - seeding anchors two decided records to their own turns;
  - null / out-of-range `turn_index` falls back to newest-turn anchoring;
  - pending card anchors to its turn and sets `confirmationPending` there.
- Full gate: `make verify` (agent-platform pytest + portal vitest/tsc).

## Out of scope

- No backfill of pre-delivery records, no inbox layout change, no change to
  decision mechanics or the SPEC-032 poll.

## Release

- 0.15.0 minor train (additive wire field + new persisted column).
