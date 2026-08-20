# Engineering Standards

These are hard requirements for all code in this app, not suggestions.
They exist to solve a specific, observed problem: in an earlier version of
this concept, the agent building it kept regressing previously-working
functionality while adding new features, with no reliable way to catch it.
These standards are the fix — they turn "please be careful" into "the
process itself catches you if you're not."

## Testing (the big one)
- Every feature ships with automated tests (pytest) covering its
  acceptance criteria — see each feature's file in `app/features/`.
- **Before declaring any task complete, run the FULL test suite** (e.g.
  `pytest` from the sandbox root), not just tests related to the current
  change. A task that adds a new feature but breaks an old one is not
  done — it's a regression, and the whole point of this standard is to
  catch that automatically instead of hoping nobody notices.
- Tests live under `app/tests/`, mirroring the structure of the code they
  test.
- Prefer real, runnable tests (actually import and exercise the code)
  over tests that only check that a file exists or contains certain text.

## Type hints
Use type hints throughout — function signatures, return types, and
non-trivial variables. This is not optional style preference; it makes
mistakes easier to catch and keeps the codebase honest about what it
expects.

## Prefer established libraries over hand-rolled logic
Don't reinvent things that a well-established library already does well.
Concretely, for this app:
- Audio/DSP: `librosa`, `scipy`, `numpy` — not hand-written signal
  processing.
- Audio conversion: `ffmpeg` (via subprocess or a thin wrapper) — not a
  custom decoder.
- Web framework: FastAPI (already chosen) — don't introduce a second,
  competing framework without a real reason.
- Fulcra integration: the `fulcra-api` Python SDK (`pip install
  fulcra-api`) — NOT the `fulcra-api` CLI, and NOT raw subprocess/shell
  calls to any Fulcra tooling. The SDK gives real Python objects, proper
  exceptions, and testability that shelling out does not. This is a
  deliberate, non-negotiable departure from how a prior version of this
  concept integrated with Fulcra.

## Fulcra-specific patterns
- Use annotation data types (`MomentAnnotation`, custom types via
  `create_annotation`/`record_data_type`) to make application state
  queryable, rather than relying on directory scanning or implicit file
  state. This pattern already proved valuable for locating files by
  semantic query instead of scanning, and is being deliberately extended
  to track pipeline processing status too (see
  `app/features/processing_status_tracking.md`).
- Validate records against their schema (`validate_records`) before
  submitting them where practical, so malformed data is caught with a
  clear error rather than an opaque API rejection.

## Regression prevention (enforced, not just requested)
The `git_commit` tool itself runs the test suite before allowing a commit
to succeed, and refuses to commit if any test fails. This means the rule
above ("run tests before declaring done") is not just an instruction the
agent is expected to follow — it is structurally impossible to commit code
that fails existing tests through that tool. See
`harness/tools/git_tool.py` for the actual mechanism.
