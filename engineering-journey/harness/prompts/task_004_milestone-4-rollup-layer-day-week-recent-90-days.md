Task: Milestone 4: Rollup layer -- day/week (recent 90 days)

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-3 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, and app/CONTEXT.md's Decisions Log
and "Fulcra SDK usage notes" section. There is real GitHubActivityRaw
data already in Fulcra from previous milestones' real ingestion runs
(fulcradynamics/agent-skills, schr3b3r/agent-testing, and others) that
you can read and roll up -- you do not need to re-ingest from GitHub to
build/test this milestone, though you may top up a small additional
real window if useful.

Your task right now
Build the `ActivityRollup` Fulcra record type (per architecture.md:
one type, parameterized by a `period_type` field, rather than five
separate types) and the day/week rollup generation logic for the
recent-90-day window only (month/quarter/year rollups are Milestone 5).

Specifically:

1. `ActivityRollup` Fulcra record type (new module, e.g. rollup.py),
   following the same MomentAnnotation-based, JSON-note pattern as
   GitHubBackfillProgress and GitHubActivityRaw -- see checkpoint.py /
   github_activity.py for the established pattern and app/CONTEXT.md's
   "Fulcra SDK usage notes" for verified exact SDK call shapes. Fields
   should include at minimum: `period_type` ("day" | "week" -- month/
   quarter/year come in Milestone 5), `start_date`, `end_date`,
   `username`, a generated `summary` (LLM-produced narrative text
   summarizing the period's activity), structured volume stats (e.g.
   commit/PR/issue counts, repos touched), and a `source_record_ids`
   (or similarly named) field listing which GitHubActivityRaw record
   IDs the summary was actually built from -- this provenance chain is
   a hard requirement from the brief/Architecture, not optional. Include
   `write_rollup`/`read_rollups`/`clear_rollups` functions mirroring the
   existing write/read/clear pattern (including the same eventual-
   consistency polling treatment as read_raw_activities/list_checkpoints
   where it applies -- see app/CONTEXT.md's Decisions Log for why).

2. Rollup generation logic: given a period (start_date, end_date,
   period_type day or week) and a username, read the matching
   GitHubActivityRaw records (reuse read_raw_activities from
   github_activity.py), and produce an ActivityRollup: an LLM call
   (reuse the existing Gemini-based harness provider pattern -- see
   harness/providers/gemini.py's call_model -- do not build a second,
   parallel LLM integration) that summarizes the raw activity into a
   short narrative-ready summary, plus the structured volume stats
   computed directly from the raw records (counts don't need an LLM
   call -- only the narrative text does). Record which raw record IDs
   fed into it.

3. Wire this into checkpointing the same way ingestion was: reuse
   `checkpoint.process_with_checkpoint` so rollup generation over many
   periods is itself resumable, rather than a bespoke loop with no
   resumability. A day/week rollup "work item" is naturally a
   (period_type, start_date, end_date) tuple -- mirror the shape used
   for ingestion's (repo, start_date, end_date) work items in
   github_activity.py's generate_period_chunks/build_backfill_work_items
   if that's a natural fit, or a new, equally simple period-only work-
   item list if day/week doesn't need the repo dimension (rollups
   aggregate ACROSS repos for a period, unlike raw ingestion which is
   per-repo -- think about this rather than copying the ingestion
   work-item shape unreflectively).

4. Prove it end-to-end on REAL data: generate day and week rollups for
   a real, recent, bounded window using the real GitHubActivityRaw
   records already in Fulcra from earlier milestones (or a small top-up
   ingestion if the existing data doesn't cover a useful window) --
   read the generated ActivityRollup records back and confirm the
   summary text is real, non-empty, and actually reflects the underlying
   activity (not generic/hallucinated boilerplate) -- e.g. check that a
   real commit message or repo name mentioned in the raw data shows up
   meaningfully represented in the summary, or at minimum that the
   summary is clearly derived from real content rather than a fixed
   template string.

5. This milestone does NOT need month/quarter/year rollups or the
   notability signal -- those are Milestones 5-6. Keep day/week scoped
   to the most recent 90 days per the Interview/Architecture decaying-
   granularity boundary (you don't need to handle the case of rolling up
   activity older than 90 days into day/week granularity -- that's
   explicitly out of scope, monthly is the older-history granularity per
   Milestone 5).

Keep it minimal and correct rather than elaborate -- reuse
process_with_checkpoint, read_raw_activities, and the existing Gemini
provider as-is; don't rebuild checkpointing, raw-activity reading, or
LLM calling from scratch. When you're done, give a short summary of the
files you created/changed, a real example of a generated rollup summary
(actual text), and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. Note the current full suite runs real, sometimes slow, live
  API tests (both GitHub and Fulcra) -- budget for that; the git_commit
  test gate's timeout was raised to 300s in Milestone 3 for this reason.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section (including the "Known minor gap" note about
  clear_checkpoint/clear_raw_activities) before guessing a call
  signature.
- Reuse harness/providers/gemini.py's call_model for the LLM
  summarization call -- do not add a second LLM provider integration or
  call the Gemini SDK directly from app/ code.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the first three feature files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
