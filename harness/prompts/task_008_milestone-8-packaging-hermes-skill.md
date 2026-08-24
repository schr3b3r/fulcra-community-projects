Task: Milestone 8: Packaging as an installable Hermes skill

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history going back approximately 3 years, and produces a
single, well-formatted, engaging markdown document telling the story of
their engineering journey over that period.

Milestones 1-7 are done and committed -- see checkpoint.py,
github_client.py, github_activity.py, rollup.py, notability.py,
narrative.py, and app/CONTEXT.md's Decisions Log and "Fulcra SDK usage
notes" section. Every layer (raw ingestion -> day/week/month/quarter/year
rollups -> notability signals -> final narrative) is built, tested
against real data, and committed. Read app/CONTEXT.md fully before
starting -- it has the exact call shapes and real numbers you need
(e.g. real backfill timing estimates from Milestone 3).

This is the LAST milestone in plan.md. The person running this is about
to hand this project to a completely fresh Hermes/Claude Code agent
session on a DIFFERENT machine, to run against a DIFFERENT real GitHub
account they've used for ~20 years (importing ~3-4 years of it, not the
full 20). That fresh agent will have NO memory of this build process --
only whatever you package here. Write everything as if a careful stranger
with no prior context has to follow it cold.

Your task right now

1. Unify the two real entrypoints behind one clear CLI, e.g. a new
   `app/engineering_journey.py` (or similar) with two subcommands:
   - `backfill`: runs the full real pipeline for a given GitHub
     username/token and date range -- `backfill_full_github_activity`
     (Milestone 3) -> `generate_day_week_rollups` (Milestone 4) +
     `generate_month_rollups`/`generate_layer_rollups` for
     month/quarter/year (Milestone 5) -> `generate_notability_signals`
     (Milestone 6) for each period_type that has enough history for a
     baseline. This is the slow, occasionally-run step (per Interview
     decision #5, "however long it takes, run it once" is fine for v1).
     Make the date range configurable (default ~3 years back from today,
     but must accept a `--years` or `--start-date`/`--end-date` override
     -- the person running this next wants to try 3-4 years, and the
     Interview's own decision #3 says cover whatever history actually
     exists, don't hardcode 3).
   - `generate`: runs `generate_journey_narrative` (Milestone 7) against
     whatever's already ingested -- the fast, freely-re-runnable step,
     kept SEPARATE from `backfill` per Architecture's Context-Compute
     Separation point (context lives durably in Fulcra; regenerating the
     narrative from it should not require re-hitting GitHub at all).
   Both subcommands must accept GitHub username/token and Fulcra
   credentials path as CLI args or env vars (GITHUB_TOKEN,
   GITHUB_USERNAME, FULCRA_CREDENTIALS_PATH) -- no hardcoded account,
   no assumption about `gh` CLI session identity (this was already a
   hard requirement from Architecture; just make sure the final
   entrypoint actually respects it end to end, don't silently reintroduce
   an assumption).

2. Write `SKILL.md` (Hermes skill format -- look at the frontmatter/
   structure convention used by other installed skills under
   ~/.hermes/skills/*/SKILL.md on this machine, e.g. the
   fulcra-agent-harness-starter or flow-state-app skills, for the exact
   shape expected: YAML frontmatter with name/description/author/version/
   metadata.tags, then step-by-step agent-facing instructions) at the
   root of THIS repo (sibling to plan.md/architecture.md/README.md).
   It should tell a fresh agent, in order:
   - How to confirm/obtain GitHub auth (a PAT with repo + read:org scopes
     is enough; do NOT depend on `gh` CLI session identity) and Fulcra
     auth (point at the fulcra-connect skill, same pattern flow-state-app
     uses).
   - How to set up the Python environment (venv + install deps -- reuse
     whatever this repo's app already needs; check if there's an
     app-level pyproject/requirements or if app/ currently only has
     harness/'s pyproject.toml and needs its own).
   - How to run `backfill` (with realistic expectations set: point back
     at Milestone 3's real measured ~25-30 min estimate for a 3-year/
     8-repo account, and note it scales with account history size and
     repo count, so a busier or longer-history account should expect
     more).
   - How to run `generate` afterward (fast, re-runnable any time new
     data exists).
   - Where the output file ends up and what it's for (a single, shareable
     markdown document).

3. Write (or substantially rewrite) the top-level `README.md` so a
   stranger -- not just a fresh Hermes agent, an actual human reading it
   on GitHub -- could clone this repo and get the same result. It should
   cover: what this is, prerequisites, installation, both entrypoints
   with real example commands, and where output lands. It's fine for
   `SKILL.md` and `README.md` to share content/structure -- SKILL.md is
   agent-instruction-shaped, README.md is human-shaped -- but don't just
   make one a copy-paste of the other; each should read naturally for
   its actual audience.

4. Prove the packaging works end-to-end for real, from a clean starting
   point, not just "the underlying functions already work" (they do --
   that's not what's being tested here):
   - Actually run `generate` against the already-ingested real data
     (schr3b3r, whatever's already in Fulcra from Milestones 4-7) via
     the NEW unified CLI entrypoint you just built, confirm it produces
     the same kind of real, correct markdown output Milestone 7 already
     proved out, but now through the packaged entrypoint rather than
     calling `narrative.py` directly.
   - You do NOT need to re-run a real multi-year `backfill` against
     GitHub again from scratch for this milestone (that would burn a lot
     of real time/API budget for something Milestones 2-3 already proved
     works) -- but DO verify the `backfill` subcommand's argument
     parsing, wiring, and orchestration logic with a fast automated test
     (e.g. mocking/stubbing the actual network calls, or running it
     against a tiny real bounded window like a few days) so a bug in the
     NEW orchestration code (not the underlying functions, which are
     already tested) would be caught.
   - Read the actual SKILL.md and README.md yourself afterward as if you
     were the fresh stranger/agent described above, and fix anything
     that assumes context that wouldn't actually be available (e.g. "the
     harness already did X" -- a fresh session on a new VM has no
     harness state, no prior conversation, nothing but this repo's files
     and whatever it's told to authenticate).

5. Update `app/CONTEXT.md` (Current State -> all 8 milestones done;
   Decisions Log entry for this milestone) and `app/features/INDEX.md` +
   a new `app/features/08_packaging_hermes_skill.md` feature file,
   following the established pattern.

Keep it minimal and correct rather than elaborate -- this is glue/
packaging around already-correct, already-tested logic, not new product
logic. Don't rebuild ingestion/rollup/notability/narrative logic here.
When you're done, give a short summary of the files you created/changed,
the exact commands a fresh stranger would run for both `backfill` and
`generate`, and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's new orchestration code
  (the new CLI/entrypoint module), and the FULL test suite passes --
  not just tests for what you just changed. Budget several minutes for
  a full run (it includes real, live API tests from prior milestones).
- app/tests/conftest.py already loads .env for the pytest suite.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git.
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own try/finally
  cleanup) before finishing -- this has been a real, repeated issue on
  this project (see app/CONTEXT.md's Decisions Log -- 9 stray
  NotabilitySignal records were just found and cleaned up after
  Milestone 7 for exactly this reason).
