Task: Milestone 11: Fix stale checkpoints masking improved discovery

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3-4 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-10 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, notability.py,
narrative.py, engineering_journey.py, fulcra_types.py, and
app/CONTEXT.md's Decisions Log and "Fulcra SDK usage notes" section.

**Read app/CONTEXT.md's Decisions Log entry titled "Real gap found via
a SECOND fresh-account live test" FIRST, in full, before writing any
code.** It documents the exact confirmed diagnosis: a second real
fresh-account test found that Milestone 10's private-repo discovery fix
(already correct and merged) is UNREACHABLE via the documented
`backfill` CLI path in practice, because
`github_activity.backfill_full_github_activity`'s checkpoint `task_id`
(`f"backfill_3yr:{username}:{start_str}_{end_str}"`) depends only on
username + date range, never on which repos were actually discovered.
`checkpoint.process_with_checkpoint` trusts an existing
`existing.status == "completed"` checkpoint unconditionally and returns
immediately with ZERO new work -- so a checkpoint left over from an
earlier, narrower backfill (fewer repos discovered, e.g. before
Milestone 10's fix landed) silently causes every later backfill attempt
for that same username+range to complete instantly while covering only
the old, smaller repo set -- even though the discovery code has since
improved and would find far more real activity if actually run.

Your task right now

**This must be a DELTA-AWARE fix, not a blind "ignore completed and
reprocess everything" fix.** `github_activity.write_raw_activities` has
NO deduplication by `activity_id` -- it's a pure append. Blindly
reprocessing the full item list for a "stale" checkpoint would create
real duplicate `GitHubActivityRaw` records (and downstream double-
counted rollups/notability signals) for repos already correctly
covered by the old checkpoint. Do not take that shortcut.

1. Change `backfill_full_github_activity` (github_activity.py) to store
   the ACTUAL discovered repo list (not just `len(repo_names)`) in
   checkpoint metadata -- e.g. `metadata={"repo_names": sorted(repo_names), ...}`
   alongside the existing `total_repos`/`total_periods` fields (keep
   those too, for backward-compat readability of already-existing
   checkpoints that don't have `repo_names`).

2. Before trusting an existing `"completed"` checkpoint,
   `backfill_full_github_activity` should:
   - Read the existing checkpoint (it already reads it implicitly via
     `process_with_checkpoint` -- you likely need to read it explicitly
     ONE level up, in `backfill_full_github_activity` itself, before
     calling `process_with_checkpoint`, so you can compare repo sets
     and decide whether to run a full call, a delta call, or skip).
   - Compare the freshly discovered `repo_names` against the existing
     checkpoint's stored `repo_names` metadata (if present -- older
     checkpoints without this field should be treated conservatively,
     e.g. as "unknown coverage," not silently trusted as fully covering
     the fresh set. Use your judgement on the safest interpretation but
     document it).
   - If there are NEW repos not covered by the old checkpoint's stored
     list: run a distinctly-tracked delta backfill covering ONLY those
     new repos (build a separate work-item list scoped to just the new
     repos x the same period chunks, with its own `task_id` -- e.g.
     incorporating a stable hash of the sorted new-repo subset -- so
     it's independently resumable/interruptible like any other backfill
     unit, and does NOT touch/reprocess the repos the original
     checkpoint already covered).
   - If there are no new repos, behave as today (trust the existing
     completed checkpoint, no wasted work).
   - Print/log something visible (not just a silent internal decision)
     when a delta backfill is triggered, e.g. "Found N repos not
     covered by a prior backfill; ingesting those now" -- so a user
     running this via the CLI can tell the difference between "nothing
     to do" and "found new work and did it."

3. Update `engineering_journey.py`'s `run_backfill` orchestration if
   needed so this delta behavior is visible in its own output/return
   value too (it currently just reports `raw_res.get("completed_items_count")`
   from the single `backfill_full_github_activity` call -- decide
   whether that return shape needs to reflect "some items came from an
   original completed run, some from a delta run" or whether it's fine
   as-is; make a deliberate choice, don't just leave it inconsistent
   without checking).

4. Prove this end-to-end on REAL data, reproducing the actual reported
   scenario, not a synthetic stand-in:
   - Run a real, narrow-scope `backfill_full_github_activity` call
     against this environment's real GitHub account for a SMALL,
     deliberately restricted `repo_names` list (e.g. just 1-2 real
     repos) and a short date window, let it complete normally (a real,
     legitimately "completed" checkpoint).
   - Run it again with `repo_names=None` (full discovery) covering a
     window that includes at least one repo NOT in the original narrow
     list (a real private repo this account has, if one exists, mirrors
     the actual reported scenario most closely -- otherwise any repo
     not in the original narrow list is fine).
   - Confirm: the second call detects the new repo(s), runs a real
     delta backfill for just those, and that real `GitHubActivityRaw`
     records for the new repo(s) actually get ingested into Fulcra.
   - Confirm: the ORIGINAL repo's raw activity record count in Fulcra
     does NOT change/duplicate after the second call (the critical
     "did we avoid the naive reprocess-everything bug" check).
   - Clean up all real Fulcra checkpoints/records created during this
     verification that aren't covered by a test's own try/finally
     cleanup.

5. Automated tests: add a real live integration test covering the exact
   scenario in point 4 (narrow checkpoint marked completed, then a
   second call with an expanded real repo set, asserting the new repo's
   activity is ingested and the original repo's activity count is
   unchanged) -- this is the test that would have caught this bug
   before it shipped; a unit test of `enumerate_repositories()` alone
   is not sufficient (Milestone 10 already had one of those, and it
   didn't catch this). Skip gracefully if no GitHub token is available,
   matching the existing pattern in this project's tests.

Keep it minimal and correct rather than elaborate, but do not
under-scope this into something that skips the delta-awareness
requirement -- that's the actual point of this fix. When you're done,
give a short summary of the files you changed, the real before/after
proof (narrow checkpoint completed, new repo discovered and delta-
ingested, original repo's count unchanged), and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. Budget several minutes for a full run (it includes real,
  live API tests from prior milestones).
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the existing ten feature
  files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
