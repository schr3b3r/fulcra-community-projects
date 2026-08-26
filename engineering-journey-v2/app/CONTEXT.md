# Engineering Journey v2: Project Context & Architecture

This document is the durable memory for this app, maintained by the agent
itself across tasks. Read this before starting any new task. Update it
whenever you make an architectural decision, pivot, or complete a
significant milestone — so the next task (run by you or a future agent) has
accurate context without needing to re-derive it from the diff history.

This project is independent: it does not reference or depend on any other
app's code, files, or context. Record all decisions relevant to this app
here.

## The Product
Ingest a user-provided number of years of a developer's GitHub activity
(from their own authenticated account) into Fulcra as durable, queryable
records, and support turning that raw activity into different kinds of
readable output — a paced narrative "story," a resume-style overview
blurb, or the data backing a future custom dashboard. This is a ground-up
rebuild, not an iteration on any prior implementation: no existing
codebase, prior architecture, or prior lessons-learned are being...

A ground-up rebuild (see `intake/brief.md` for full scope) that backfills
a user-specified span of one GitHub identity's activity (all contribution
types, public and private repos) into Fulcra as durable, per-item, real
custom-typed records; builds precomputed day/week/month/quarter/year
rollups and a per-period notability signal on top; and ships a lightweight
markdown narrative generator reading that structure. Ingestion/rollup math
is fully deterministic; only rollup-summary text and narrative generation
invoke a model, and only whatever model is already running the skill --
no bundled LLM provider dependency.

(See `architecture.md` at the repo root for the full architecture writeup this summary was excerpted from.)

## Current State
Freshly scaffolded — no code written yet. See `plan.md` (at the repo root) for the intended build sequence.

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(initial)** Scaffolded from the fulcra-rapid-prototype skill.
  Architecture, Interview, and Plan artifacts from the
  fulcra-prototype-grill-me skill's Intake/Interview/Architecture/Plan phases
  informed this file's initial content — see `intake/`, `interview/`,
  `architecture.md`, and `plan.md` at the repo root (outside `app/`, since
  they're prototyping-phase artifacts, not part of the running app) for
  the full reasoning that produced this starting point.
