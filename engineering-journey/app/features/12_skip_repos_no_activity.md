# Feature: Skip Repositories With No Author Activity Before Per-Chunk Ingestion

## Status
done

## Description
Optimizes GitHub activity backfill by performing a lightweight, range-wide author activity pre-check
on discovered repositories prior to building per-period-chunk work items. Repositories in which the user
has zero author activity across the entire requested date window are skipped up front, avoiding dozens of
wasted Search API queries (`fetch_commits`, `fetch_pull_requests`, `fetch_issues`) per inactive repository.

The implementation:
1. Adds `GitHubClient.has_author_activity(repo_name, start_date, end_date) -> bool` which executes up to 2
   REST Search API requests with `per_page=1` across the full date range (1 for `search/commits`, and 1 for
   `search/issues` covering both issues and PRs via `type:issue,pr`). Returns `True` immediately on commit match,
   short-circuiting the second call.
2. Refactors `_paginate_search()` in `GitHubClient` to share a common rate-limit retrying helper `_execute_search_request()`.
3. Updates `backfill_full_github_activity()` in `github_activity.py` to filter discovered `repo_names` (and `new_repos`
   in delta backfill mode) using `has_author_activity()` before creating work items via `build_backfill_work_items()`.
4. Reports `repos_skipped_no_activity` in the returned summary dict and logs/prints skipped repositories clearly.
5. Records both `repo_names` (all evaluated discovered repos) and `active_repo_names`/`repos_skipped_no_activity` in
   checkpoint metadata so future runs recognize skipped repos as evaluated.

## Acceptance Criteria
- [x] Added `has_author_activity(repo_name, start_date, end_date) -> bool` to `GitHubClient` making up to 2 REST Search API calls across full range.
- [x] `has_author_activity` short-circuits to `True` on commit match without making issue/PR search calls.
- [x] `backfill_full_github_activity()` filters discovered repos (and delta `new_repos`) using `has_author_activity` before building work items.
- [x] Repositories with no author activity are excluded from `build_backfill_work_items` and never passed to `_ingest_single_item_activity`.
- [x] Summary dict includes `repos_skipped_no_activity` list.
- [x] Checkpoint metadata stores discovered repo coverage so subsequent runs do not re-evaluate skipped repos as unverified.
- [x] Has automated unit tests with mocked GitHub Search API and live API test fallback covering `has_author_activity` and skipping logic.
- [x] FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `02_github_raw_activity_ingestion.md`
- `03_full_3year_backfill_chunking_resumability.md`
- `10_private_repo_discovery.md`
- `11_stale_checkpoint_masking_fix.md`

## Notes
- Trade-off note: Repos with author activity pay up to 2 extra Search API calls upfront (the pre-check itself) before per-chunk work begins. For a multi-chunk backfill (~50 chunks, 150 calls per repo), a zero-activity repo drops from 150 calls down to 2 calls (saving 148 calls per inactive repo). For repos with active work spread across many chunks, the 2 upfront calls are a net win; for a single-chunk active repo, it is a minor overhead (+2 calls).
