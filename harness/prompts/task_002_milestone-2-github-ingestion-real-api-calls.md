Task: Milestone 2: GitHub ingestion — raw activity, real API calls

Context
Engineering Journey: a Hermes skill that ingests a developer's GitHub
activity history (commits, PRs, PR reviews, PR/issue discussion) going
back approximately 3 years, and produces a single, well-formatted,
engaging markdown document telling the story of their engineering
journey over that period.

This is the second task, following Milestone 1 (the resumable backfill
checkpoint, already built and committed -- see checkpoint.py and
app/CONTEXT.md's Fulcra SDK usage notes). Full architecture context is
in architecture.md and app/CONTEXT.md if you need more than the summary
below.

Your task right now
Build a GitHub API client and wire it into Milestone 1's checkpoint
mechanism, then ingest a small, real, bounded window of real activity
into a new GitHubActivityRaw Fulcra record type.

Specifically:

1. GitHub client (github_client.py or similar):
   - Accept a GitHub identity (username + personal access token) as
     RUNTIME CONFIGURATION -- e.g. environment variables
     (GITHUB_TOKEN, GITHUB_USERNAME) or an explicit constructor
     argument. Do NOT shell out to the gh CLI and do NOT assume the
     host machine's gh session -- this must work with an arbitrary
     provided token for an arbitrary account, per the Interview's
     explicit auth requirement. Use the requests library (or Python's
     stdlib http.client) directly against GitHub's REST and/or GraphQL
     APIs.
   - Implement at minimum: a GraphQL contributionsCollection query (for
     per-repo commit/PR/review/issue counts over a date range) and a
     REST Search API call (for actual commit messages / PR titles and
     bodies for a bounded window) -- both of these were verified
     working live during the Architecture phase; see architecture.md
     for the exact query shapes that were tested.
   - To actually test this yourself in this environment: a real GitHub
     token is available via `gh auth token` (this environment's `gh` is
     logged in as a real account) -- use that value to exercise your
     client against the REAL GitHub API, but write the client itself so
     it takes the token as configuration, not by calling `gh` or
     assuming this specific setup. In other words: it's fine to use the
     locally available token as a convenient way to get a real token
     for testing; it is NOT fine for the client's CODE to fetch that
     token via `gh` itself.

2. GitHubActivityRaw Fulcra record type: durable record of raw ingested
   activity (per architecture.md: commit metadata + message, PR
   metadata + body, review, comment). Follow the same MomentAnnotation-
   based, JSON-note pattern as GitHubBackfillProgress from Milestone 1 --
   see checkpoint.py for the established pattern and app/CONTEXT.md's
   "Fulcra SDK usage notes" section for verified exact SDK call shapes
   (record_data_type needs api_version as a required arg, etc.).

3. Wire ingestion INTO Milestone 1's checkpoint mechanism (per plan.md:
   "Wire this INTO the Milestone 1 checkpoint mechanism (checkpointing
   by repo+date-range), rather than building ingestion standalone and
   integrating later") -- reuse process_with_checkpoint from
   checkpoint.py, don't build a separate, parallel resumability
   mechanism for this milestone.

4. Prove it end-to-end on a SMALL, REAL, BOUNDED window: one real month
   of one real account's activity (not the full 3-year backfill yet --
   that's Milestone 3). Ingest it into real GitHubActivityRaw records in
   Fulcra, then read them back and confirm the content is real and
   correct (not just "some records exist").

Keep it minimal and correct rather than elaborate. Don't build the full
3-year backfill loop, rollups, or notability signal yet -- those are
later milestones. When you're done, give a short summary of the files
you created/changed and the test results.

Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes -- not just tests for what you just
  changed. Note: as of the fix committed after Milestone 1, the
  git_commit test gate runs `python -m pytest`, so plain top-level
  imports of sibling app/ modules (like `from fulcra_client import
  get_fulcra_client`) work correctly through the gate -- you do not need
  to work around this.
- Use the fulcra-api Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches. Check app/CONTEXT.md's "Fulcra
  SDK usage notes" section before guessing a call signature.
- Do not commit any real GitHub token, username, or other credential
  into a file tracked by git -- read them from environment variables at
  runtime only. (This project's .gitignore already excludes .env; if you
  need a new local-only config file for testing, gitignore it too.)
- Update app/features/INDEX.md and add a new app/features/*.md file for
  this feature (following the pattern of
  01_resumable_backfill_progress.md).
- Commit your work with git_commit once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
- Clean up any real Fulcra test records you create during manual
  exploration/testing (not ones covered by a test's own
  try/finally cleanup) before finishing -- this has been a real, repeated
  issue on this project (see app/CONTEXT.md's Decisions Log).
