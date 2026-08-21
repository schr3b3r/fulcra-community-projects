# Feature: GitHub Raw Activity Ingestion

## Status
done

## Description
A GitHub API client (`github_client.py`) that authenticates via a
runtime-supplied token/username (constructor args or `GITHUB_TOKEN`/`GITHUB_USERNAME`
env vars — never `gh` CLI, never assumes the host machine's `gh` session),
queries GitHub's GraphQL `contributionsCollection` for per-repo activity
breakdown and REST Search API for commit/PR/issue content, and stores
the results durably in Fulcra as `GitHubActivityRaw` records
(`github_activity.py`). Ingestion is wired into Milestone 1's
`process_with_checkpoint` mechanism (checkpointing by repo, within a
given date range), so a bounded ingestion run is itself resumable —
not a separate, parallel mechanism from the backfill checkpoint.

## Acceptance Criteria
- [x] `GitHubClient` accepts a GitHub identity (token + username) as
      runtime configuration (constructor args or env vars), not by
      shelling out to `gh` or assuming a specific machine's `gh` session.
- [x] `GitHubClient.get_contributions_collection` queries the real
      GraphQL `contributionsCollection` endpoint and returns per-repo
      commit/PR/review/issue counts for a date range.
- [x] `GitHubClient.fetch_commits`/`fetch_pull_requests`/`fetch_issues`
      query the real REST Search API (paginated) for actual content
      (commit messages, PR/issue titles and bodies) within a bounded
      window.
- [x] `GitHubActivityRaw` Fulcra record type (JSON-note `MomentAnnotation`,
      same pattern as `GitHubBackfillProgress`) with `write_raw_activities`/
      `read_raw_activities`/`clear_raw_activities`.
- [x] `ingest_github_activity` wires ingestion into
      `checkpoint.process_with_checkpoint` (checkpointing per repo, not a
      separate resumability mechanism) — verified with a real interrupt-
      and-resume test against real repos and the real GitHub API.
- [x] Proven end-to-end on a small, real, bounded window (June 2026, one
      real account's real activity across `fulcradynamics/agent-skills`
      and `schr3b3r/agent-testing`): real records ingested into Fulcra,
      read back, and confirmed to contain real, non-empty commit/PR
      content — not just "some records exist."
- [x] Has automated tests (pytest) covering the above criteria, and the
      FULL test suite passes (not just this feature's own tests) — see
      `app/ENGINEERING_STANDARDS.md`.

## Dependencies
`01_resumable_backfill_progress.md` (reuses `process_with_checkpoint`
directly rather than building a separate resumability mechanism).

## Notes
- Live tests in `test_github_activity.py` that need a real GitHub token
  read it from `GITHUB_TOKEN`/`GITHUB_USERNAME` env vars (falling back to
  `gh auth token` only as a LOCAL TESTING convenience in the test file
  itself — never in the actual `GitHubClient` implementation, which has
  no `gh` dependency at all) and `pytest.skip()` cleanly if no token is
  available, so the suite doesn't hard-fail on a machine with no GitHub
  credentials configured.
- `read_raw_activities` (like `checkpoint.list_checkpoints` before it)
  needed an `expected_min_count` + `timeout_seconds` polling option to
  avoid an intermittent test failure from Fulcra's eventual consistency
  — a query run immediately after a write can legitimately miss it for
  a short window. See `app/CONTEXT.md`'s Decisions Log.
- This milestone deliberately does NOT build the full 3-year backfill
  loop, rollups, or notability signal — see Milestone 3+ in `plan.md`.
