"""
Standalone smoke test for the control loop, run from the repo root so the
`harness` package resolves correctly:

    .venv/bin/python -m harness.test_loop_smoke

This is the first test that exercises the FULL path: model -> tool call ->
tool execution -> result fed back -> model -> final answer. If this passes,
the core mechanics of the harness (piece #2 and #3 from our design) are
proven to work together, not just in isolation.
"""

from dotenv import load_dotenv

load_dotenv()

from harness.loop import run
from harness.tools.filesystem import TOOLS


def main():
    print("--- Smoke test: force a real write_file tool call ---")
    result = run(
        task=(
            "Create a file called 'greeting.txt' inside the sandbox with "
            "the exact content 'Hello from the harness control loop.' "
            "Then confirm you did it."
        ),
        tools=TOOLS,
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
