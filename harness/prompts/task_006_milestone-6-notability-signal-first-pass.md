Task: Milestone 6: Notability signal (first pass)

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-5 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, and app/CONTEXT.md's
Decisions Log and "Fulcra SDK usage notes" section. rollup.py has the
full ActivityRollup layer (day/week/month/quarter/year), each with
structured stats (commit/PR/issue/comment counts, repos touched) and a
provenance chain (source_record_ids). Read rollup.py before writing new
code. There is real GitHubActivityRaw and (after you generate it)
ActivityRollup data already in Fulcra you can read directly.

Your task right now
Implement a first-pass "notability" signal: a per-rollup-period score/
label indicating whether that period stands out, based on:
- Activity volume/variance vs. the account's own personal baseline (not
  a fixed global threshold -- "notable" is relative to how active this
  specific person normally is).
- Detected "firsts" or "switches" (e.g. first activity in a new repo,
  a period where the dominant repo/focus area changed from the prior
  period).
- Streaks and gaps (a period of unusually sustained activity, or a
  period of unusually low/no activity following an active stretch --
  per Interview decision #3, gaps are real, narratively significant
  data, not noise to hide).

Specifically:

1. `NotabilitySignal` Fulcra record type (new module, e.g. notability.py),
   following the same MomentAnnotation-based, JSON-note pattern as the
   other record types. Fields should include at minimum: which rollup
   period it was computed for (period_type/start_date/end_date/username),
   a notability score or label (your choice of shape -- e.g. a 0-1 score,
   or a small set of categorical flags like "high_volume"/"gap"/
   "new_repo"/"focus_switch" -- pick something the Milestone 7 narrative
   pass can act on, and document your choice), a short explanation of
   WHY it was flagged (e.g. "3x normal commit volume" or "first activity
   in org/new-repo" or "14-day gap after an active month"), and a
   `source_rollup_id` (or similar) referencing the ActivityRollup record
   it was computed from -- the provenance requirement applies here too.
   Include write/read/clear functions mirroring the established pattern.

2. Notability computation logic: given a rollup period and the
   account's history of prior rollups (same period_type, to compare
   like with like -- e.g. compare a week's stats against the
   distribution of the account's other weeks, not against a day or a
   month), compute:
   - A baseline (e.g. mean/median of total_activities or commit_count
     across the account's own rollups of that period_type) and how far
     this period deviates from it.
   - Whether this period's dominant repo (by activity count) differs
     from the previous period's dominant repo (a focus switch), or
     whether this period includes a repo not seen in any prior period
     (a "first").
   - Whether this period is unusually quiet (well below baseline,
     including zero activity) immediately following an unusually active
     stretch (a gap worth naming, not silently skipping).
   This does NOT need to be a single unified formula -- keep it as a
   set of clearly separable checks/signals per the Interview's explicit
   "expect to revise this" framing, and design generate_notability_signal
   (or similar) so a future pass could swap in a different scoring
   approach without touching rollup.py or the ingestion/checkpoint code.
   An LLM call is optional here (the checks above are mostly
   arithmetic/comparison, not narrative generation) -- if you do use one
   (e.g. to help phrase the explanation text), reuse
   harness.providers.gemini.call_model, don't add a new integration.

3. Wire computation across many periods into
   checkpoint.process_with_checkpoint the same way rollup generation is,
   so a multi-period notability computation run is itself resumable.

4. Prove it end-to-end on REAL data: compute notability signals for a
   real sequence of the account's real rollup periods (reuse whatever
   day/week/month/quarter rollups already exist in Fulcra from
   Milestones 4-5, or generate a few more real ones if the existing
   spread of periods isn't enough to establish a meaningful baseline --
   you need several periods of the SAME period_type to compute a
   baseline against). Read the generated NotabilitySignal records back
   and confirm: at least one period that should plausibly be flagged as
   notable (e.g. the account's highest-activity real period) actually
   is, and its explanation text makes sense relative to the real
   underlying stats -- not just that some records got written.

5. This milestone does NOT need the final narrative-generation pass --
   that's Milestone 7, which will read both the rollup layer AND this
   milestone's NotabilitySignal records.

Keep it minimal and correct rather than elaborate -- reuse
process_with_checkpoint, read_rollups, and (if used) the existing Gemini
provider; don't rebuild any of these from scratch. When you're done,
give a short summary of the files you created/changed, a real example
of a generated NotabilitySignal (the actual score/flags/explanation) for
a period that stands out, and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. The current full suite runs real, sometimes slow, live API
  tests -- budget several minutes for a full run.
- app/tests/conftest.py already loads .env for the pytest suite (added
  in Milestone 4) -- if you write any one-off verification script
  outside pytest and it needs GEMINI_API_KEY, remember to load .env
  yourself.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section before guessing a call signature.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the first five feature files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
