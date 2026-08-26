# Task: Milestone 1: Resumable backfill checkpoint, proven in isolation

## Context
Engineering Journey v2: Ingest a user-provided number of years of a developer's GitHub activity
(from their own authenticated account) into Fulcra as durable, queryable
records, and support turning that raw activity into different kinds of
readable output — a paced narrative "story," a resume-style overview
blurb, or the data backing a future custom dashboard. This is a ground-up
rebuild, not an iteration on any prior implementation: no existing
codebase, prior architecture, or prior lessons-learned are being...

This is the first task, generated from plan.md's first milestone. Full architecture context is in `architecture.md` and `app/CONTEXT.md` if you need more than the summary below.

## Your task right now
Build the "GitHub Backfill Checkpoint" Fulcra record type and
read/write-checkpoint functions, tested against FAKE work items (not
real GitHub data) -- process items 1 through N, kill the process
partway through, restart from a fresh process, confirm correct resume
without reprocessing or skipping. Also proves the per-repo tag-based
tracking design (Architecture's `repo` tag on this type) actually
supports the "detect which repos are already covered when extending
backward/forward" requirement from Intake, using fake repo names before
any real GitHub enumeration exists. No GitHub API calls in this
milestone.

Keep it minimal and correct rather than elaborate. When you're done, give a
short summary of the files you created/changed and the test results.

## Reminders (see app/ENGINEERING_STANDARDS.md for the full list)
- Type hints throughout.
- Automated tests (pytest) covering this task's acceptance criteria, and
  the FULL test suite passes — not just tests for what you just changed.
- Use the `fulcra-api` Python SDK (not the CLI, not subprocess) for any
  Fulcra integration this task touches.
- Update `app/features/INDEX.md` and the relevant `app/features/*.md` file
  if this task completes or advances a tracked feature.
- Commit your work with `git_commit` once tests pass. Remember: git_commit
  will refuse to commit if the test suite fails, so make sure it's green
  first.
