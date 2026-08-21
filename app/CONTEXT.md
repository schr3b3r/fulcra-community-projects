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

- **(initial)** Scaffolded from the fulcra-agent-harness-starter kit.
  Architecture, Interview, and Plan artifacts from the
  fulcra-rapid-prototype skill's Intake/Interview/Architecture/Plan phases
  informed this file's initial content — see `intake/`, `interview/`,
  `architecture.md`, and `plan.md` at the repo root (outside `app/`, since
  they're prototyping-phase artifacts, not part of the running app) for
  the full reasoning that produced this starting point.
