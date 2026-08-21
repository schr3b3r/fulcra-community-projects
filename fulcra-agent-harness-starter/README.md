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

# 3. Set up and verify the new project:
cd /path/to/new-project
git init && git add -A && git commit -m "Initial scaffold"
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

## Status

Extracted and generalized from a real, previously-built harness (proven
working across multiple real features in that project). The scaffold
script itself has a real pytest suite (`scripts/tests/test_scaffold.py`)
and has been manually verified end-to-end: scaffold a fake project,
install it, run all six harness smoke tests against a real Gemini API
key, confirm all pass.

Not yet done: no automated CI for this repo itself; the
`--domain-library-guidance` CLI flag is a manual convenience, not derived
automatically from `architecture.md` (parsing that reliably would need
more structure in `fulcra-rapid-prototype`'s own artifact format than it
currently guarantees).
