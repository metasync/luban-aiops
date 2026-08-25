# SPEC-033 Tasks: Confirmation Card Turn Anchoring

## Backend: persist the parking turn ordinal (R-1)

- [x] `make_record` accepts and stores `turn_index` (default None).
- [x] DDL gains the `turn_index INTEGER` column; `initialize()` runs an
      idempotent `ADD COLUMN IF NOT EXISTS` migration for existing tables.
- [x] `_INSERT_PARKED` and all `_LOAD_*` selects carry the column;
      `_row_to_record` maps it.
- [x] `_build_confirmation_frame` takes `turn_index` and both call sites
      (chat stream, resume stream) pass the already-computed ordinal.
- [x] pytest: store round-trips `turn_index`; legacy rows load as None.

## Surface: additive field on session detail (R-2)

- [x] `ConfirmationRecordModel` gains `turn_index: int | None = None`.
- [x] `agent-session.schema.json` confirmation item gains the additive
      property with the SPEC-033 note.
- [x] pytest: session-detail payload includes `turn_index` for new parks.

## Portal: anchor cards by turn (R-3)

- [x] `ConfirmationRecord` type gains `turn_index?: number | null`.
- [x] `attachConfirmations` anchors in-range records to their own turn;
      null/missing/out-of-range falls back to the legacy anchor.
- [x] vitest: multi-record anchoring, legacy fallback, pending anchoring.

## Delivery gate

- [x] `make verify` green; spec closure on all four surfaces.
- [x] CHANGELOG + release notes; 0.15.0 version lockstep.
- [x] Commit train, build, deploy, smoke, tag, security gate, push.
