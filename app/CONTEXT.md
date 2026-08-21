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
Milestone 1 (resumable backfill checkpoint) is DONE — see
`checkpoint.py` and `app/features/01_resumable_backfill_progress.md`.
Milestone 2 (real GitHub ingestion) is the next task
(`harness/prompts/task_002_milestone-2-github-ingestion-real-api-calls.md`).
See `plan.md` (at the repo root) for the full intended build sequence.

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

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

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
