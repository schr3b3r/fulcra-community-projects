"""
Run a real task against the harness.

Usage:
    .venv/bin/python -m harness.run_task task_001_scaffold_backend.md

Gives the agent the full tool registry (filesystem + git + run_command), a
real iteration budget (real work needs more round-trips than a quick smoke
test), and prints the full result for inspection, including the message
transcript so you can see *how* it worked, not just what it produced.
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from harness.loop import run
from harness.prompts import load_task


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m harness.run_task <task_prompt_filename>")
        sys.exit(1)

    task_filename = sys.argv[1]
    task = load_task(task_filename)

    print(f"--- Running task: {task_filename} ---\n")
    # 30 is a reasonable default for genuine feature work (not just
    # smoke-test-sized tasks) — real tasks commonly need dozens of
    # read/write/run_command round-trips before reaching git_commit. Raise
    # it further for large or exploratory tasks.
    result = run(task=task, max_iterations=30)

    print("\n" + "=" * 60)
    print("RUN SUMMARY")
    print("=" * 60)
    print("stopped_reason:", result.stopped_reason)
    print("iterations:", result.iterations)
    print("\nfinal_text:\n", result.final_text)

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
