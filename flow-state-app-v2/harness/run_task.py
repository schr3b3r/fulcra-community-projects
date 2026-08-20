"""
Run a real task against the harness — not a smoke test. This is the first
time we point the control loop at genuine, open-ended work rather than a
task we basically dictated the answer to.

Usage:
    .venv/bin/python -m harness.run_task task_scaffold_backend.md

Gives the agent the full tool registry (filesystem + git), a higher
iteration budget than the smoke tests (real work may need more round-trips),
and prints the full result for inspection, including the message transcript
so we can see *how* it worked, not just what it produced.
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
    result = run(task=task, max_iterations=15)

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
