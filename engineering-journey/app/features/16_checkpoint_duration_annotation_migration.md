# Feature: Migrate GitHubBackfillProgress to DurationAnnotation

## Status
done

## Description
Migrates `checkpoint.GitHubBackfillProgress` -- the resumable-progress record written throughout
every phase of `backfill` -- from `MomentAnnotation` (with `recorded_at` set to ingestion time) to
`DurationAnnotation` (with `recorded_at = {start_time, end_time}` reflecting the specific work item
each checkpoint update actually covers). This was raised directly by a user reviewing this
project's real Fulcra usage: a real account with 3,391 real `GitHubBackfillProgress` records had
every single one clustered on just 2-3 calendar days, despite representing a multi-year backfill --
a structural type mismatch (a checkpoint covering a date range IS a duration, not a moment), not
just a wrong-value bug like Milestones 14/15 fixed for the other three record kinds.

Key implementation details and real platform constraints discovered while building this:
1. **A new catalog type name was required.** This account's real Fulcra catalog already had a
   custom type literally named `GitHubBackfillProgress`, created in Milestone 9, permanently
   classified as `MomentAnnotation` -- Fulcra does not support changing a custom type's base
   annotation type after creation. Reusing the same name would silently resolve to the old
   MomentAnnotation-based UUID regardless of the requested annotation_type. The new type is
   catalogued as `GitHubBackfillProgressV2` (`checkpoint.CATALOG_TYPE_NAME`); the JSON `note`
   payload's own `record_type` field is unchanged (`"GitHubBackfillProgress"`), since that's a
   separate, purely content-level concept from the real catalog/base-type identity.
2. **Zero-length DurationAnnotation records are silently dropped by Fulcra's backend.** Confirmed
   empirically (not just in theory) while debugging this migration: a `DurationAnnotation` record
   whose `start_time` and `end_time` are exactly equal reports write success but is never returned
   by any later read, filtered or unfiltered. This would have silently broken every checkpoint with
   no item-level date range (the fallback-to-`updated_at` case) and every single-day period chunk
   (`start_date == end_date`) with no error anywhere. Fixed by using end-of-day (`23:59:59Z`) for
   the `end_time` bound when formatting a plain date, and by adding a real 1-second offset in the
   no-date fallback instead of repeating the exact same instant for both bounds.
3. `process_with_checkpoint` now derives `start_date`/`end_date` from the CURRENT work item being
   processed (when the item is a dict exposing those keys, matching the shape already used
   throughout `github_activity.py`/`rollup.py`/`notability.py`'s own work items) -- not the overall
   task's full multi-year span.
4. `checkpoint._fetch_annotations_merged`'s real overmatching bug was fixed in the same pass: its
   backward-compatibility fallback previously queried ALL untagged `MomentAnnotation` records
   account-wide with no source filter at all whenever the tagged query failed, inflating a real
   3,391-record checkpoint query to 31,588 apparent "matches" against unrelated raw-activity/
   rollup/signal records.
5. **Old MomentAnnotation-shaped checkpoints are deliberately abandoned, not migrated.** This was
   an explicit, discussed design decision: checkpoints are ephemeral process state, not durable
   historical data worth a dual-read/migration path across this type change. The 3,391 real
   old-format records already in this account will simply stop being found by the new
   DurationAnnotation-based queries.

## Acceptance Criteria
- [x] `GitHubBackfillProgress` checkpoints are written as `DurationAnnotation` records with `recorded_at = {start_time, end_time}` reflecting the specific work item's own date range.
- [x] A new catalog type name (`GitHubBackfillProgressV2`) is used, since the existing `GitHubBackfillProgress` catalog entry is permanently a `MomentAnnotation` and cannot be reclassified.
- [x] `process_with_checkpoint` derives per-item `start_date`/`end_date` from real work item dicts during processing.
- [x] Checkpoints with no item-level date range, and single-day period checkpoints (`start_date == end_date`), remain genuinely readable -- confirmed via a real regression test after discovering Fulcra silently drops zero-length `DurationAnnotation` records.
- [x] `_fetch_annotations_merged`'s real overmatching bug is fixed (no longer fetches all untagged account-wide `MomentAnnotation`s as its fallback).
- [x] Old-format `MomentAnnotation`-shaped checkpoints are explicitly NOT read back after this migration (confirmed via a real regression test) -- deliberately abandoned, not migrated.
- [x] FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `09_custom_fulcra_data_types.md`
- `13_recorded_at_real_event_time.md`

## Notes
- This was raised directly by a user reviewing this project's real Fulcra usage in the portal web
  app -- see `app/CONTEXT.md`'s Milestone 17 Decisions Log entry for the full context.
- The zero-length-DurationAnnotation-drop behavior discovered here is a real Fulcra platform
  constraint worth remembering for any future DurationAnnotation-based record type in this or other
  projects, not just this one checkpoint type.
