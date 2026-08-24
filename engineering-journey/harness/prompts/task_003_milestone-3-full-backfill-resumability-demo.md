Task: Milestone 3: Full 3-year backfill, with the real resumability demo

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1 (resumable backfill checkpoint) and 2 (real GitHub
ingestion for a single bounded window) are done and committed -- see
checkpoint.py, github_client.py, github_activity.py, and
app/CONTEXT.md's Decisions Log and "Fulcra SDK usage notes" section.

Your task right now
Extend Milestone 2's single-window ingestion into a full multi-period,
multi-repo backfill spanning approximately 3 years, using the
decaying-granularity boundary from the Interview phase (see
interview/findings.md at the repo root, decision #1): the most recent
90 days get ingested at a finer period granularity suitable for later
daily/weekly rollups; everything older than 90 days is ingested at a
coarser monthly granularity. This milestone is about the INGESTION
granularity/chunking and the real backfill loop across the full window
and all repos -- it does NOT need to build any rollup/summarization
logic yet (that's Milestones 4-5).

Specifically:

1. Repo enumeration across the full window: query
   GitHubClient.get_contributions_collection repeatedly across the full
   ~3-year span (chunked, since a single contributionsCollection call
   has a query date-range that GitHub may not want spanning years in one
   call -- check this empirically rather than assuming; the Architecture
   phase only validated a single-month query 3 years back, not a
   multi-year span in one call) to build the full set of repos the
   account has contributed to over that whole period, not just the
   repos active in one bounded window like Milestone 2 did.

2. Chunk the full ~3-year window into ingestion periods per the decaying
   granularity: last 90 days -> weekly chunks (so each ingested period
   is small enough to later support Milestone 4's day/week rollups);
   older than 90 days -> monthly chunks. Build the ordered list of
   (repo, period_start, period_end) work items across the full window
   and all repos -- this is the "items" list for
   checkpoint.process_with_checkpoint, extending what
   ingest_github_activity already does for a single window into the
   full multi-period case.

3. Real, at-scale resumability demo: run this full backfill for REAL
   against your own real GitHub account (same token/username pattern as
   Milestone 2 -- GITHUB_TOKEN/GITHUB_USERNAME env vars, available via
   `gh auth token` in this environment for testing), but interrupt it
   partway through (e.g. after a real, meaningful number of work items
   have been processed -- tens of items, not the full multi-year set,
   so this doesn't take an unreasonably long time to run) using the
   SAME interrupt_at_index mechanism already proven in Milestones 1-2.
   Kill it, restart from a fresh call (or ideally a genuinely fresh
   process if that's practical within a single task), and confirm it
   resumes at the correct point across potentially MULTIPLE repos and
   period chunks (not just within a single repo's single window like
   Milestone 1's fake-item test) -- this is what makes this milestone's
   resumability demo more real than Milestone 1's or Milestone 2's:
   multi-repo AND multi-period-granularity in one checkpointed run.
   You do not need to actually run and wait for the COMPLETE 3-year
   backfill to finish in this task (that could take a very long time
   against a real API) -- what matters is proving the FULL work-item
   list is correctly built across the whole window/all repos, and that
   interrupting and resuming partway through that real list works
   correctly. Note the actual full completed count and elapsed time you
   observe for however much of the real backfill you DO run, and record
   it in app/CONTEXT.md so Architecture risk #2 (real API/LLM call count
   and runtime for a full 3-year pull) has a real, extrapolated
   estimate instead of the pre-build guess from the Interview phase.

4. Keep using GitHubActivityRaw for the actual stored records (same
   record type from Milestone 2) -- this milestone does not introduce
   a new raw-data record type, only a bigger/smarter chunking and
   iteration strategy over the existing pieces.

Keep it minimal and correct rather than elaborate -- reuse
process_with_checkpoint and GitHubActivityRaw as-is; don't rebuild
checkpointing or the raw record type from scratch. When you're done,
give a short summary of the files you created/changed, the real
completed-item count and elapsed time you observed, and the test
results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section (including the "Known minor gap" note about
  clear_checkpoint/clear_raw_activities) before guessing a call
  signature.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the first two feature files).
- Update app/CONTEXT.md's Current State and Decisions Log to reflect
  this milestone's completion and the real call-count/runtime
  observation from step 3, per this project's own standing convention.
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing before finishing -- check via
  checkpoint.list_checkpoints() and github_activity.read_raw_activities()
  with no filters, and clear anything stray. This has been a real,
  repeated issue on this project (see app/CONTEXT.md's Decisions Log) --
  be especially careful here since this milestone will legitimately
  create MANY real checkpoint/activity records across many repos and
  periods during testing.
