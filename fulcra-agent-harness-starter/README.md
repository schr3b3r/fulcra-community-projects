# fulcra-agent-harness-starter

A starter kit that scaffolds a small, hand-rolled agent harness (control
loop + sandboxed tools + model provider adapter) for a new project built
on [Fulcra](https://docs.fulcradynamics.com/), using the
`fulcra-rapid-prototype` skill's Intake/Interview/Architecture/Plan phases
to gather requirements before generating anything.

This is both a **usable tool** (run `scripts/scaffold.py` to get a working
project skeleton in seconds) and a **reference implementation** of the
patterns described in
[fulcra-for-agents.md](https://github.com/kubla/fulcra-for-agents/blob/main/fulcra-for-agents.md) —
the generated `app/ENGINEERING_STANDARDS.md` encodes those patterns
(Context–Compute Separation, Derived Context, Resumable Discovery) as
concrete, checkable rules rather than abstract advice.

It was extracted from a real, working agent harness (built and battle-
tested across multiple real features on an earlier project), generalized
here to remove that project's specific content — the engine underneath
this starter kit is proven, not speculative.

## Quick start

```bash
# 1. Run fulcra-rapid-prototype's Intake -> Interview -> Architecture ->
#    Plan phases with your project idea (see that skill's own docs).
#    This produces intake/brief.md, architecture.md, plan.md somewhere.

# 2. Scaffold a new project from those artifacts:
python scripts/scaffold.py \
  --project-name "My Project" \
  --rapid-prototype-dir /path/to/rapid-prototype-output \
  --output-dir /path/to/new-project \
  --dry-run   # always look before you leap

# Drop --dry-run once the plan looks right:
python scripts/scaffold.py \
  --project-name "My Project" \
  --rapid-prototype-dir /path/to/rapid-prototype-output \
  --output-dir /path/to/new-project

# 3. Set up and verify the new project. If you saw "Preserving
#    fulcra-rapid-prototype git history" above, a repo with the real
#    Intake/Interview/Architecture/Plan commits already exists --
#    just commit the new files on top:
cd /path/to/new-project
git log --oneline   # confirm the real phase history came through
git add -A && git commit -m "Scaffold harness + app"
# Otherwise (no source git repo was found), initialize fresh instead:
#   git init && git add -A && git commit -m "Initial scaffold"
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env   # fill in GEMINI_API_KEY
.venv/bin/python -m harness.test_loop_smoke   # confirm it actually works

# 4. Run the first real task:
.venv/bin/python -m harness.run_task task_001_*.md
```

See `SKILL.md` for the full, step-by-step orchestration this is meant to
be run through (as a Hermes skill), including where the
`fulcra-rapid-prototype` phases fit in and what to verify before handing
a scaffolded project back to the user.

## Layout

```
fulcra-agent-harness-starter/
├── SKILL.md              # the actual skill — step-by-step orchestration
├── README.md              # this file — human-facing overview
├── engine/                 # project-agnostic agent harness, copied
│   │                        verbatim into every scaffolded project's
│   │                        harness/ directory
│   ├── loop.py              # the control loop (model -> tools -> repeat)
│   ├── run_task.py           # entry point: run a real task
│   ├── providers/
│   │   └── gemini.py           # the only file that knows about Gemini's
│   │                            SDK shapes; swap/add providers here
│   ├── tools/
│   │   ├── filesystem.py       # sandboxed read/write/list, scoped to app/
│   │   ├── git_tool.py          # git_diff / git_commit (with a test-gate:
│   │   │                         refuses to commit if pytest is red)
│   │   └── run_command.py        # sandboxed shell execution, hard timeout
│   └── prompts/
│       └── __init__.py            # loads system_prompt.md / task_*.md /
│                                    app/CONTEXT.md
├── templates/               # the handful of files that DO need
│   │                          per-project hydration (plain {{PLACEHOLDER}}
│   │                          substitution, no templating framework)
│   ├── system_prompt.md.template
│   ├── task.md.template
│   ├── README.md.template
│   ├── pyproject.toml.template
│   ├── .gitignore.template
│   ├── .env.example.template
│   └── app/
│       ├── CONTEXT.md.template
│       ├── ENGINEERING_STANDARDS.md.template   # encodes fulcra-for-agents.md patterns
│       └── features/
│           ├── INDEX.md.template
│           └── _TEMPLATE.md            # per-feature file skeleton, copied verbatim
└── scripts/
    ├── scaffold.py            # reads rapid-prototype artifacts + templates,
    │                            writes a new project's harness/ + app/
    └── tests/
        └── test_scaffold.py    # real tests: run the real script against
                                  real fake artifacts, assert on real output
```

## Why `engine/` vs `templates/` as separate directories

`engine/` is code with zero project-specific content — it gets copied
byte-for-byte into every scaffolded project's `harness/` directory. You
should essentially never need to hand-edit these files after scaffolding;
if you find yourself wanting to, that's usually a sign the change belongs
in a new tool module (`harness/tools/your_thing.py`, registered in
`harness/tools/__init__.py`) or the system prompt, not a fork of the
engine itself.

`templates/` is the small set of files that necessarily differ per
project — because they describe *what the project is*, not *how the
harness works*. These use plain `{{PLACEHOLDER}}` string substitution
(see `scripts/scaffold.py`'s module docstring for why not Jinja2) and are
expected to be hand-edited further after scaffolding — the generated
versions are a real starting point, not a finished product.

## Git history preservation

`fulcra-rapid-prototype` commits after every phase (Intake, Interview,
Architecture, Plan) — it uses that git history plus a `git bundle`
backup specifically so a project can be resumed cleanly across fresh
agent sessions with no shared filesystem. Throwing that history away the
moment a project graduates from prototyping into its own real repo would
undo exactly the continuity that mechanism exists for.

So by default (`--history=auto`), `scripts/scaffold.py` **preserves**
that history: if `--rapid-prototype-dir` is a real git working tree, the
new project is created with `git clone` (bringing every phase commit
along as real history), and the harness/app scaffolding is added on top
as new, uncommitted files for you to commit yourself. If the source
isn't a git repo, it falls back to the old behavior: a fresh repo you
initialize yourself, with the artifact files copied in as plain content
under a single "Initial scaffold" commit.

Force either behavior explicitly with `--history=preserve` (errors out
clearly, rather than silently falling back, if the source isn't a real
git repo) or `--history=copy` (always flattens, even if the source repo
could have been preserved). See `scripts/scaffold.py --help` for the
full flag description, including the constraint that history-preserving
mode needs `--output-dir` to not exist yet at all (a `git clone`
requirement, not something this script imposes).

## Cross-session, cross-machine continuity during Build (no GitHub required)

This continuity story doesn't stop at scaffolding. Every time the
generated harness's `git_commit` tool successfully commits (during the
Build phase, i.e. real task/milestone work), it automatically bundles
the FULL local git history (`git bundle create --all`) and uploads it
to the user's own Fulcra file store, at
`/harness-projects/<project-dir-name>.bundle` — see
`harness/tools/git_tool.py`'s module docstring for the implementation.
This is deliberately automatic (built into the tool itself, not a
separate step a system prompt asks the agent to remember), for the same
reason the test gate is enforced structurally rather than requested: an
agent running low on iteration budget right at the end of a task is
exactly the agent most likely to skip an optional last step.

The practical result: resuming a project on a genuinely fresh VM, with
no shared filesystem and no assumption that GitHub (or any other
hosting) is involved at all, is just:
1. Authenticate to Fulcra (already required for the scaffolded app
   itself to do anything real).
2. Download `/harness-projects/<project-dir-name>.bundle`.
3. `git clone` it.

That's real continuity — full commit history, not just a snapshot —
using only the same Fulcra account the project already needs, with
zero dependency on a GitHub account, SSH key, or any other remote
hosting decision. If a user separately wants a GitHub-hosted, PR-able
copy of the project, they can add a GitHub remote at any time on top of
this — the two aren't mutually exclusive, this mechanism just doesn't
assume or require it as the default path.

The backup step is best-effort and never blocks a commit: if Fulcra
credentials aren't configured yet, or the upload fails for any reason,
`git_commit` still reports the underlying commit as successful (it
really happened) and just appends a warning noting the backup didn't
happen this time.

## Known caveats

- `harness/tools/test_git_commit_gate_smoke.py` (in a scaffolded project)
  can occasionally hit a stale-`__pycache__`-bytecode artifact when run
  multiple times in quick succession against the same filenames — a
  Python/pytest file-mtime-resolution quirk, not a bug in the generated
  code. If you see a confusing pytest failure on this specific smoke test
  that doesn't match what the test script itself asserts, clear
  `app/**/__pycache__` and re-run once before assuming something is
  actually broken.
- `scripts/scaffold.py`'s `extract_first_plan_milestone()` is a heuristic
  (first non-title markdown heading + the text under it), not a strict
  parser of `plan.md`'s structure. It's meant to save you from writing the
  first task prompt entirely from scratch, not to guarantee it picked the
  ideal starting point — review the generated `task_001_*.md` by hand.
- History-preserving mode writes `harness/`, `app/`, `README.md`,
  `pyproject.toml`, `.gitignore`, and `.env.example` directly into the
  cloned repo, overwriting any same-named files that happen to already
  exist there without asking. Not an issue for a typical
  fulcra-rapid-prototype repo (its own files never collide with these
  names), but review `git status`/`git diff` before committing if your
  source repo had its own root-level files with these names.

## Status

Extracted and generalized from a real, previously-built harness (proven
working across multiple real features in that project). The scaffold
script itself has a real pytest suite (`scripts/tests/test_scaffold.py`,
including coverage of both history-preserving and history-flattening
paths against real git repos) and has been manually verified end-to-end:
scaffold a fake project (with and without a real rapid-prototype git
history to preserve), install it, run all six harness smoke tests against
a real Gemini API key, confirm all pass.

Not yet done: no automated CI for this repo itself; the
`--domain-library-guidance` CLI flag is a manual convenience, not derived
automatically from `architecture.md` (parsing that reliably would need
more structure in `fulcra-rapid-prototype`'s own artifact format than it
currently guarantees).
