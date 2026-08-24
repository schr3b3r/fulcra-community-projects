# Feature: Rollup Layer -- Day/Week (Recent 90 Days)

## Status
done

## Description
Builds the `ActivityRollup` Fulcra record type (`rollup.py`) and the
day/week rollup generation logic for the recent-90-day window, per
Interview decision #1's decaying-granularity boundary. A rollup reads
matching `GitHubActivityRaw` records for a period, computes structured
volume stats directly (no LLM needed for counts), and calls the
existing Gemini-based harness provider (`harness/providers/gemini.py`'s
`call_model`) to generate a narrative summary of the period's real
activity, storing an explicit `source_record_ids` provenance chain
alongside it. Generation across many periods is wired into
`checkpoint.process_with_checkpoint` (`(period_type, start_date,
end_date)` work items), so a multi-period rollup run is itself
resumable, the same pattern used for raw ingestion.

## Acceptance Criteria
- [x] `ActivityRollup` Fulcra record type (`MomentAnnotation`-based,
      JSON-note pattern, same as `GitHubBackfillProgress`/
      `GitHubActivityRaw`) with `period_type` ("day"/"week" this
      milestone; month/quarter/year in Milestone 5), `start_date`,
      `end_date`, `username`, `summary`, `stats` (commit/PR/issue/
      comment counts, total activities, repos touched), and
      `source_record_ids` (provenance -- the hard requirement from the
      brief/Architecture). `write_rollup(s)`/`read_rollups`/
      `clear_rollups` mirror the established write/read/clear pattern,
      including `expected_min_count`/`timeout_seconds` polling on
      `read_rollups` for the same eventual-consistency reason as
      `read_raw_activities`/`list_checkpoints`.
- [x] `generate_period_rollup` reads matching raw activity for a period
      (reuses `read_raw_activities`), computes stats directly (no LLM
      call), and calls `harness.providers.gemini.call_model` (the
      existing provider, not a second LLM integration) to generate the
      narrative summary — with a real, working real-data path (see
      Notes on the dotenv gap found and fixed).
- [x] `generate_day_week_rollups` chunks a date range into day AND week
      period work items (`generate_day_week_rollup_chunks`/
      `build_rollup_work_items`) and wires them into
      `process_with_checkpoint` unchanged — proven resumable with a
      real interrupt-at-index-2/resume test across 4 work items.
- [x] Proven end-to-end on REAL data: real `GitHubActivityRaw` records
      (topped up via a small real ingestion run covering 2026-07-15 to
      2026-08-23) rolled up for a real day (2026-08-20, 53 real
      activities across `schr3b3r/fulcra-community-projects`) produced
      a real, grounded LLM narrative (not boilerplate) that explicitly
      named real repo/feature content from that day's actual commits
      (flow-state-app-v2 harness build, audio pipeline, SvelteKit
      frontend) — verified by actually reading the generated text, not
      just checking it was non-empty.
- [x] Has automated tests (pytest) covering the above, and the FULL test
      suite passes (not just this feature's tests).

## Dependencies
`01_resumable_backfill_progress.md` (reuses `process_with_checkpoint`),
`02_github_raw_activity_ingestion.md` (reuses `read_raw_activities`,
`GitHubActivityRaw`).

## Notes
- **Real bug found and fixed:** `rollup.py`'s LLM narrative call failed
  silently with `GEMINI_API_KEY not set` whenever the test suite (or any
  script) didn't go through `harness/run_task.py`'s own `load_dotenv()`
  call — this includes the `git_commit` test gate itself (which invokes
  bare `python -m pytest` from `app/`, per `harness/tools/git_tool.py`),
  meaning every rollup generated *through the commit gate* would have
  silently produced boilerplate stats-only text instead of a real
  summary, with no visible error. Fixed two ways: (1) added
  `app/tests/conftest.py` to load `.env` before any test module runs,
  so the real LLM path is actually exercised during tests, and (2) the
  previously-silent `except Exception` fallback in
  `generate_period_rollup` now logs a warning with the real error
  instead of swallowing it — so a future real failure (e.g. rate limit,
  bad key) is visible instead of masquerading as a working summary. This
  was found by literally reading a generated summary's text and noticing
  it was generic stats-only boilerplate, not by a failing test.
- Task run for this milestone hit the harness's `max_iterations=30` cap
  before finishing (the model had built `rollup.py` and
  `tests/test_rollup.py` with 5/6 tests passing, 1 real-data test
  correctly `skip`ping since there was no raw data left in Fulcra after
  Milestone 3's cleanup) — completed manually: topped up a small real
  ingestion window, fixed the test's hardcoded stale date to dynamically
  pick whichever real day has the most activity (so it doesn't silently
  start skipping once that specific date's data is cleaned up later),
  fixed a `clear_rollups()` call bug (passed an unsupported `start_date`
  kwarg), found/fixed the dotenv gap above, ran the full suite, and
  committed.
- This milestone deliberately does NOT build month/quarter/year rollups
  or the notability signal — see Milestone 5+ in `plan.md`.
