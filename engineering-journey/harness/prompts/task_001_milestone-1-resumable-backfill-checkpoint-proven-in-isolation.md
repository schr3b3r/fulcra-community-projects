# Task: Milestone 1: Resumable backfill checkpoint, proven in isolation

## Context
Engineering Journey: Build a Hermes skill that ingests a developer's GitHub activity history
(commits, PRs, PR reviews, PR/issue discussion) going back approximately
3 years, and produces a single, well-formatted, engaging markdown
document telling the story of their engineering journey over that
period — something they could read for themselves, or share with others,
that captures how their work/focus/scope evolved over time.

This is the first task, generated from plan.md's first milestone. Full architecture context is in `architecture.md` and `app/CONTEXT.md` if you need more than the summary below.

## Your task right now
Build the `GitHubBackfillProgress` Fulcra record type and the
read-checkpoint / write-checkpoint functions around it, tested against
FAKE work items (not real GitHub data yet) — e.g. "process items 1
through 100," kill the process at item 47, restart from a fresh process,
confirm it resumes at 48 and doesn't reprocess 1-47 or skip anything.
This directly and literally tests Architecture risk #3 before anything
else is built on top of it. No GitHub API calls in this milestone at all
— pure Fulcra checkpoint plumbing, kept deliberately decoupled from what
it will eventually checkpoint.

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
