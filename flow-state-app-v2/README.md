# Flow State App v2 — Agent Harness Learning Project

This folder is a hands-on exercise in **agent harness engineering**, using the
original `flow-state-app` (see `../flow-state-app/CONTEXT.md`) as the subject
matter. The app itself is secondary — the point is to build, from first
principles, a small standalone harness capable of understanding, running, and
extending that codebase.

## Layout

- `harness/` — the agent harness itself. This is the thing we're actually
  building and learning from. It talks to the Anthropic API directly (no
  agent framework), runs its own control loop, and manages its own state.
  - `providers/` — model-provider adapters (Anthropic first; structured so a
    second provider, e.g. Gemini, could be added later without touching the
    control loop).
  - `tools/` — the small, explicit set of actions the agent is allowed to take
    (read/write files, run scoped commands, git operations).
  - `prompts/` — system prompt and any templated prompt pieces, kept as plain
    text/markdown so they're easy to iterate on without touching code.
  - `state/` — per-run scratchpad and any persisted state the harness needs
    across runs.
- `app/` — where the recreated/extended Flow State application code will
  live once the harness starts producing it. Deliberately kept separate from
  `harness/` so it's always clear which layer is "the agent" and which is
  "the thing the agent is working on."

## Status

Scaffolding stage — folder structure only, no logic yet. Being built
incrementally, one small step at a time.
