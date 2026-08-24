Task: Milestone 5: Rollup layer -- month (older history) + quarter/year (both)

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-4 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, and app/CONTEXT.md's
Decisions Log and "Fulcra SDK usage notes" section. rollup.py already
has the `ActivityRollup` record type (period_type/start_date/end_date/
username/summary/stats/source_record_ids) and day/week rollup
generation wired into checkpointing -- read it before writing new code,
since month/quarter/year rollups should extend/reuse this, not duplicate
it. There is real GitHubActivityRaw data already in Fulcra you can read
directly (no need to re-ingest from GitHub, though you may top up a
small additional window if useful -- see how Milestone 4 topped up a
window when the previous milestone's own test cleanup had emptied
Fulcra).

Your task right now
Extend the `ActivityRollup` rollup layer with `period_type=month` (for
history older than 90 days, skipping the weekly layer entirely per the
Interview decision) and `period_type=quarter`/`year` (built on top of
BOTH the recent week-based layer and the older month-based layer --
same output shape, different lower-layer inputs).

Specifically:

1. Month rollups: for history older than 90 days, generate
   `ActivityRollup` records with `period_type="month"` directly from
   `GitHubActivityRaw` records (same approach as day/week: compute
   stats directly, call harness.providers.gemini.call_model for the
   narrative, record source_record_ids provenance) -- there is no
   weekly layer to build on for old history, per the Interview decision
   (a 3-year backfill produces ~90 days of daily/weekly plus ~33 months
   of monthly, skipping weekly for old history entirely). Reuse
   generate_period_rollup's stats-computation and provenance logic
   rather than rewriting it for month -- the period-type-specific
   difference here is really just the date-chunking granularity, not
   the underlying computation, so check whether generate_period_rollup
   already generalizes to period_type="month" as-is (it takes
   period_type as a parameter already) before adding new machinery.

2. Quarter/year rollups: these summarize a *layer* of rollups, not raw
   activity directly -- a quarter/year rollup for the recent window is
   built from the WEEK-level ActivityRollup records under it; a
   quarter/year rollup for older history is built from the MONTH-level
   ActivityRollup records under it. Same ActivityRollup output shape
   (period_type="quarter"/"year") but the provenance/source_record_ids
   should reference the IDs of the lower-layer ActivityRollup records
   it was built from, not raw GitHubActivityRaw record IDs directly --
   this is the "uniform top of the pyramid, differently-grained base"
   design from Interview finding #1, and matters for the provenance
   requirement to still be meaningful at this layer (a reader of a
   quarter rollup should be able to trace it to the weeks/months that
   fed it, and from there down to raw activity). You will likely need a
   new function (e.g. generate_layer_rollup or similar) since this
   reads ActivityRollup records as input rather than GitHubActivityRaw
   records -- but keep it structurally parallel to
   generate_period_rollup (compute stats by aggregating the child
   rollups' stats, call the same LLM provider for the narrative, same
   ActivityRollup output dataclass) rather than a divergent design.

3. Chunking: build the month/quarter/year period boundaries (e.g.
   calendar months, calendar quarters, calendar years -- pick a
   sensible, clearly-documented convention and apply it consistently)
   and wire generation across many periods into
   checkpoint.process_with_checkpoint the same way day/week rollups
   are, so a multi-period month/quarter/year rollup run is itself
   resumable.

4. Prove it end-to-end on REAL data:
   - Generate at least one real month rollup from real
     GitHubActivityRaw records older than 90 days (top up a small real
     ingestion window for a period 3+ months back if the existing raw
     data doesn't already cover one -- ingest_github_activity/
     backfill_full_github_activity from github_activity.py can do
     this).
   - Generate at least one real quarter or year rollup built from real
     lower-layer ActivityRollup records (either real week rollups from
     Milestone 4's recent window, or real month rollups from this
     milestone), and confirm its source_record_ids correctly reference
     those lower-layer rollup records' real Fulcra IDs.
   - Read the generated rollups back and confirm the summary text is
     real and reflects the underlying activity/lower-layer summaries
     (not generic boilerplate) -- same verification bar as Milestone 4
     (actually read the text, don't just check it's non-empty).

5. This milestone does NOT need the notability signal or the final
   narrative-generation pass -- those are Milestones 6-7.

Keep it minimal and correct rather than elaborate -- reuse
process_with_checkpoint, generate_period_rollup (or a clear, structurally
-parallel sibling function), read_raw_activities, read_rollups, and the
existing Gemini provider; don't rebuild any of these from scratch. When
you're done, give a short summary of the files you created/changed, a
real example of a generated month rollup summary AND a real example of a
generated quarter/year rollup summary (actual text), and the test
results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. The current full suite runs real, sometimes slow, live API
  tests (both GitHub and Fulcra) -- budget for that; expect the full
  suite to take several minutes.
- IMPORTANT: any test that needs a real Gemini call (or any other
  environment-configured credential) will silently produce wrong
  fallback output instead of failing if GEMINI_API_KEY isn't loaded --
  app/tests/conftest.py already loads .env for the pytest suite (added
  in Milestone 4 after this exact failure mode was found), so this
  should already work when running via `pytest`/`python -m pytest` from
  app/ -- but if you write any new one-off verification script outside
  pytest, remember to load .env yourself (see app/tests/conftest.py's
  docstring for why this matters).
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section before guessing a call signature.
- Reuse harness/providers/gemini.py's call_model for any LLM
  summarization call -- do not add a second LLM provider integration.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the first four feature files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
