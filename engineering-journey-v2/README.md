# Engineering Journey v2

Ingest a user-provided number of years of a developer's GitHub activity
(from their own authenticated account) into Fulcra as durable, queryable
records, and support turning that raw activity into different kinds of
readable output — a paced narrative "story," a resume-style overview
blurb, or the data backing a future custom dashboard. This is a ground-up
rebuild, not an iteration on any prior implementation: no existing
codebase, prior architecture, or prior lessons-learned are being...

## Layout

- `harness/` — the agent harness. Talks to the Google Gemini API directly
  (no agent framework), runs its own control loop, and manages its own
  state. Scaffolded from the
  [fulcra-rapid-prototype](https://github.com/fulcradynamics/community-skills/tree/main/skills/fulcra-rapid-prototype)
  skill — see that skill's README for how this was generated and how to
  regenerate/update the generic parts.
  - `providers/` — model-provider adapters (Gemini currently; structured so
    a second provider could be added later without touching the control
    loop or tools).
  - `tools/` — the explicit set of actions the agent is allowed to take,
    all sandboxed to `app/`: `read_file`/`write_file`/`list_files`,
    `git_diff`/`git_commit`, and `run_command`.
  - `prompts/` — system prompt and task prompts, kept as plain markdown so
    they're easy to iterate on without touching code. `system_prompt.md`
    was generated once from this project's Architecture/Plan artifacts
    (see below) and is expected to be hand-edited from here on as the
    project evolves.
  - `loop.py` — the control loop: call the model, dispatch any tool calls,
    feed results back, repeat until natural completion or a max-iteration
    stop condition.
  - `run_task.py` — entry point for running a real task against the
    harness.
- `app/` — the actual application code the harness produces, plus its own
  `CONTEXT.md` (durable, agent-maintained project memory) and
  `features/` (structured per-feature specs with acceptance criteria).
  Deliberately kept separate from `harness/` so it's always clear which
  layer is "the agent" and which is "the thing the agent is working on."
- `intake/`, `interview/`, `architecture.md`, `plan.md` — artifacts from
  the `fulcra-prototype-grill-me` skill's Intake/Interview/Architecture/Plan
  phases, which is how this project's requirements were originally
  gathered before the harness was scaffolded. Kept at the repo root
  (outside `app/`) since they document the *prototyping process*, not the
  running application itself.

## Getting started

```bash
cd harness  # or wherever this README lives relative to the venv
python -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env  # then fill in GEMINI_API_KEY
.venv/bin/python -m harness.test_loop_smoke      # confirm the harness itself works
.venv/bin/python -m harness.run_task task_001_*.md  # run the first real task
```

## Status

Freshly scaffolded — no code written yet. See `plan.md` (at the repo root) for the intended build sequence.
