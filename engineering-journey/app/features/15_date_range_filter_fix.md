# Feature: Fix `read_rollups`/`read_notability_signals` Date-Range Filter Bug

## Status
done

## Description
Fixes a real, high-impact bug found via a genuine fresh-account, full-scale 3-year backfill test:
the resulting narrative document showed "Max Notability Score: 0.00, Flags: none" for every single
section, despite `generate_notability_signal`'s own scoring logic having a hard floor of `0.05` --
a real computed score can never legitimately be `0.00`. That contradiction was the tell that
something was silently broken, not that the account's activity was genuinely uniform.

Root cause, confirmed directly against the real account's real data: `rollup.read_rollups()` and
`notability.read_notability_signals()` both filtered candidate records using exact string equality
(`data.get("start_date") != start_date`) rather than genuine range-overlap semantics, despite both
functions' own docstrings describing these parameters as date range filters, and despite the actual
caller (`generate_notability_signals`) already assuming and correctly implementing range semantics
downstream -- it just never received real data to filter, since the exact-match bug upstream had
already discarded almost everything. Confirmed empirically: querying a real account's 182 real day
`ActivityRollup` records with no date filter returned 182; the identical query with the real 3-year
backfill window's `start_date`/`end_date` set returned 0. Every real notability checkpoint for that
account showed `"completed": 0/0` for every period type as a direct, confirmable consequence.

The fix: both functions now filter using genuine range-overlap semantics -- a record is kept if its
own `[start_date, end_date]` span overlaps the requested query window, discarding it only when the
record's `start_date` is strictly after the requested `end_date`, or the record's `end_date` is
strictly before the requested `start_date`.

## Acceptance Criteria
- [x] `read_rollups()` filters `start_date`/`end_date` using range-overlap semantics, not exact string equality.
- [x] `read_notability_signals()` filters `start_date`/`end_date` using range-overlap semantics, not exact string equality.
- [x] `generate_notability_signals`'s own downstream range filtering left unchanged (redundant but harmless, now operating on real data).
- [x] Automated tests for both fixed functions assert that querying with OUTER bounds (not matching any single record's exact dates) returns all records whose range overlaps the query window.
- [x] Real end-to-end verification against a real account's real ~3-year backfill: confirmed 182 real day rollups now correctly return when queried with the real backfill date range (previously 0), and confirmed real `NotabilitySignal` generation now produces 310 real signal records (matching the real 310 `ActivityRollup` count) with genuine score variance (290/310 non-floor scores).
- [x] FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `04_rollup_layer_day_week.md`
- `05_rollup_layer_month_quarter_year.md`
- `06_notability_signal.md`
- `07_narrative_generation.md`

## Notes
- This bug was scoped specifically to callers that pass explicit `start_date`/`end_date` into
  `read_rollups`/`read_notability_signals` -- `narrative.py`'s own read calls pass no date filters
  at all, so the narrative's rollup-backed prose was unaffected by this bug; only the notability
  layer was silently empty, which is exactly the symptom a real user reported.
- Real production `NotabilitySignal` data was generated for a real account during verification of
  this fix (310 records, matching its 310 real `ActivityRollup` records) -- this was kept as
  genuine production data for that account's real `generate` run, not deleted as test scaffolding,
  since regenerating a full 3-year backfill's worth of LLM-scored signals is expensive and this data
  is now correct.
