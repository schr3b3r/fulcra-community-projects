"""
Standalone smoke test for the control loop, run from the repo root so the
`harness` package resolves correctly:

    .venv/bin/python -m harness.test_loop_smoke

This is the first test that exercises the FULL path: model -> tool call ->
tool execution -> result fed back -> model -> final answer. If this passes,
the core mechanics of the harness (control loop + tools + provider adapter
wired together) are proven to work, not just in isolation. Run this right
after scaffolding a new project, before writing any real task prompts, to
confirm the harness itself is functional in this environment (API key
set, dependencies installed, etc.) before you start trusting it with real
work.
"""

from dotenv import load_dotenv

load_dotenv()

from harness.loop import run
from harness.tools.filesystem import TOOLS as FILESYSTEM_TOOLS


def main():
    print("--- Smoke test: force a real write_file tool call ---")
    # Deliberately scoped to filesystem-only tools for this test: giving it
    # the full ALL_TOOLS registry (including git_commit) can cause it to
    # autonomously commit its own test output during a run — fine for real
    # tasks, but not what you want happening on every smoke-test run.
    result = run(
        task=(
            "Create a file called 'greeting.txt' inside the sandbox with "
            "the exact content 'Hello from the harness control loop.' "
            "Then confirm you did it."
        ),
        tools=FILESYSTEM_TOOLS,
        include_app_context=False,  # isolated mechanics test, not a real task
    )

    print("\n=== RUN RESULT ===")
    print("stopped_reason:", result.stopped_reason)
    print("iterations:", result.iterations)
    print("final_text:", result.final_text)

    assert result.stopped_reason == "completed", "Loop did not complete normally"

    # Verify the tool call actually had a real, observable effect on disk —
    # not just that the model claimed success.
    from harness.tools.filesystem import read_file

    content = read_file("greeting.txt")
    print("\nfile on disk contains:", repr(content))
    assert "Hello from the harness control loop." in content

    print("\nLoop smoke test passed: tool call had a real, verified effect.")


if __name__ == "__main__":
    main()
