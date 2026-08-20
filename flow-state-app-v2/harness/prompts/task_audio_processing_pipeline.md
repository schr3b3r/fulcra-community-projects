# Task: Build the Audio Processing Pipeline feature

Build the feature described in `features/audio_processing_pipeline.md`.
Read that file in full before starting — it is the source of truth for
what "done" means here, including its acceptance criteria.

## Key points to keep in mind
- Real test fixtures already exist at `tests/fixtures/marker.webm` and
  `tests/fixtures/raw_session.webm` (see `tests/fixtures/README.md` for
  their properties and validated ground truth). Use these for real tests,
  not synthetic audio.
- Follow `ENGINEERING_STANDARDS.md`: type hints throughout, automated
  pytest tests covering the acceptance criteria, and use ffmpeg via
  subprocess (not a hand-rolled decoder) for the actual conversion.
- This feature does not require a live WebSocket session — build and test
  it standalone, given `.webm` files as input.
- When finished, update this feature's status and acceptance-criteria
  checkboxes in `features/audio_processing_pipeline.md`, and keep
  `features/INDEX.md`'s status column in sync.
- Commit your work with `git_commit` once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.

Give a clear summary of what you built and the test results when done.
