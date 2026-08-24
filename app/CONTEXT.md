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
Milestones 1 (resumable backfill checkpoint), 2 (real GitHub ingestion),
3 (full 3-year backfill chunking + real at-scale resumability), and 4
(day/week rollup layer with real LLM narrative summaries) are DONE —
see `checkpoint.py`, `github_client.py`, `github_activity.py`,
`rollup.py`, and `app/features/`. Milestone 5 (month/quarter/year
rollups) is next. See `plan.md` (at the repo root) for the full intended
build sequence.

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
