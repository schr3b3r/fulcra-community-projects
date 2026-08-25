# Feature: `recorded_at` Reflects Real Historical Event/Period Time

## Status
done

## Description
Fixes a foundational correctness bug: every writer in this project previously set the Fulcra
`recorded_at` field to ingestion time (when the backfill script happened to run), never the real
historical event/period time the record actually describes. Since Fulcra's query surface is
fundamentally time-range-based, this made genuinely time-scoped queries (e.g. "what happened in
March 2024") return nothing even though the data existed -- defeating the point of storing it in
Fulcra as durable, time-queryable data rather than an arbitrary blob store.

The implementation:
1. `GitHubActivityRaw.to_fulcra_record()`: `recorded_at` is now the real GitHub event timestamp
   (`self.timestamp`), formatted via a new `_format_iso_timestamp()` helper.
2. `ActivityRollup`/`NotabilitySignal.to_fulcra_record()`: `recorded_at` is now the period's
   `start_date`, formatted the same way -- anchoring a period record at when its period began.
3. Added `compute_deterministic_activity_id(activity_type, activity_id, repo_name)` in
   `github_activity.py` (MD5 hash of the three fields, converted to a UUID) wired into
   `GitHubActivityRaw.to_fulcra_record()`'s `id` field, fixing a previously-documented dedup gap
   (`write_raw_activities` was a pure append with no dedup by `activity_id`).
4. `updated_at` (ingestion/last-write time) stays inside the JSON `note` payload for all three
   record kinds -- separate from `recorded_at`, not conflated with it.

Deliberately out of scope (see `app/CONTEXT.md`'s Milestone 14 Decisions Log entry for full
reasoning): base-type reclassification of `ActivityRollup`/`NotabilitySignal` from
`MomentAnnotation` to `DurationAnnotation`; deterministic IDs for rollups/signals; bulk migration
of already-written records with the old (wrong) `recorded_at` values.

## Acceptance Criteria
- [x] `GitHubActivityRaw.to_fulcra_record()`'s `recorded_at` reflects the real GitHub event timestamp, not ingestion time.
- [x] `ActivityRollup`/`NotabilitySignal.to_fulcra_record()`'s `recorded_at` reflects the period's real `start_date`, not ingestion time.
- [x] `updated_at` (ingestion/last-write provenance) remains available inside the JSON `note` payload for all three record kinds.
- [x] Added `compute_deterministic_activity_id()` producing deterministic, distinct UUIDs from `(activity_type, activity_id, repo_name)`.
- [x] Automated unit tests pin `recorded_at` to real event/period time for all three record kinds.
- [x] Automated tests cover determinism/distinctness of `compute_deterministic_activity_id()`.
- [x] A real live test confirms a record with a historical `recorded_at` is genuinely discoverable via a Fulcra time-range read scoped to that period.
- [x] FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `02_github_raw_activity_ingestion.md`
- `04_rollup_layer_day_week.md`
- `06_notability_signal.md`
- `09_custom_fulcra_data_types.md`

## Notes
- This was raised directly by a user reviewing the project's Fulcra usage, not discovered
  internally -- see `app/CONTEXT.md`'s Milestone 14 Decisions Log entry for the full context and
  the `fulcra-ingest` skill's documented `recorded_at` convention this project should have
  followed from the start.
- Future follow-up (not this task): consider migrating `ActivityRollup`/`NotabilitySignal` from
  `MomentAnnotation` to `DurationAnnotation` so `recorded_at` can be a true `{start_time, end_time}`
  span rather than an anchor-at-start-date approximation.
