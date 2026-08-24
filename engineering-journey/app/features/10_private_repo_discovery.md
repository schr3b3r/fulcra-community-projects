# Feature: Private Repo Discovery Fix

## Status
done

## Description
Fixes private repository discovery in `GitHubClient.enumerate_repositories()` by
combining listing-based repository discovery (`GET /user/repos?affiliation=owner,collaborator,organization_member`)
with GraphQL `contributionsCollection` query chunking. GraphQL `contributionsCollection`
can miss private repositories even when the user has active contributions in them.
The new `list_accessible_repositories(pushed_after, pushed_before)` method enumerates
all repositories accessible to the user (paginated) and prefilters by `pushed_at` date window.
`enumerate_repositories()` unions these results, ensuring private repositories are discovered
before downstream per-repo activity fetching (commits, PRs, issues via REST Search API) runs.

## Acceptance Criteria
- [x] `GitHubClient.list_accessible_repositories(pushed_after, pushed_before)` calls
      `GET /user/repos?affiliation=owner,collaborator,organization_member` with pagination and
      filters returned repositories by `pushed_at` date window when provided.
- [x] `GitHubClient.enumerate_repositories()` unions `list_accessible_repositories()` discovery
      with GraphQL `contributionsCollection` chunked queries and deduplicates the result.
- [x] Verified on REAL data: confirmed known private repository (`schr3b3r/shimmer`) was
      absent in `enumerate_repositories()` before fix and present after fix. Confirmed real
      `GitHubActivityRaw` records for private repo activity are ingested into Fulcra and
      read back successfully.
- [x] Cleaned up all real Fulcra records created during verification.
- [x] Has automated tests (pytest) covering unit pagination/filtering and real API execution,
      and the FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `02_github_raw_activity_ingestion.md`
- `03_full_3year_backfill_chunking_resumability.md`

## Notes
- Search API functions (`fetch_commits`, `fetch_pull_requests`, `fetch_issues`, `_paginate_search`)
  worked correctly for private repositories once the repository name was in `repo_names`.
  The gap was solely upstream in repository discovery (`enumerate_repositories()`).
