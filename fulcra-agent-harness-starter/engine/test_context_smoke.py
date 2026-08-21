"""
Standalone smoke test for app/CONTEXT.md auto-loading.

Run from repo root:
    .venv/bin/python -m harness.test_context_smoke

This asserts against the mechanism (does load_app_context read the real
file? does it get prepended to tasks? does it correctly return None when
absent?) rather than any specific project's content, so it works unchanged
regardless of what you're building.
"""

from dotenv import load_dotenv

load_dotenv()

from harness.loop import run
from harness.prompts import load_app_context
from harness.tools.filesystem import SANDBOX_ROOT


def main():
    context_path = SANDBOX_ROOT / "CONTEXT.md"

    print("--- Test 1: load_app_context reads the real app/CONTEXT.md ---")
    context = load_app_context()
    print("loaded:", (context or "")[:80], "...")
    assert context is not None, (
        "Expected app/CONTEXT.md to exist by now — did scripts/scaffold.py "
        "run successfully? See templates/CONTEXT.md.template."
    )

    print("\n--- Test 2: load_app_context returns None when the file is absent ---")
    # Temporarily rename the real file to simulate a brand-new sandbox.
    backup_path = SANDBOX_ROOT / "CONTEXT.md.smoke_test_backup"
    context_path.rename(backup_path)
    try:
        result = load_app_context()
        print("result when absent:", result)
        assert result is None
    finally:
        backup_path.rename(context_path)  # always restore, even on failure

    print("\n--- Test 3: run() actually prepends context (visible in the transcript) ---")
    # Use a trivial task and no tools, just to inspect what the first
    # message in the transcript actually contains — this proves the
    # prepending really happens, not just that the function exists.
    result = run(
        task="Reply with exactly the word: AFFIRMATIVE",
        tools={},
        include_app_context=True,
        max_iterations=1,
    )
    first_message = result.messages[0]["content"]
    print("first message starts with:", first_message[:60])
    assert "App context" in first_message
    assert "AFFIRMATIVE" in first_message  # original task text still present
    # The real CONTEXT.md content should appear verbatim somewhere in the
    # prepended block -- check for a substring of the actual file rather
    # than any hardcoded project name, so this test works for any project.
    assert context is not None
    context_snippet = context.strip().splitlines()[0]
    assert context_snippet in first_message, (
        "Expected the real CONTEXT.md content to be prepended verbatim"
    )

    print("\n--- Test 4: include_app_context=False skips it entirely ---")
    result = run(
        task="Reply with exactly the word: AFFIRMATIVE",
        tools={},
        include_app_context=False,
        max_iterations=1,
    )
    first_message = result.messages[0]["content"]
    print("first message:", first_message)
    assert "App context" not in first_message
    assert first_message == "Reply with exactly the word: AFFIRMATIVE"

    print("\nAll app-context smoke checks passed.")


if __name__ == "__main__":
    main()
