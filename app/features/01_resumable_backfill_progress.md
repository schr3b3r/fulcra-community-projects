# Feature: Resumable Backfill Progress Checkpoint

## Status
done

## Description
Provides durable checkpoint tracking for GitHub backfill progress stored in Fulcra as custom `MomentAnnotation` records.
Enables a backfill task to be interrupted mid-process (e.g. process killed at item 47) and resumed from a fresh process starting at item 48 without re-processing items 1-47 or skipping any work.

## Acceptance Criteria
- [x] `GitHubBackfillProgress` data structure represents checkpoint state (task_id, stage, repo_name, start_date, end_date, last_processed_item, last_processed_index, completed_items_count, total_items, status, updated_at, metadata).
- [x] `write_checkpoint` writes durable checkpoint records to Fulcra using the `fulcra-api` SDK as JSON-encoded `MomentAnnotation` objects.
- [x] `read_checkpoint` queries Fulcra for the most recent progress checkpoint matching a given `task_id`.
- [x] Resumability verified in an isolated test:
  - Process items 1 through 100.
  - Kill / interrupt the process at item 47.
  - Restart from a fresh process reading the saved checkpoint.
  - Confirm execution resumes at item 48 and completes items 48 to 100 without reprocessing 1-47 or skipping any items.
- [x] Has automated tests (pytest) covering the above criteria, and the FULL test suite passes (not just this feature's own tests) — see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
none

## Notes
- Does not call the GitHub API (pure Fulcra checkpoint plumbing, tested against fake work items).
- Follows Fulcra SDK usage conventions documented in `app/CONTEXT.md`.
- `list_checkpoints` accepts an `expected_task_ids` + `timeout_seconds` polling option: Fulcra writes are eventually consistent, so a query run immediately after a write can legitimately miss it for a short window. `test_list_checkpoints` originally failed intermittently for exactly this reason (querying right after two back-to-back writes with no poll/retry) — fixed by adding this option and using it in the test, rather than adding an arbitrary blind `sleep()`.
