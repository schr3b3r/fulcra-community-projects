---
name: fulcra-agent-harness-starter
description: "Scaffolds a hand-rolled agent harness (control loop + sandboxed tools + provider adapter) for a new project built on Fulcra, using fulcra-rapid-prototype's Intake/Interview/Architecture/Plan phases to gather requirements before generating the harness. Trigger when the user wants to build something new on Fulcra with a custom agentic build loop, rather than using Hermes/Claude Code directly."
author: schr3b3r
version: 1.0.0
metadata:
  tags: [fulcra, agent-harness, scaffolding, meta, rapid-prototype]
---

# Fulcra Agent Harness Starter

This skill turns a project idea into a **running, project-specific agent
harness** — a small, hand-rolled control loop (model call -> tool
dispatch -> feedback -> repeat) with sandboxed file/git/shell tools, a
system prompt describing the specific project, and a first real task
prompt to run against it. It does not build the project itself; it builds
the *thing that will build the project*, then hands off.

This exists as a reference implementation of building on Fulcra with an
agent harness — see
[fulcra-for-agents.md](https://github.com/kubla/fulcra-for-agents/blob/main/fulcra-for-agents.md)
for the architectural patterns (Context-Compute Separation, Derived
Context, Resumable Discovery, etc.) this starter kit's generated
`ENGINEERING_STANDARDS.md` encodes as concrete rules.

## When to use this skill
Trigger this when the user explicitly wants to:
- Build a new application/tool on top of Fulcra using a **custom agent
  harness** they control and can inspect/modify (not just "have Claude
  Code build it directly").
- Learn agent-harness engineering fundamentals by having a real, minimal
  reference implementation to study and extend.

Do NOT use this for: quick one-off scripts, tasks where the user just
wants you (Claude Code) to build something directly without a separate
harness layer, or projects with no Fulcra involvement at all (the
generated harness's ENGINEERING_STANDARDS.md assumes Fulcra as the data
backend).

## Prerequisites
- The `fulcra-rapid-prototype` skill must be available (it lives in the
  `fulcradynamics/community-skills` repo). This skill depends on it for
  the Intake/Interview/Architecture/Plan phases — it does not duplicate
  that requirements-gathering logic.
- A Gemini API key will be needed eventually (the generated harness
  uses `google-genai` — see `engine/providers/gemini.py`'s docstring
  if you want to swap providers later; that's a deliberate extension
  point, not a limitation to work around here), but **do not ask the
  user for it now.** None of Intake, Interview, Architecture, or Plan
  need it -- those phases are pure conversation/document work with no
  model calls of their own. Only ask for the key at Step 5, right
  before it's actually needed to run the harness for the first time --
  asking for it up front is unnecessary friction before the user even
  knows what they're building, and (worse) an unused credential sitting
  around from step 1 is one more thing that can go stale, get
  forgotten, or get asked for again redundantly if the session breaks
  and resumes later.

## The flow (follow these steps in order)

### 1. Run fulcra-rapid-prototype through its Plan phase
Load `fulcra-rapid-prototype` and run its Intake -> Interview ->
Architecture -> Plan phases with the user, exactly as that skill
specifies (including its Architecture user gate — do not skip it). Stop
before that skill's own Prototype/Build phases: this starter kit's
generated harness is what replaces those two phases for a project that
wants a custom harness, not something layered on top of them.

By the end of this step you should have, in the rapid-prototype project's
git repo:
```
intake/brief.md
interview/findings.md
architecture.md   (approved by the user)
plan.md
```

If the user already has these from a previous session, confirm they're
still current before proceeding — don't re-run the phases from scratch if
recent, approved artifacts already exist.

### 2. Confirm this starter kit is available
This skill's actual scaffolding logic lives in a sibling project directory
(not inside `~/.hermes/skills/`) so it can be tested, versioned, and
published independently:
`fulcra-community-projects/fulcra-agent-harness-starter/`

If you don't already have a local clone of `fulcra-community-projects`,
clone it. This skill assumes `scripts/scaffold.py` inside that repo is
available to run.

### 3. Decide where the new project will live
Ask the user where the new project's own repo/directory should be created
(a new directory, typically a sibling of other projects — NOT inside
`fulcra-agent-harness-starter/` itself, which stays a template, not a
place real projects accumulate).

### 4. Run the scaffold script
```bash
cd fulcra-agent-harness-starter
python scripts/scaffold.py \
  --project-name "<Human-readable project name>" \
  --rapid-prototype-dir <path to the repo with intake/, architecture.md, plan.md> \
  --output-dir <path to the new project's directory> \
  --domain-library-guidance "- For X: use library Y, not a hand-rolled Z."
```
Run with `--dry-run` first and show the user what would be written before
doing the real run — this is good practice for any scaffolding operation,
and cheap to do since dry-run makes no filesystem changes.

`--domain-library-guidance` is optional but worth filling in if the
Architecture phase surfaced an obvious domain (e.g. "audio processing" ->
`librosa`/`scipy`/`numpy`; "web backend" -> pick one framework). If
omitted, the generated `ENGINEERING_STANDARDS.md` will contain a `TODO`
placeholder for the user to fill in by hand — that's an acceptable
outcome, not a failure, since not every project has an obvious domain
library set worth calling out this early.

**Git history:** by default (`--history=auto`) this script PRESERVES
fulcra-rapid-prototype's real phase-by-phase commit history — if
`--rapid-prototype-dir` is a git working tree (the normal case, since
that skill commits after every phase), the new project is created by
cloning it, so a future session can `git log` the new project and see
the actual Intake/Interview/Architecture/Plan commits, not just their
content flattened into one commit. This matters for the same reason
fulcra-rapid-prototype uses `git bundle` for cross-session continuity in
the first place — don't throw that continuity away at the exact moment
the project graduates to its own repo.

If the user has a `.bundle` backup instead of a live checkout, unpack it
first (`git clone <bundle> <dir>`, per fulcra-rapid-prototype's own
"Resuming a Project" instructions) and point `--rapid-prototype-dir` at
the unpacked directory. If `--rapid-prototype-dir` isn't a git repo at
all, this script automatically falls back to flattening (equivalent to
`--history=copy`) — that's a normal, silent fallback for `auto`, not an
error. Only pass `--history=preserve` explicitly if you want a hard
failure instead of a silent fallback (e.g. to catch a mistake in which
directory you pointed at).

Note: history-preserving mode clones directly into `--output-dir`, which
means that path must not exist yet at all (not even as an empty
directory) — this is a real constraint of `git clone`, not a limitation
of this script. If you hit this, either delete/rename the target first
or pick a fresh path.

### 5. Verify the scaffold actually works before handing off
Do NOT just report "scaffolding complete" once the script exits — that is
exactly the kind of unverified claim this project's own engineering
standards exist to prevent. Before running any of the commands below,
**explicitly ask the user for a Gemini API key now** (this is the first
point in the whole flow it's actually needed -- see Prerequisites above
for why it's deliberately not asked for any earlier) and write it into
the new project's `.env` yourself once given:
```bash
cd <new project dir>
git log --oneline   # if history was preserved, confirm the real
                     # Intake/Interview/Architecture/Plan commits are
                     # there, not just one flattened commit
git add -A && git commit -m "Scaffold harness + app"   # or "git init &&
                     # git add -A && git commit -m 'Initial scaffold'"
                     # if history was NOT preserved (no repo exists yet
                     # in that case) -- the script's own final output
                     # tells you which applies
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env   # then write the user's actual Gemini API key
                        # into GEMINI_API_KEY yourself -- don't just
                        # tell the user to go edit the file by hand,
                        # since you already have the key from asking
                        # them a moment ago
.venv/bin/python -m harness.test_loop_smoke
.venv/bin/python -m harness.test_context_smoke
.venv/bin/python -m harness.tools.test_filesystem_smoke
.venv/bin/python -m harness.tools.test_git_smoke
.venv/bin/python -m harness.tools.test_git_commit_gate_smoke
.venv/bin/python -m harness.tools.test_run_command_smoke
```
All six should pass. If any fails, that's a real bug — fix it before
telling the user the harness is ready (see this starter kit's own
`scripts/tests/test_scaffold.py` and the "Known caveats" section in this
repo's README for issues already identified and how they were resolved).

Known caveat: `test_git_commit_gate_smoke.py` can occasionally show a
stale-bytecode-cache artifact from very fast successive writes to the
same test filename within one process's lifetime (a Python/pytest mtime-
resolution quirk, not a bug in this starter kit's code). If it fails on
the first run, clear `app/**/__pycache__` and re-run once before assuming
something is actually broken.

### 6. Hand off to the user
Point the user at:
- `harness/prompts/system_prompt.md` and the generated
  `harness/prompts/task_001_*.md` — tell them explicitly these were
  generated by heuristics from `plan.md` and are a starting point to
  review/edit, not a finished, guaranteed-correct artifact.
- `README.md` (in the new project) for the getting-started steps.
- `app/CONTEXT.md` / `app/features/` for how the harness will track its
  own progress once real tasks start running.

Then either run the first task yourself (`python -m harness.run_task
task_001_*.md`) if the user wants to see it in action immediately, or
stop here and let the user run it themselves.

## What this skill deliberately does NOT do
- It does not gather requirements itself — that's `fulcra-rapid-prototype`'s
  job, reused rather than duplicated.
- It does not run the generated harness's Build phase autonomously beyond
  the verification smoke tests in step 5 — the user decides when/how much
  to let the freshly-scaffolded agent build on its own.
- It does not template every file in a scaffolded project loosely with a
  general-purpose templating engine (no Jinja2) — see
  `scripts/scaffold.py`'s module docstring for why plain string
  substitution is a deliberate choice, not a shortcut.
