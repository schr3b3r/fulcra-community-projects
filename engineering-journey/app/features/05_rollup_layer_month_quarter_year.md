# Feature: Month, Quarter, and Year Rollup Generation

## Status
done

## Description
Extends the rollup layer with monthly rollups for history older than 90 days (computed directly from raw GitHub activity records) and quarterly/yearly rollups (synthesized from lower-layer rollups such as week or month rollups). Provides structured volume stats, LLM narrative summaries, explicit lower-layer provenance tracking, and resumable execution backed by Fulcra checkpoints.

## Acceptance Criteria
- [x] Generates `ActivityRollup` records with `period_type="month"` directly from `GitHubActivityRaw` records for historical periods, recording volume stats, LLM narrative summaries, and raw activity record IDs in `source_record_ids`.
- [x] Generates `ActivityRollup` records with `period_type="quarter"` and `period_type="year"` from lower-layer rollups (week or month rollups), aggregating child stats, synthesizing child narrative summaries, and referencing lower-layer `ActivityRollup` record IDs in `source_record_ids`.
- [x] Provides period chunking for calendar months, quarters, and years, integrated into `checkpoint.process_with_checkpoint` for resumable execution across multiple period chunks.
- [x] Verified on real data: generated real month rollups and real quarter layer rollups in Fulcra, confirming narrative summaries are grounded in actual content and `source_record_ids` match lower-layer rollup IDs.
- [x] Has automated tests (pytest) covering the above criteria, and the FULL test suite passes (not just this feature's own tests) — see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `02_github_raw_activity_ingestion.md`
- `04_rollup_layer_day_week.md`

## Notes
- Month rollups skip the weekly layer for history older than 90 days per Interview decision #1.
- Quarter and year rollups form the uniform top of the rollup pyramid, built on top of weekly rollups for recent history and monthly rollups for older history.
- `generate_layer_rollup`'s `child_period_types` defaults to `["week", "month"]`, deliberately excluding `"day"` -- `generate_day_week_rollups` (Milestone 4) always writes both a day AND a week `ActivityRollup` covering the same dates, so a naive "aggregate every rollup I find" would double-count that activity. Found and fixed after the initial task run (which only tested the month-child path, not the day+week overlap case) -- see the regression test and CONTEXT.md's Decisions Log.
