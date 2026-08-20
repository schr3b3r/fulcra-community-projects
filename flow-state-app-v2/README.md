# Flow State App v2 — Agent Harness Learning Project

This folder is a hands-on exercise in **agent harness engineering**. It is
inspired by an earlier "Flow State" concept (a web app for musicians to
record jam sessions and auto-extract musical ideas via an audio marker),
but this project is fully independent — it does not reference, import from,
or depend on any other app's code or files. Any resemblance to a prior
version is conceptual only; all context and history for this app lives
entirely within this folder (see `app/CONTEXT.md`).

The app itself is secondary — the point is to build, from first principles,
a small standalone harness capable of understanding, running, and extending
a real codebase.

## Layout

- `harness/` — the agent harness itself. This is the thing we're actually
  building and learning from. It talks to the Google Gemini API directly
  (no agent framework), runs its own control loop, and manages its own
  state.
  - `providers/` — model-provider adapters (Gemini currently; structured so
    a second provider could be added later without touching the control
    loop or tools).
  - `tools/` — the explicit set of actions the agent is allowed to take,
    all sandboxed to `app/`: `read_file`/`write_file`/`list_files`,
    `git_diff`/`git_commit`, and `run_command` (execute + self-verify).
  - `prompts/` — system prompt and task prompts, kept as plain markdown so
    they're easy to iterate on without touching code. Also handles loading
    `app/CONTEXT.md` automatically into every task.
  - `loop.py` — the control loop: call the model, dispatch any tool calls,
    feed results back, repeat until natural completion or a max-iteration
    stop condition.
  - `run_task.py` — entry point for running a real task against the
    harness (as opposed to the various `test_*_smoke.py` files, which
    exercise individual pieces in isolation).
- `app/` — the actual application code the harness produces, plus its own
  `CONTEXT.md` (durable, agent-maintained project memory — architecture
  decisions, current state, etc.). Deliberately kept separate from
  `harness/` so it's always clear which layer is "the agent" and which is
  "the thing the agent is working on."

## Status

Foundational harness work is complete and tested: provider adapter,
sandboxed tools (file I/O, git, command execution), control loop, and
auto-loaded project memory are all in place. A first real task (scaffolding
a minimal FastAPI backend) has been run successfully end-to-end. Next up:
real feature work on the app itself.
