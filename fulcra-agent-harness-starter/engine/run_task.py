"""
Run a real task against the harness.

Usage:
    .venv/bin/python -m harness.run_task task_001_scaffold_backend.md
    .venv/bin/python -m harness.run_task task_001_scaffold_backend.md --max-iterations 60

Gives the agent the full tool registry (filesystem + git + run_command), a
real iteration budget (real work needs more round-trips than a quick smoke
test), and prints the full result for inspection, including the message
transcript so you can see *how* it worked, not just what it produced.
"""

import argparse

from dotenv import load_dotenv

load_dotenv()

from harness.loop import run
from harness.prompts import load_task

# 45 is a reasonable default for genuine feature work (not just
# smoke-test-sized tasks) -- real tasks commonly need dozens of
# read/write/run_command round-trips before reaching git_commit, and
# in practice a task that also needs to write tests, update
# app/CONTEXT.md, and update app/features/INDEX.md before committing
# routinely needs more than 30 (see this starter kit's own README/
# ENGINEERING_STANDARDS.md notes on this if a project has already hit
# this cap repeatedly -- that's a real, recurring signal worth raising
# the default further project-wide, not just for one task). Override
# per-task with --max-iterations for unusually large or exploratory
# work instead of hand-editing this file.
DEFAULT_MAX_ITERATIONS = 45


def main():
    parser = argparse.ArgumentParser(
        description="Run a task prompt against the harness."
    )
    parser.add_argument(
        "task_filename",
        help="Task prompt filename, relative to harness/prompts/ (e.g. task_001_scaffold_backend.md).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=(
            f"Hard cap on model round-trips for this run (default: {DEFAULT_MAX_ITERATIONS}). "
            "Raise this for large or exploratory tasks rather than splitting them "
            "into smaller task prompts purely to fit under a smaller cap -- a task "
            "that legitimately needs tests + doc updates + a commit in one pass "
            "will often need more than the default."
        ),
    )
    args = parser.parse_args()

    task = load_task(args.task_filename)

    print(f"--- Running task: {args.task_filename} (max_iterations={args.max_iterations}) ---\n")
    result = run(task=task, max_iterations=args.max_iterations)

    print("\n" + "=" * 60)
    print("RUN SUMMARY")
    print("=" * 60)
    print("stopped_reason:", result.stopped_reason)
    print("iterations:", result.iterations)
    print("\nfinal_text:\n", result.final_text)

    if result.stopped_reason == "max_iterations":
        print(
            "\n[warning] Stopped due to hitting max_iterations before the model "
            "produced a final turn with no tool calls. This does NOT necessarily "
            "mean the task is incomplete -- check the transcript below and the "
            "actual repo state (git status, git diff) before assuming otherwise. "
            "If this happens repeatedly across tasks in this project, re-run with "
            "a higher --max-iterations rather than treating each occurrence as a "
            "one-off to patch up by hand every time."
        )

    print("\n" + "=" * 60)
    print("FULL MESSAGE TRANSCRIPT")
    print("=" * 60)
    for i, msg in enumerate(result.messages):
        role = msg["role"]
        if role == "tool":
            print(f"[{i}] tool ({msg['name']}): {msg['content']!r}")
        elif role == "assistant" and msg.get("tool_calls"):
            calls = ", ".join(
                f"{c['name']}({c.get('args', {})})" for c in msg["tool_calls"]
            )
            print(f"[{i}] assistant (tool call): {calls}")
        else:
            print(f"[{i}] {role}: {msg['content']!r}")


if __name__ == "__main__":
    main()
