"""
Standalone smoke test for the git tools. Uses the real git repo (the one
this project lives in) and the real app/ sandbox — so it cleans up after
itself.

Run from repo root:
    .venv/bin/python -m harness.tools.test_git_smoke
"""

import subprocess

from harness.tools.filesystem import SANDBOX_ROOT, write_file
from harness.tools.git_tool import git_commit, git_diff


def _git(*args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=SANDBOX_ROOT, capture_output=True, text=True
    )
    return result.stdout


def main():
    print("--- Test 1: git_diff on a fresh untracked file shows nothing ---")
    # Untracked files don't show in `git diff` (only tracked-but-modified
    # ones do) — this confirms our scoped diff behaves like normal git.
    write_file("git_smoke_test.txt", "temporary content for smoke test\n")
    diff_before_add = git_diff()
    print("diff (untracked, expected empty):", repr(diff_before_add))

    print("\n--- Test 2: git_commit stages and commits only app/ ---")
    result = git_commit("Smoke test: add temporary file")
    print(result)
    assert result.startswith("Committed as"), f"Unexpected result: {result}"

    print("\n--- Test 3: verify the commit is real and scoped to app/ ---")
    log_output = _git("log", "-1", "--stat")
    print(log_output)
    assert "git_smoke_test.txt" in log_output
    # Confirm no files outside app/ were swept into this commit.
    assert "harness/" not in log_output
    assert ".env" not in log_output

    print("\n--- Test 4: git_commit with nothing staged is handled cleanly ---")
    result = git_commit("Should be a no-op")
    print(result)
    assert result.startswith("Nothing to commit")

    print("\n--- Cleanup: revert the smoke test commit ---")
    _git("revert", "--no-edit", "HEAD")
    log_output = _git("log", "-1", "--stat")
    print(log_output)

    print("\nAll git tool smoke checks passed.")


if __name__ == "__main__":
    main()
