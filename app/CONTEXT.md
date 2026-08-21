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
Not yet written: `GitHubBackfillProgress` (Milestone 1's checkpoint type)
does not exist yet. Two consecutive harness task runs against this
milestone burned their entire iteration budget on Fulcra SDK exploration
(auth wiring, then `record_data_type`'s exact call signature) without
writing any checkpoint code. See "Fulcra SDK usage notes (verified)"
below for what those two runs discovered, captured here specifically so
a third run doesn't have to rediscover it — read that section before
writing any Fulcra integration code in this project.

See `plan.md` (at the repo root) for the intended build sequence.

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

- **(initial)** Scaffolded from the fulcra-agent-harness-starter kit.
  Architecture, Interview, and Plan artifacts from the
  fulcra-rapid-prototype skill's Intake/Interview/Architecture/Plan phases
  informed this file's initial content — see `intake/`, `interview/`,
  `architecture.md`, and `plan.md` at the repo root (outside `app/`, since
  they're prototyping-phase artifacts, not part of the running app) for
  the full reasoning that produced this starting point.
