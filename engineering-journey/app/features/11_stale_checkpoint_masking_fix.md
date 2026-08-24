# Feature: Stale Checkpoints Masking Improved Discovery Fix

## Status
done

## Description
Fixes a bug where a stale `"completed"` backfill checkpoint from an earlier, narrower discovery
pass (e.g. before private repo discovery was added or improved) silently masked subsequent backfill
runs for the same username and date range, preventing newly discoverable repositories from ever being ingested.

The fix makes `backfill_full_github_activity()` in `github_activity.py` delta-aware:
1. `backfill_full_github_activity()` records the actual `repo_names` list in checkpoint metadata.
2. Before trusting an existing `"completed"` checkpoint, it compares the freshly discovered `repo_names` against
   the stored repo set.
3. If new repos are detected (or if older checkpoints lack stored `repo_names`), it triggers a distinctly-tracked
   delta backfill with its own task ID (`<task_id>:delta:<hash>`), covering ONLY the new repos across the same period
   chunks.
4. Old repos already covered by the completed checkpoint are NOT reprocessed, preventing duplicate `GitHubActivityRaw`
   records.
5. Upon successful completion of the delta run, the parent checkpoint's metadata is updated to union the newly covered
   repos with the prior set.
6. `engineering_journey.py` logs and displays visible messages when a delta backfill occurs.

## Acceptance Criteria
- [x] `backfill_full_github_activity()` stores `repo_names` in checkpoint metadata.
- [x] Before trusting a `"completed"` checkpoint, `backfill_full_github_activity()` compares fresh repo set against stored `repo_names`.
- [x] If new repos exist, runs a distinctly-tracked delta backfill covering ONLY new repos x period chunks.
- [x] Avoids reprocessing existing repos and avoids duplicating `GitHubActivityRaw` records in Fulcra.
- [x] Updates parent checkpoint metadata upon successful completion of delta backfill.
- [x] `engineering_journey.py` logs/prints delta status and new repos list when a delta backfill occurs.
- [x] Real data proof: verified on live account (`schr3b3r`) that a narrow completed checkpoint followed by an expanded backfill call triggers delta backfill, ingests new repo, and leaves original repo's record count unchanged.
- [x] Cleaned up all test checkpoints and raw activity test records created during verification.
- [x] Has automated tests covering delta backfill behavior, and the FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `03_full_3year_backfill_chunking_resumability.md`
- `10_private_repo_discovery.md`

## Notes
- Older checkpoints without stored `repo_names` metadata are treated conservatively (unknown coverage / empty set),
  ensuring all freshly discovered repos are verified via delta backfill rather than being silently skipped.
