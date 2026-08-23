# Feature: Full 3-Year Backfill — Chunking & Multi-Repo/Multi-Period Resumability

## Status
done

## Description
Extends Milestone 2's single-window ingestion into a full ~3-year,
multi-repo backfill using the decaying-granularity boundary from the
Interview phase: the most recent 90 days are chunked weekly (to support
later daily/weekly rollups), everything older is chunked monthly. Adds
repo enumeration across the full window (`GitHubClient.enumerate_repositories`),
period chunking (`generate_period_chunks`), the combined work-item list
builder (`build_backfill_work_items`), and the top-level entrypoint
(`backfill_full_github_activity`) that wires all of it into the existing
`checkpoint.process_with_checkpoint` mechanism — reusing it as-is rather
than building a second resumability mechanism.

Also fixes a real bug found while proving this milestone: GitHub's
REST Search API has a much stricter rate limit (30 req/min authenticated)
than the core REST API, and 3 search calls per work item across tens of
items in quick succession hits it easily during a real backfill.
`GitHubClient._paginate_search` now detects a rate-limit 403 (via
`X-RateLimit-Remaining`/message content, not just any 403) and retries
with a computed backoff (`Retry-After` or `X-RateLimit-Reset` header,
falling back to a flat 60s), up to 5 retries, instead of failing the
whole backfill on an expected, transient condition.

## Acceptance Criteria
- [x] `GitHubClient.enumerate_repositories` walks the full date window in
      <=1-year chunks and merges results — empirically required: a real
      GraphQL call spanning >1 year returns a real `VALIDATION` error
      ("The total time spanned by 'from' and 'to' must not exceed 1
      year"), confirmed against the live API, not assumed from docs.
- [x] `generate_period_chunks` produces weekly chunks for the most recent
      90 days and monthly chunks for everything older, chronologically
      ordered, with no gaps or overlaps, covering the full requested
      window exactly.
- [x] `build_backfill_work_items` combines repos x period chunks into a
      single ordered work-item list (chronological by period, then
      alphabetical by repo within a period).
- [x] `backfill_full_github_activity` wires enumeration + chunking + the
      work-item list into `process_with_checkpoint` unchanged (no new
      resumability mechanism), reusing `_ingest_single_item_activity`
      (factored out of Milestone 2's `ingest_github_activity` so both
      entrypoints share the same per-item fetch/store logic).
- [x] Real, at-scale resumability demo: a real backfill run across 2
      real repos and 15 real period chunks (30 real work items, spanning
      both monthly and weekly granularity) was interrupted at index 5 via
      `interrupt_at_index`, then resumed via a fresh call, and completed
      all 30 items with zero duplicates or gaps (`completed_items_count
      == total_items`, `resumed_from_index == 5`).
- [x] Real GitHub Search API rate-limit handling, found and fixed via the
      resumability demo itself hitting it live (see Notes) — not
      speculative/defensive code added without a real trigger.
- [x] Has automated tests (pytest) covering the above, and the FULL test
      suite passes (not just this feature's tests).

## Dependencies
`01_resumable_backfill_progress.md` (reuses `process_with_checkpoint`
directly), `02_github_raw_activity_ingestion.md` (reuses
`GitHubActivityRaw`, `write_raw_activities`, and the per-item fetch
logic factored into `_ingest_single_item_activity`).

## Notes
- Real observed numbers (see `app/CONTEXT.md`'s Decisions Log for the
  extrapolated full-backfill estimate): enumerating repos across a real
  ~3-year window (2023-08-23 to 2026-08-23) for account `schr3b3r` took
  ~0.7s and found 8 repos; that window chunks into 47 period chunks and
  376 total work items. The real interrupt/resume demo (2 repos, 15
  period chunks, 30 work items, spanning both granularities) completed
  in 137s total across both calls (first call: process 0-4 then
  interrupt; second/resumed call: process 5-29) — see CONTEXT.md for
  the extrapolation to the full 376-item case.
- This milestone deliberately does NOT build rollups or the notability
  signal — see Milestone 4+ in `plan.md`.
