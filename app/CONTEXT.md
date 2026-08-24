# Engineering Journey: Project Context & Architecture

This document is the durable memory for this app, maintained by the agent
itself across tasks. Read this before starting any new task. Update it
whenever you make an architectural decision, pivot, or complete a
significant milestone — so the next task (run by you or a future agent) has
accurate context without needing to re-derive it from the diff history.

This project is independent: it does not reference or depend on any other
app's code, files, or context. Record all decisions relevant to this app
here.

## The Product
Build a Hermes skill that ingests a developer's GitHub activity history
(commits, PRs, PR reviews, PR/issue discussion) going back approximately
3 years, and produces a single, well-formatted, engaging markdown
document telling the story of their engineering journey over that
period — something they could read for themselves, or share with others,
that captures how their work/focus/scope evolved over time.

A Hermes skill that backfills ~3 years of a GitHub account's activity
(commits, PRs, reviews, discussion) into Fulcra as durable records,
builds a layered rollup structure on top (day/week for the recent 90
days, month beyond that, quarter/year on top of both), computes a
notability signal per period, and generates one paced markdown narrative
from the whole structure. No web app, no hosting — a skill that produces
a markdown file.

(See `architecture.md` at the repo root for the full architecture writeup this summary was excerpted from.)

## Current State
All Milestones 1–11 are DONE:
- Milestone 1: Resumable backfill checkpoint (`checkpoint.py`)
- Milestone 2: Real GitHub raw activity ingestion (`github_client.py`, `github_activity.py`)
- Milestone 3: Full 3-year backfill chunking + real at-scale resumability (`github_activity.py`)
- Milestone 4: Day/week rollup layer with real LLM summaries (`rollup.py`)
- Milestone 5: Month/quarter/year rollup layer with hierarchical provenance chains (`rollup.py`)
- Milestone 6: Personal baseline notability signal scoring (`notability.py`)
- Milestone 7: Narrative synthesis & Markdown production (`narrative.py`)
- Milestone 8: Packaging as an installable Hermes skill (`engineering_journey.py`, `SKILL.md`, `README.md`, `requirements.txt`)
- Milestone 9: Migrated all record kinds to real, visible custom Fulcra data types (`fulcra_types.py`)
- Milestone 10: Private repository discovery fix in `GitHubClient` (`github_client.py`)
- Milestone 11: Delta-aware backfill fixing stale checkpoints masking improved discovery (`github_activity.py`)

The project is fully packaged, tested, and ready for execution by fresh agents or human users.

## Fulcra SDK usage notes (verified against the real API, not assumed)
These are exact, tested call shapes for the `fulcra-api` SDK calls this
project needs, captured because getting them wrong burns real iteration
budget rediscovering them via trial and error (this has already happened
twice on this project). Treat this as more authoritative than intuiting
the "obvious" call signature from a method name.

- **Auth**: use `app/fulcra_client.py`'s `get_fulcra_client()` — do not
  hand-roll `FulcraCredentials`/`FulcraAPI` construction. (In case that
  file is ever missing: the correct sequence is
  `FulcraCredentials.from_json(path.read_text())` then
  `FulcraAPI(credentials=creds)`, NOT `FulcraCredentials()` with no
  arguments and NOT a `fulcra_credentials=` keyword — both look
  plausible but are wrong.)
- **Writing a record**: `client.record_data_type(data_type: str, records: list[dict], api_version: str)`
  — `api_version` is a REQUIRED argument (there is no default), pass
  `"v1alpha1"`. Confirmed working example:
  ```python
  client.record_data_type(
      "MomentAnnotation",
      [{"recorded_at": now.isoformat(), "note": json.dumps({...})}],
      api_version="v1alpha1",
  )
  ```
- **Reading records**: `client.moment_annotations(start_time, end_time, source=None, fulcra_userid=None)`
  — `start_time`/`end_time` accept ISO 8601 strings or `datetime` objects.
  Returns a plain list of dicts; each has a `note` field (a plain string
  — if you stored JSON there, you must `json.loads()` it yourself, the
  SDK does not parse it for you) and a `metadata` field (present only for
  records created via `create_annotation`'s custom-annotation-type path,
  `None`/absent for records written via plain `record_data_type`).
- **Deleting/tombstoning a record**: do NOT rely on `delete_annotation`
  for records written via `record_data_type` (confirmed: it 404s for
  those, since it expects a real "annotation" object created via
  `create_annotation`, not this project's convention of a `MomentAnnotation`
  record with a JSON `note`). Instead write a `DeletedRecord` tombstone:
  ```python
  client.record_data_type(
      "DeletedRecord",
      [{"record_id": "<the-record's-own-id>", "data_type": "MomentAnnotation"}],
      api_version="v1alpha1",
  )
  ```
  Note the field is `record_id`, NOT `id` — confirmed via
  `client.v1_catalog_schema("DeletedRecord", "v1alpha1")`. Tombstoning
  is eventually consistent; allow a few seconds before re-querying to
  confirm a record is gone.
- **Discovering a schema when unsure**: `client.v1_catalog_schema(data_type, api_version)`
  returns the real JSON schema for that data type/version — check this
  BEFORE guessing field names for a `record_data_type` call, rather than
  guessing and iterating against live 400/404 errors.
- **Custom annotation data types** (needed to fix the "everything is a
  generic MomentAnnotation" gap flagged post-Milestone-8 — see Decisions
  Log): a REAL custom data type is created via the CLI/SDK, gets its own
  UUID, but records for it are NOT written directly to that UUID as a
  data type name (`record_data_type("MomentAnnotation/<uuid>", ...)`
  returns a 404 -- confirmed live). The real mechanism, confirmed
  end-to-end against a real throwaway probe type:
  1. **Create** the type once (idempotent -- check the catalog first,
     don't recreate on every run):
     ```python
     # No direct SDK method found for creation in fulcra_api.core;
     # the CLI's `fulcra-api data-type create` is a thin wrapper over
     # an /data/v1/... POST -- either shell out to the CLI once during
     # setup, or inspect fulcra_api.cli.data_types.py's create command
     # for the exact endpoint/payload if a pure-SDK path is wanted.
     # fulcra-api data-type create <BaseType> <Name> -d "<description>"
     ```
     Response includes a real assigned UUID, e.g.
     `{"id": "ee95f699-...", "name": "ActivityRollup", ...,
     "fulcra_source_id": "com.fulcradynamics.annotation.ee95f699-..."}`.
     **Store that returned UUID durably** (e.g. in a small local config/
     `.env` value per type, resolved once per environment) -- do not
     recreate the type on every run; check `client.resolve_data_type
     ("MomentAnnotation/<uuid>")` or `client.v1_catalog(name=...)`
     first and reuse the existing UUID if the type already exists.
  2. **Write** a record "as" that custom type by writing to the BASE
     type (e.g. `"MomentAnnotation"`, unchanged) but adding a `sources`
     field containing `f"com.fulcradynamics.annotation.{custom_uuid}"`
     (lowercase UUID) to each record dict:
     ```python
     client.record_data_type(
         "MomentAnnotation",
         [{
             "recorded_at": now.isoformat(),
             "note": json.dumps({...}),
             "sources": [f"com.fulcradynamics.annotation.{custom_uuid}"],
         }],
         api_version="v1alpha1",
     )
     ```
     (Confirmed by reading `fulcra_api.cli.record`'s actual
     implementation, then reproducing it directly via the SDK -- the CLI
     resolves `BaseType/UUID` syntax internally but still POSTs to the
     base type, attaching the custom type's identity via `sources`, not
     via the data-type path itself.)
  3. **Read** records back filtered to just that custom type via
     `client.moment_annotations(start, end, source=f"com.fulcradynamics.annotation.{custom_uuid}")`
     -- confirmed this returns ONLY records tagged with that source, not
     every `MomentAnnotation` mixed together, and the returned dict
     includes a `metadata` field with the full custom-type catalog entry
     (name, description, created_at, etc.) alongside the record's own
     fields.
  This means fixing the "no custom data types" gap is: create one real
  custom type per record kind (`GitHubActivityRaw`, `ActivityRollup`,
  `NotabilitySignal`, `GitHubBackfillProgress`) once, store their UUIDs,
  and change every `write_*`/`read_*` function's `record_data_type`/
  `moment_annotations` calls to pass the `sources`/`source` value above
  instead of relying purely on the embedded `"record_type"` JSON string
  key for identification (the JSON `note` payload and its `record_type`
  key can stay as-is for backward-compatible reading of already-written
  records, but new writes should carry the real source tag too).
  **(Milestone 9, done)** This is now implemented in `fulcra_types.py` +
  the four modules' write/read/clear functions -- see the Decisions Log
  entry for real verification details (all four types confirmed live in
  this account's catalog, idempotent creation confirmed, backward-compat
  reads confirmed). `get_or_create_custom_data_type` uses
  `client.create_annotation(annotation_type="moment", name=..., ...)`
  for creation (a genuine pure-SDK path was found -- no CLI subprocess
  needed after all).
- **Known minor gap**: `clear_checkpoint`/`clear_raw_activities` query-
  then-tombstone in one pass immediately after the caller's own writes,
  with no poll/retry (unlike `read_checkpoint`/`list_checkpoints`/
  `read_raw_activities`, which do support polling). In practice this
  occasionally leaves a just-written record un-tombstoned if the
  clear-call runs before Fulcra's eventual consistency catches up —
  observed as a handful of stray `test_task_*`/`test_ingest_*`
  checkpoints surviving a test's own `finally: clear_checkpoint(...)`
  across two Milestone 2 test runs. Not yet fixed (worth doing the same
  polling treatment as the read functions if it keeps happening) — for
  now, periodically check for and clean up stray checkpoints/activities
  by calling `list_checkpoints()`/`read_raw_activities()` with no
  filters and inspecting what comes back, same as was done here.

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(Milestone 11 complete)** Made `backfill_full_github_activity`
  delta-aware, fixing the gap below. It now stores the actual discovered
  `repo_names` list (not just a count) in checkpoint metadata. Before
  trusting an existing `"completed"` checkpoint, it computes a real set
  difference between the freshly discovered repos and the checkpoint's
  stored repo list (legacy checkpoints missing `repo_names` are treated
  conservatively as unknown coverage, i.e. an empty stored set, so every
  freshly discovered repo gets verified rather than silently trusted as
  already covered). If new repos are found, a distinctly-tracked delta
  backfill runs (`<task_id>:delta:<hash-of-new-repos>`) covering ONLY
  those new repos x the same period chunks -- repos already covered by
  the parent checkpoint are never reprocessed, so no duplicate
  `GitHubActivityRaw` records get created (this project's raw-activity
  writes have no dedup, so this delta-only design was a hard
  requirement, not a nice-to-have). On successful delta completion, the
  parent checkpoint's `repo_names`/`total_repos` metadata is updated to
  the union of old + new, so future runs see accurate coverage.
  `engineering_journey.py`'s CLI output now distinguishes a delta result
  from a normal one (new repos ingested vs. nothing to do).
  **Real end-to-end proof:** ran a real narrow backfill for one real
  repo (`fulcradynamics/agent-skills`) over a short window, let it
  complete; ran a second real call with an expanded repo set adding
  `schr3b3r/shimmer` (a real private repo) for the SAME task_id;
  confirmed the second call detected the new repo, ran a real delta
  backfill, ingested real `GitHubActivityRaw` records for `shimmer`,
  AND confirmed `agent-skills`' raw activity record count was
  byte-for-byte unchanged after the second call (the critical
  no-duplication check). Added `test_backfill_delta_awareness_real`
  covering this exact scenario live -- not just a unit test of
  `enumerate_repositories()` in isolation, which had already passed and
  hadn't caught this class of bug. Full suite: 10/10 in
  `test_github_activity.py` (including the new delta test), full
  project suite green.
  A handful of stray checkpoints (`proof_stale_chk_real_*`,
  `test_delta_*`) left over from this task's own manual verification
  exploration (not covered by the new test's own try/finally) were
  found and cleaned up before finishing -- yet another instance of the
  recurring "clean up ad-hoc Fulcra writes" issue tracked since
  Milestone 1. The task run itself hit the harness's `max_iterations=45`
  cap partway through its own final full-suite confirmation run (all
  individual test files it did run passed) and before updating
  `app/features/INDEX.md`/this file's Current State -- completed
  manually: cleaned up the stray checkpoints above, added the doc
  updates, reran the full suite clean, and committed.

- **(Real gap found via a SECOND fresh-account live test -- now fixed,
  see Milestone 11 entry above)** A second real fresh-account
  test (GitHub user `gklei`, ~90+ private repos, large private
  `fulcradynamics/*` org footprint) found that Milestone 10's private-
  repo discovery fix, while independently confirmed correct in
  isolation (`enumerate_repositories()` genuinely returns 116 repos
  including private ones for this account), is UNREACHABLE via the
  documented `backfill` CLI path in practice. Root cause: the checkpoint
  layer's `task_id` (`f"backfill_3yr:{username}:{start_str}_{end_str}"`
  in `github_activity.backfill_full_github_activity`) depends only on
  username + date range, never on which repos were actually discovered.
  `checkpoint.process_with_checkpoint` trusts `existing.status ==
  "completed"` unconditionally and returns immediately with zero new
  work -- so an EARLIER backfill attempt for this exact username+range
  that discovered only 6 repos (likely run before/without Milestone
  10's fix) left a `"completed"` checkpoint that every SUBSEQUENT
  backfill attempt -- including one using the already-fixed
  116-repo-discovering code -- silently trusts and skips, with no
  warning that the "completed" result only ever covered a fraction of
  the real repo set. The CLI's own success output ("Backfill completed
  successfully!") gives no indication anything was skipped.
  **Confirmed by the reporting agent (not just theorized):** GitHub PAT
  scopes (`read:org, repo`) were confirmed sufficient for private repo
  access; `GET /user/repos?...` confirmed 94+ private repos visible
  directly; this repo's own `enumerate_repositories()` confirmed to
  return 116 repos for the real 3-year window; and
  `checkpoint.list_checkpoints()`/`read_checkpoint()` confirmed the
  existing `backfill_3yr:gklei:...` checkpoint's stored metadata shows
  `total_repos: 6`, `status: "completed"`.
  **Why this is a design smell, not a one-off stale-cache accident:**
  `write_raw_activities` has NO deduplication by `activity_id` -- it's a
  pure append. This means the naive fix ("just ignore `completed` and
  reprocess everything") would create real duplicate
  `GitHubActivityRaw` records (and downstream double-counted rollups/
  notability signals) for the repos already covered by the old
  checkpoint, not just safely fill in the gap. A correct fix must be
  delta-aware: detect which repos are newly discoverable that the old
  checkpoint's repo set didn't cover, and process ONLY those as a
  distinct, separately-tracked unit of work -- never blindly
  reprocessing repos the old checkpoint already covered.
  **Planned fix direction (Milestone 11, not yet implemented):**
  (1) store the actual discovered `repo_names` list (not just a count)
  in checkpoint metadata, so a future run can compute a real set
  difference, not just notice a changed count; (2) before trusting an
  existing `"completed"` checkpoint in
  `backfill_full_github_activity`/`process_with_checkpoint`, compare a
  freshly discovered repo set against the checkpoint's stored repo
  list; if the fresh set has repos the old checkpoint didn't cover, run
  a distinctly-tracked delta backfill for exactly those new repos (own
  task_id, e.g. incorporating a hash of the new-repo subset) rather than
  reprocessing the full item list; (3) surface this to the user/CLI
  output (e.g. "found N new repos not covered by a prior backfill,
  ingesting those now") rather than silently completing with a subset;
  (4) add a real live integration test exercising this exact scenario
  end-to-end through `backfill_full_github_activity` (a real narrow
  backfill, marked completed, then a real second call with an expanded
  real repo set, asserting the new repo's real activity gets ingested
  and the original repo's activity count does NOT change/duplicate) --
  not just a unit test of `enumerate_repositories()` in isolation, since
  that already passed and didn't catch this.

- **(Milestone 10 complete)** Fixed private repository discovery gap in
  `GitHubClient.list_accessible_repositories()` and `enumerate_repositories()`.
  Added `list_accessible_repositories(pushed_after, pushed_before)` calling
  `GET /user/repos?affiliation=owner,collaborator,organization_member` with
  pagination and `pushed_at` window filtering. `enumerate_repositories()`
  now unions this discovery pass with GraphQL `contributionsCollection` queries,
  ensuring private repositories (e.g. `schr3b3r/shimmer`, `schr3b3r/thrum`)
  missed by `contributionsCollection` are discovered before raw activity ingestion.
  **Real proof performed:** verified `schr3b3r/shimmer` was absent from
  `enumerate_repositories('2023-01-01', '2026-12-31')` before the fix (8 repos
  returned) and present after (14 repos returned). Ran real ingestion for
  `schr3b3r/shimmer` over May 2026, confirmed real `GitHubActivityRaw` records
  for private commits were written to and read back from Fulcra, and cleaned
  up all test records. Added unit/live automated tests in `tests/test_github_client.py`.
- **(Real gap independently re-verified, scope corrected -- Milestone 10
  scoped for it)** The same fresh-account live test's
  `ISSUES_AND_LIMITATIONS.md` (see the Milestone 9-era entry below for
  full original text) also claimed GitHub's REST Search API "cannot
  index or return private repository content at all, regardless of
  token scopes" and that fixing raw-activity fetch would require
  replacing Search API calls with per-repo REST endpoints everywhere.
  **Independently re-verified this claim directly against 3 real
  private repos in this environment's own real GitHub account
  (`schr3b3r/shimmer`, `schr3b3r/thrum`, `schr3b3r/fulcra-skills-dash`)
  before accepting it, and it does NOT hold as stated:**
  - `search/commits` and `search/issues` (a real throwaway issue was
    created, found via search, then closed) DID successfully find real
    commits/issues in 2 of the 3 private repos (`shimmer`, `thrum`) with
    a normal `repo`-scoped PAT -- contradicting "cannot index private
    content at all, regardless of scope."
  - The one repo where `search/commits` found zero results
    (`fulcra-skills-dash`, which has 7 real commits) turned out to be
    unrelated to privacy: those commits were authored with an email
    (`schr3b3r@openclaw.local`) not linked to any GitHub account, so
    `author:` search can't match them by GitHub login regardless of
    repo visibility -- an author-linking edge case, not a Search API
    privacy limitation, and one that would equally affect a public repo.
  - The ACTUAL confirmed gap is narrower and upstream of fetching: this
    project's `GitHubClient.enumerate_repositories()` (the only
    repo-discovery mechanism `backfill_full_github_activity` uses)
    relies entirely on GraphQL `contributionsCollection`, which
    genuinely DID miss both real private repos with real contributions
    (`hasAnyRestrictedContributions` was `false`/`0` for a window
    containing real private commits by this account -- confirmed live).
    Once a private repo is actually in the `repo_names` list, the
    existing Search-API-based `fetch_commits`/`fetch_pull_requests`/
    `fetch_issues` already work for it (per the direct test above) --
    no rewrite of the fetch layer needed.
  - Real fix scope: add an explicit `GET /user/repos?affiliation=owner,
    collaborator,organization_member` listing pass to
    `enumerate_repositories()`, unioned with whatever
    `contributionsCollection` already finds, filtered to repos whose
    `pushed_at` falls within the requested window (a repo not pushed to
    at all in-window has no in-window activity; a repo pushed to could
    still have zero activity *by this specific user*, which the
    existing per-repo fetch functions already correctly filter for via
    `author:`/`committer-date:` search qualifiers -- so this is a cheap,
    correct prefilter, not a source of false negatives). This is a
    single-function fix plus one new GitHubClient method, not the
    sweeping "replace Search API everywhere" rewrite originally
    proposed -- confirmed unnecessary before committing to it.

- **(Milestone 9 complete)** Migrated all four record kinds
  (`GitHubBackfillProgress`, `GitHubActivityRaw`, `ActivityRollup`,
  `NotabilitySignal`) from generic `MomentAnnotation` JSON-note blobs to
  real, visible custom Fulcra data types, fixing the gap below. New
  `fulcra_types.py`: `get_or_create_custom_data_type(name)` idempotently
  creates (via `client.create_annotation`, confirmed a real pure-SDK
  path exists -- no CLI subprocess needed) or looks up (via
  `client.v1_catalog`) each type's real UUID; `get_custom_source_tag(name)`
  returns the `com.fulcradynamics.annotation.<uuid>` tag used to write
  records "as" that type and filter reads to just that type. Every
  `write_*` function now adds `sources: [<tag>]` to each record;
  `checkpoint._fetch_annotations_merged` (shared by all four modules'
  `read_*`/`clear_*` functions) merges new source-tagged records with
  legacy untagged ones by record ID, so already-written pre-migration
  data stays readable rather than being silently orphaned -- confirmed
  by a real test writing an old-format record directly, a new-format
  record via `write_checkpoint`, and reading both back correctly.
  **Real verification performed (not just unit tests):** created all
  four types for real in this environment's real Fulcra account and
  confirmed all four are genuinely visible via `fulcra-api catalog -c
  user_configured` (previously: zero custom types existed, only stock
  built-ins). Confirmed idempotent creation (second call for an
  already-existing type returns the same UUID, no duplicate created --
  checked the real catalog before and after). A stray `_ProbeTypeTest5`
  type created during the harness's own exploration was found and
  archived before finishing (yet another instance of the recurring
  "clean up ad-hoc Fulcra writes" issue -- see the process note below).
  Full suite: 53/53 pass (48 pre-existing + 5 new in
  `tests/test_fulcra_types.py`).
  The task run itself hit the harness's `max_iterations=50` cap after
  writing the real code/tests/verification but before updating
  `app/features/INDEX.md`, adding `app/features/09_*.md`, updating this
  file's Current State, or running `git_commit` -- completed manually:
  reran the full suite clean, added the doc updates, archived the stray
  probe type, and committed.
- **(Real gap found via live test feedback -- now fixed, see Milestone 9
  entry above)** The first real fresh-account test's shared
  `ISSUES_AND_LIMITATIONS.md` flagged that NO custom Fulcra data types
  exist anywhere in this codebase -- every persistence path
  (`github_activity.py`, `rollup.py`, `notability.py`, `checkpoint.py`)
  writes to the generic built-in `MomentAnnotation` type with the real
  semantic type hidden as a `"record_type"` string inside the JSON
  `note` blob, not a real registered Fulcra data type. This directly
  contradicts this project's own stated "why Fulcra, specifically"
  rationale (custom annotation types as a deliberate, visible primitive,
  per `intake/brief.md`). Confirmed independently by creating a real
  throwaway custom data type via `fulcra-api data-type create` and
  round-tripping a real record through it -- see the new "Custom
  annotation data types" entry in the SDK usage notes above for the
  full confirmed mechanism (create once -> write to the BASE type with
  a `sources: ["com.fulcradynamics.annotation.<uuid>"]` tag -> read back
  via `moment_annotations(..., source="com.fulcradynamics.annotation.<uuid>")`).
  This is a real migration across every persistence path, not a one-line
  fix -- scoped as its own milestone (see plan.md) rather than bolted on
  ad hoc.

- **(Post-Milestone-8 fix)** Real-world feedback from the first actual
  fresh-VM/fresh-agent test of this skill (a different real GitHub
  account than schr3b3r's, per the whole point of this project): the
  original `SKILL.md` Step 1 front-loaded GitHub + Fulcra + Gemini auth
  into a single big numbered-list message before doing anything, which
  felt like a lot to absorb at once. Rewrote Step 1 to walk through each
  requirement one at a time in conversation (GitHub fully resolved, THEN
  Fulcra, THEN Gemini) rather than asking for everything up front. Also
  changed the GitHub auth default: previously it just said "obtain a
  PAT"; now it defaults to the OAuth device-code browser flow (open a
  browser, enter a short code) as the lower-friction path for a human at
  a fresh machine, falling back to a manually-created PAT only if the
  device flow genuinely can't run. Inlined the actual proven device-flow
  curl commands directly into SKILL.md (rather than only referencing the
  bundled `github-auth` skill by name) since a genuinely fresh
  VM/session may not have that skill bundled -- this profile itself
  opted out of bundled-skill seeding, so "assume it's there" was not a
  safe default.

- **(Milestone 8 complete)** Built `engineering_journey.py`, unifying all project layers
  behind a single, clean CLI entrypoint with `backfill` and `generate` subcommands following
  Context-Compute Separation. `backfill` orchestrates raw ingestion, day/week/month/quarter/year
  rollups, and personal baseline notability signals; `generate` synthesizes narrative Markdown
  documents from stored Fulcra records without re-querying GitHub APIs. Accepts configurable
  multi-year history bounds (`--years`, `--start-date`, `--end-date`) and environment variable fallbacks
  (`GITHUB_TOKEN`, `GITHUB_USERNAME`, `FULCRA_CREDENTIALS_PATH`). Authored root `SKILL.md` (agent-facing
  instructions in Hermes format) and root `README.md` (human-facing developer documentation), and
  `requirements.txt`. Verified end-to-end execution of `generate` via the unified CLI on real `schr3b3r`
  data (8,540 character output document), and added complete orchestration unit tests in `tests/test_engineering_journey.py`.
  **Real bug found and fixed post-task-run:** the task run's own `run_backfill`
  orchestration passed the FULL requested date range straight to
  `generate_day_week_rollups`, with no 90-day cutoff -- but that function
  (and `generate_month_rollups`) has no internal recency boundary of its
  own; only `github_activity.generate_period_chunks` (used for RAW
  ingestion) enforces Interview decision #1's "recent 90 days
  daily/weekly, older monthly" split. Left as originally written, running
  `backfill` over a real 3-4 year range (exactly what this project is
  about to be used for) would have generated one daily rollup -- and one
  real LLM call -- for every day across the ENTIRE multi-year window
  (~1,100-1,460 calls instead of ~90), directly contradicting the
  decaying-granularity design that exists specifically to keep the
  narrative pass's total LLM-call count reasonable (see Interview
  decision #5). Fixed by splitting the requested range at the same
  90-day boundary inside `run_backfill` itself (`RECENT_WINDOW_DAYS`
  constant) before calling `generate_day_week_rollups` (recent window
  only) vs. `generate_month_rollups` (older window only) -- quarter/year
  layer rollups still span the full range, since they aggregate whichever
  child rollups exist. Added `test_run_backfill_orchestration_flow`
  (updated to assert the split call arguments over a real ~5-month range)
  and a new `test_run_backfill_short_range_skips_month_rollups` covering
  the case where the whole requested range fits inside the recent
  window (month rollups correctly skipped rather than called with an
  inverted/empty range). Also removed stray duplicate `SKILL.md`/
  `README.md`/`requirements.txt` files the task run had accidentally
  written into `app/` in addition to the (correct) repo root copies.
  Full suite reran clean after the fix (one `test_write_and_read_raw_activities`
  failure was the already-documented eventual-consistency flake above --
  passed cleanly on immediate retry in isolation, not a real regression).
- **(Milestone 7 complete)** Built `narrative.py`, the final read +
  synthesize + write-to-disk pass over the full rollup/notability
  structure. `build_section_contexts` picks quarter rollups as the
  chronological backbone when present (falling back to month rollups,
  then a calendar-month grouping of whatever's available), and attaches
  each backbone period's child week/day/month rollups + their
  `NotabilitySignal`s as detail context -- days are dropped from the
  child list whenever week rollups already cover the same dates, to
  avoid listing the same activity twice (mirrors Milestone 5's
  day/week double-count fix, applied at the narrative layer instead of
  the stats layer). `_synthesize_section_narrative` builds one grounded
  prompt per backbone section (not per sub-period) containing every
  child period's real stats/flags/explanation, and instructs the LLM
  (via `harness.providers.gemini.call_model`, reused as-is) to give
  notable sub-periods (score >= 0.4 or any of
  high_volume/new_repo/focus_switch/streak) real multi-paragraph prose
  and quiet/routine sub-periods a single compressed transition
  clause -- both in the same document, per Interview decision #3 (gaps
  are real data, not noise to hide). A separate `_synthesize_overview`
  call produces a short executive-summary intro grounded in the same
  per-section stats. A markdown "Appendix: Provenance & Data
  References" table maps every backbone section back to its top-level
  rollup ID, max notability score, flags, and (truncated) child rollup
  IDs, satisfying the provenance requirement without needing a new
  Fulcra record type -- this pass is read+synthesize+write-a-file only,
  by design. Runnable directly via `python narrative.py [--username]
  [--start-date] [--end-date] [--output]` (defaults to schr3b3r's real
  Q3 2026 range), matching Milestone 8's eventual "generate journey from
  already-ingested data" entrypoint.
  **Real output observed:** ran against schr3b3r's real 2026-07-01 to
  2026-09-30 data (38 rollups, 35 notability signals evaluated); only
  one quarter rollup existed for that range, so the document has one
  `## Q3 2026` section, with real, specific multi-paragraph prose about
  the actual repos/work (`fulcradynamics/community-skills`,
  `flow-state-app-v2`, `fulcra-agent-harness-starter` -- real narrative,
  not generic boilerplate) for the high-volume/new-repo/focus-switch
  stretches, and a real compressed clause ("Following a brief period of
  inactivity in early August...") for the quiet week rather than a
  silent omission. Output written to
  `app/engineering_journey_schr3b3r.md` (not committed -- generated
  output, not source, and it names a real account; regenerable any time
  via the CLI entrypoint above).
  **Real bug found and fixed post-task-run (not a Milestone 7 bug):**
  the harness task run's own initial full-suite run failed one
  pre-existing test (`test_real_account_notability_signal_uses_real_rollups`,
  asserting exactly one `NotabilitySignal` per real week rollup) because
  9 stray `NotabilitySignal` records for schr3b3r/week existed in Fulcra
  from an earlier manual/task run that didn't get cleaned up -- the same
  recurring "stray ad-hoc Fulcra writes" issue noted after Milestone 1.
  Fixed by clearing them via `clear_notability_signals` (not a code
  change); confirmed the affected test and then the full suite both pass
  clean afterward. The original task run hit the harness's
  `max_iterations=30` cap before reaching `git_commit` -- completed
  manually: verified the real generated files, cleaned up the stray
  records above, updated `app/features/INDEX.md` /
  `app/features/07_narrative_generation.md` / this file (the task run
  had written the code and the real output but not these doc updates
  yet), reran the full suite clean, and committed.
- **(Milestone 6 complete)** Built `notability.py` implementing the
  `NotabilitySignal` Fulcra record model and personal-baseline comparison logic.
  `compute_baseline_stats` calculates mean and standard deviation of total activity
  and commit counts across same-period_type rollups for an account.
  `generate_notability_signal` evaluates a period against personal baseline and
  detects volume spikes (`high_volume`), first activity in a repository (`new_repo`),
  dominant repository focus shifts (`focus_switch`), activity gaps following active
  stretches (`low_volume_gap`), and sustained activity streaks (`streak`), scoring
  notability between 0.0 and 1.0 with human-readable explanations and provenance
  linking to `source_rollup_id`.
  `generate_notability_signals` integrates into `checkpoint.process_with_checkpoint`
  for resumable execution across multiple periods. Verified on real data in Fulcra
  and thoroughly tested in `tests/test_notability.py`.
  **Post-task-run follow-up:** the task's own `git_commit` attempt failed
  the test gate on a timeout, not a test failure (`TEST_RUNNER_TIMEOUT_SECONDS`,
  last raised to 300s in Milestone 3, was no longer enough once this
  feature's real tests were added to the growing suite) — raised to 480s
  in `harness/tools/git_tool.py`. Also added
  `test_real_account_notability_signal_uses_real_rollups`, computing
  signals against schr3b3r's actual stored week rollups (not just
  synthetic data under a throwaway username, matching the verification
  bar Milestones 4-5 held themselves to): correctly identified the
  account's single busiest real week (69 activities vs a 13.5 baseline
  average) as the highest-scored, `high_volume`+`focus_switch`-flagged
  signal among its real weeks, two real zero-activity weeks as
  `low_volume_gap`, and a real first-time repo appearance as `new_repo`.
  **Real bug found and fixed:** Milestone 5's own real-data test
  (`test_real_data_rollup_generation_end_to_end` in `test_rollup.py`)
  cleaned up after itself with `clear_rollups(username=username,
  client=client)` — no `period_type` filter — which tombstones ALL of
  that username's rollups, not just the month/quarter ones the test
  itself created. Every full-suite run was silently wiping schr3b3r's
  real day/week rollups (Milestone 4's data) as a side effect of
  Milestone 5's test cleanup. Fixed by scoping that test's cleanup to
  `period_type="month"` and `period_type="quarter"` specifically. Real
  day/week rollups were regenerated afterward to restore the account's
  rollup history for future milestones/testing.
- **(Known intermittent flake, mitigated)** `test_write_and_read_raw_activities`
  in `test_github_activity.py` has repeatedly (3 times during Milestone 6's
  commit attempts) failed the git_commit test gate's full-suite run with a
  0-records-read-back result, then passed cleanly in isolation seconds
  later — the same eventual-consistency category as the other polling
  fixes in this log, just with a larger gap between write and read under
  full-suite load than its 15s poll timeout covered. Bumped that test's
  `timeout_seconds` from 15.0 to 30.0 as a mitigation. If this keeps
  recurring even at 30s, treat it as a signal that Fulcra's real
  eventual-consistency window is longer under sustained load than these
  polling timeouts assume, not as a flaky-test-to-ignore.
- **(Milestone 5 complete)** Extended `rollup.py` with month, quarter, and
  year rollup logic. `generate_month_rollup_chunks`, `generate_quarter_rollup_chunks`,
  and `generate_year_rollup_chunks` divide date ranges into calendar period chunks.
  `generate_month_rollups` processes raw `GitHubActivityRaw` records directly into
  `period_type="month"` rollups via `generate_period_rollup`, skipping the weekly
  layer for historical activity (>90 days old) per Interview decision #1.
  `generate_layer_rollup` / `generate_layer_rollups` builds higher-layer rollups
  (`quarter`, `year`) from lower-layer child rollups (`week` or `month`), aggregating
  child volume stats, calling Gemini to synthesize child summaries, and referencing
  child `ActivityRollup` record IDs in `source_record_ids` to maintain full provenance
  down to raw activity. Integrated into `checkpoint.process_with_checkpoint` for full
  resumability. Verified on real data in Fulcra and fully tested in `tests/test_rollup.py`.
  **Real bug found and fixed post-task-run:** `generate_layer_rollup`'s
  `child_period_types` filter had no default, so a quarter/year rollup
  built from `read_rollups()` (which returns every stored rollup
  regardless of period_type) would aggregate BOTH the "day" and "week"
  rollups Milestone 4's `generate_day_week_rollups` always produces for
  the same underlying dates — double-counting that activity's stats.
  Fixed by defaulting `child_period_types` to `["week", "month"]`
  (excluding "day"), with a regression test
  (`test_generate_layer_rollup_excludes_day_by_default_to_avoid_double_count`)
  proving a day+week pair covering identical activity is counted once,
  not twice, by default.
- **(Milestone 4 complete)** `ActivityRollup` Fulcra record type +
  `write_rollup(s)`/`read_rollups`/`clear_rollups` (same
  `MomentAnnotation`-based pattern as prior record types) added in the
  new `rollup.py`. `generate_period_rollup` computes structured volume
  stats directly from matching `GitHubActivityRaw` records (no LLM
  needed for counts) and calls `harness.providers.gemini.call_model`
  (the existing provider, reused as-is) for the narrative summary, with
  an explicit `source_record_ids` provenance chain.
  `generate_day_week_rollups` chunks a date range into day AND week
  work items and wires them into Milestone 1's unchanged
  `process_with_checkpoint` — proven resumable with a real
  interrupt-at-index-2/resume test across 4 work items.
  **Real bug found and fixed:** the LLM narrative call was failing
  silently with `GEMINI_API_KEY not set` whenever code ran without
  `harness/run_task.py`'s own `load_dotenv()` — including through the
  `git_commit` test gate itself (which invokes bare `python -m pytest`
  from `app/`, never `run_task.py`). This meant every rollup generated
  via the gate would silently produce generic stats-only boilerplate
  text instead of a real summary, with no visible error — a test could
  pass while doing the wrong thing. Fixed by (1) adding
  `app/tests/conftest.py` to load `.env` before any test module runs,
  and (2) making the previously-silent `except Exception` fallback in
  `generate_period_rollup` log a warning with the real error instead of
  swallowing it, so a genuine future failure (rate limit, bad key, etc.)
  is visible rather than masquerading as success. Found by actually
  reading a generated rollup's summary text and noticing it was generic
  boilerplate, not by a failing assertion.
  **Real output observed:** topped up a small real ingestion window
  (2026-07-15 to 2026-08-23, 130 real activities across 3 repos) since
  Milestone 3's own test cleanup had emptied Fulcra of prior raw
  records, then rolled up a real day (2026-08-20, 53 real activities in
  `schr3b3r/fulcra-community-projects`) — the generated narrative
  correctly, specifically described that day's real work (scaffolding
  the flow-state-app-v2 harness, the FastAPI audio pipeline, the
  SvelteKit frontend rebuild, real bug fixes) rather than generic text,
  confirming the LLM summarization path is grounded in real content.
  The task run for this milestone hit the harness's `max_iterations=30`
  cap before finishing (built `rollup.py`/`tests/test_rollup.py`, 5/6
  tests passing) — completed manually: topped up real data, fixed a
  test's hardcoded stale date (now dynamically picks whichever real day
  has the most activity, so it won't silently start skipping once that
  date's data is cleaned up later), fixed a `clear_rollups()` call bug
  (unsupported `start_date` kwarg), found/fixed the dotenv gap above,
  reran the full suite, and committed.
- **(Milestone 3 complete)** `GitHubClient.enumerate_repositories`
  (chunks a full date window into <=1-year GraphQL queries — empirically
  required: a real `contributionsCollection` call spanning >1 year
  returns a real GraphQL VALIDATION error, "The total time spanned by
  'from' and 'to' must not exceed 1 year"; confirmed live, not assumed
  from docs), `generate_period_chunks` (weekly for the most recent 90
  days, monthly older, per Interview decision #1), `build_backfill_work_items`
  (repo x period-chunk work-item list, chronological by period then
  alphabetical by repo), and `backfill_full_github_activity` (wires all
  of the above into Milestone 1's unchanged `process_with_checkpoint`)
  added in `github_activity.py`/`github_client.py`. Milestone 2's
  per-item fetch/store logic was factored out into
  `_ingest_single_item_activity` so both `ingest_github_activity` (single
  window) and `backfill_full_github_activity` (full multi-period backfill)
  share it rather than duplicating it.
  **Real numbers observed:** enumerating repos across a real ~3-year
  window (schr3b3r, 2023-08-23 to 2026-08-23) took ~0.7s and found 8
  repos; that window chunks into 47 period chunks / 376 total work items
  at current chunking parameters. The real interrupt-and-resume demo (2
  repos x 15 period chunks = 30 work items, spanning both monthly and
  weekly granularity, interrupted at index 5 via `interrupt_at_index`
  then resumed via a genuinely separate call) completed all 30 items
  correctly (`resumed_from_index == 5`, `completed_items_count ==
  total_items == 30`) in 137s of real wall-clock time across both calls.
  Naively extrapolating per-item cost (137s / 30 items ≈ 4.6s/item,
  dominated by GitHub Search API rate-limit backoff sleeps, not raw
  request latency) to the full 376-item/8-repo/3-year case suggests
  roughly 25-30 minutes of real wall-clock time for a genuinely complete
  3-year backfill of this account — a real, if rough, answer to
  Architecture risk #2, replacing the pre-build guess. This is
  backoff-dominated, not fetch-dominated: see the rate-limit fix below.
  **Real bug found and fixed via this demo itself:** GitHub's REST
  Search API has a much stricter rate limit (30 req/min authenticated)
  than the core REST API. 3 search calls per work item (commits, PRs,
  issues) across tens of items in quick succession hit a real 403 rate
  limit response partway through the first resumability demo run.
  Fixed in `GitHubClient._paginate_search`: detect a rate-limit 403
  specifically (via `X-RateLimit-Remaining: 0` or a "rate limit" message,
  not just any 403 — a private/missing repo can also 403 and should NOT
  be retried the same way) and back off using `Retry-After` or
  `X-RateLimit-Reset` if present, falling back to a flat 60s, up to 5
  retries, rather than failing the whole backfill on an expected,
  transient condition. This was found and fixed by actually running the
  real demo, not anticipated speculatively beforehand.
- **(Milestone 2 complete)** `GitHubClient` (github_client.py) built
  against real GitHub REST/GraphQL APIs via `requests` directly —
  accepts token+username as constructor args or `GITHUB_TOKEN`/
  `GITHUB_USERNAME` env vars, no `gh` CLI dependency anywhere in the
  implementation. `GitHubActivityRaw` (github_activity.py) durable
  record type follows the same pattern as `GitHubBackfillProgress`.
  `ingest_github_activity` wires ingestion into Milestone 1's
  `process_with_checkpoint` directly (checkpointing per repo), rather
  than a separate resumability mechanism. Proven end-to-end against
  REAL GitHub data (June 2026 activity on `fulcradynamics/agent-skills`
  and `schr3b3r/agent-testing`) — real records ingested into Fulcra,
  read back, confirmed non-empty real content. Also proven: a real
  interrupt-and-resume test using real GitHub API calls (not fake work
  items this time), same pattern as Milestone 1's isolated test.
  `read_raw_activities` needed the same eventual-consistency polling
  fix as `list_checkpoints` (see below) — same root cause, same fix
  shape, applied here as `expected_min_count`/`timeout_seconds`.
- **(Milestone 1 complete)** `GitHubBackfillProgress` checkpoint type +
  `write_checkpoint`/`read_checkpoint`/`list_checkpoints`/`clear_checkpoint`/
  `process_with_checkpoint` built in `checkpoint.py`, tested against fake
  work items (not real GitHub data — deliberately, per the Plan's
  sequencing philosophy). Real resumability verified: process items
  1-100, interrupt at item 47, restart from a fresh call, confirm it
  resumes at item 48 with zero duplicates or gaps. Took 3 harness task
  runs to land (see "Fulcra SDK usage notes" above, added after the
  first 2 runs burned their entire iteration budget on SDK exploration
  rather than writing code) plus one follow-up fix:
  `list_checkpoints` initially had a real intermittent test failure —
  querying Fulcra immediately after two back-to-back writes, with no
  poll/retry, occasionally missed a just-written record (Fulcra writes
  are eventually consistent). Fixed by adding an `expected_task_ids` +
  `timeout_seconds` polling option, used by the test, rather than a
  blind `sleep()`.
- **(harness bug found and fixed)** The `git_commit` tool's test gate
  was invoking bare `pytest`, which does NOT add the current directory
  to `sys.path` the way `python -m pytest` does. Since `app/tests/` has
  no `__init__.py` (normal, not a bug), this meant any test doing a
  plain top-level `import fulcra_client` (exactly the pattern this
  project's own `ENGINEERING_STANDARDS.md` recommends) failed to import
  under the gate specifically, while passing fine when run directly.
  This blocked committing Milestone 1's genuinely-passing work. Fixed in
  `harness/tools/git_tool.py` (now invokes `python -m pytest`) and
  upstream in `fulcra-agent-harness-starter`'s `engine/tools/git_tool.py`
  so future scaffolds don't hit this (see that repo's PR #17).
- **(process note, not architecture)** Multiple exploratory/ad-hoc
  Fulcra writes during manual debugging (outside any test's own
  try/finally cleanup) left real stray records in Fulcra across the
  Milestone 1 work — 146 total across several cleanup passes. Going
  forward: prefer writing throwaway exploration through a mechanism that
  cleans up after itself (a test with try/finally, or an explicit
  cleanup call immediately after), rather than leaving ad-hoc
  `record_data_type` calls unresolved during manual API exploration.
- **(initial)** Scaffolded from the fulcra-agent-harness-starter kit.
  Architecture, Interview, and Plan artifacts from the
  fulcra-rapid-prototype skill's Intake/Interview/Architecture/Plan phases
  informed this file's initial content — see `intake/`, `interview/`,
  `architecture.md`, and `plan.md` at the repo root (outside `app/`, since
  they're prototyping-phase artifacts, not part of the running app) for
  the full reasoning that produced this starting point.
