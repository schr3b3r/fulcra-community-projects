Task: Milestone 7: Narrative generation — the final markdown output

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-6 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, notability.py, and
app/CONTEXT.md's Decisions Log and "Fulcra SDK usage notes" section.
rollup.py has the full ActivityRollup layer (day/week/month/quarter/
year), each with structured stats and a provenance chain
(source_record_ids). notability.py has NotabilitySignal records per
rollup period with a 0-1 score, categorical flags (high_volume,
new_repo, focus_switch, low_volume_gap, streak), an explanation string,
and a source_rollup_id. Read both files before writing new code. There
is real ActivityRollup and NotabilitySignal data already in Fulcra you
can read directly (top it up with a few more real periods first if the
existing spread is too thin to tell a real story).

Your task right now
Build the final pass: read the full layered rollup structure plus its
NotabilitySignal records, and generate ONE paced markdown document that
tells the story of the account's engineering journey. This is the
actual deliverable from the user's perspective, per Architecture/Intake:
notable periods should get real narrative space (a paragraph or more),
quiet/routine periods should get a clause or a single sentence folded
into surrounding text -- not padded out to false significance, and not
silently dropped either (per Interview decision #3, gaps are real,
narratively significant data).

Specifically:

1. New module (e.g. narrative.py). Design a function, e.g.
   `generate_journey_narrative(username, start_date, end_date, client=...)`,
   that:
   - Reads the relevant ActivityRollup and NotabilitySignal records for
     the account/date range (reuse `read_rollups` / `read_notability_signals`
     as-is -- don't re-implement Fulcra querying here).
   - Picks a sensible top-level structure to walk chronologically (e.g.
     walk quarter or year rollups as the backbone/section breaks, and
     drop down into week/month detail only for periods flagged notable
     by NotabilitySignal -- your call, but document the reasoning in
     app/CONTEXT.md).
   - For each section, decides how much narrative space it deserves
     based on the NotabilitySignal(s) covering it (score and flags),
     not a fixed template applied uniformly to every period.
   - Calls harness.providers.gemini.call_model (reused as-is, no new
     LLM integration) to actually write the prose for notable sections,
     grounded in the real rollup summaries/stats and notability
     explanations you pass it as context -- not inventing narrative
     content the LLM wasn't given grounding for. Quiet periods can
     either skip the LLM call entirely (deterministic templated clause)
     or share a single batched LLM call across several quiet periods --
     your call, but avoid one LLM call per single quiet day/week, which
     would be slow and wasteful.
   - Assembles everything into one final markdown string/file with real
     document structure (title, maybe a short intro, chronological
     sections with headers, real prose).
   - Should NOT need its own new Fulcra record type -- this is a
     read + synthesize + write-a-file pass, not a new durable record
     layer. (It's fine if you want to durably record something like
     "this journey doc was generated at time T covering range X" for
     provenance/idempotency, but that's optional, not the point of this
     milestone.)

2. Provenance: the generated markdown (or an accompanying manifest) should
   make it possible to trace a claim in the narrative back to the
   rollup/notability records that grounded it -- doesn't need to be
   visible inline in the prose itself, but should exist somewhere (e.g.
   an appendix section, or a sidecar JSON/manifest file) consistent with
   this project's provenance requirement throughout.

3. Wire it so it's runnable as a real, documented entrypoint (a script or
   a function callable from a short `if __name__ == "__main__"`, your
   call) that a human could invoke to actually produce the output file
   on disk -- Milestone 8 will wrap this in a proper skill entrypoint,
   but this milestone should already be genuinely runnable end-to-end,
   not just unit-tested in isolation.

4. Prove it end-to-end on REAL data: actually generate the markdown
   document for this real account's real ingested history (whatever
   real range Milestones 1-6 have already populated -- top it up first
   if needed to get a real multi-period, multi-notability-flag spread).
   Read the ACTUAL generated markdown output yourself and confirm:
   - It reads as a coherent, paced narrative (not just concatenated
     stats dumps).
   - At least one genuinely notable real period (e.g. the account's
     highest-activity real period, or a real new-repo/focus-switch
     period) gets real, specific narrative space and the prose actually
     reflects the real underlying activity (repo names, real work
     described) -- not generic boilerplate.
   - At least one quiet/routine real period is present but compressed to
     a clause/sentence, not silently omitted.
   - The document is structurally sound markdown (renders sensibly,
     correct heading nesting).
   Include the real generated markdown's path and a representative
   excerpt (not the whole thing) in your final summary.

5. This milestone is the actual user-facing deliverable of the whole
   project so far -- validate it like a human reader would, not just
   with an assertion that a non-empty file exists.

Keep it minimal and correct rather than elaborate -- reuse read_rollups,
read_notability_signals, and harness.providers.gemini.call_model; don't
rebuild any of these from scratch. When you're done, give a short
summary of the files you created/changed, the real generated markdown's
path plus a representative excerpt showing both a notable section and a
compressed quiet section, and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. The current full suite runs real, sometimes slow, live API
  tests -- budget several minutes for a full run.
- app/tests/conftest.py already loads .env for the pytest suite -- if
  you write any one-off verification script outside pytest and it needs
  GEMINI_API_KEY, remember to load .env yourself.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section before guessing a call signature.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git. The generated markdown output file itself
  is real content, not a secret -- fine to write to disk, use judgment
  on whether it belongs in git or should be gitignored output.
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of the first six feature files).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log).
