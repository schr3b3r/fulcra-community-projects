"""
Standalone smoke test for the git_commit test gate.

Run from repo root:
    .venv/bin/python -m harness.tools.test_git_commit_gate_smoke

This is the most safety-critical smoke test in this starter kit — it proves
the gate that's supposed to prevent regressions actually works, both when
it should allow a commit and when it should refuse one.
"""

import subprocess

from harness.tools.filesystem import SANDBOX_ROOT, write_file
from harness.tools.git_tool import git_commit


def _git(*args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=SANDBOX_ROOT, capture_output=True, text=True
    )
    return result.stdout


def main():
    tests_dir = SANDBOX_ROOT / "tests"
    assert not tests_dir.exists(), (
        "app/tests/ already exists — this test assumes a clean slate to "
        "properly exercise the fail-open/fail-closed transition. Run this "
        "smoke test on a repo state with no existing test suite (e.g. "
        "right after scaffolding a brand-new project)."
    )

    print("--- Test 1: no test suite yet -> gate fails OPEN, commit allowed ---")
    write_file("gate_smoke_test.txt", "no tests exist yet\n")
    result = git_commit("Smoke test: gate fail-open (no tests exist)")
    print(result)
    assert result.startswith("Committed as"), f"Expected commit to succeed: {result}"
    # This starter kit's own repo has no app/fulcra_client.py (that file
    # only exists in a SCAFFOLDED project) -- the Fulcra backup step must
    # skip gracefully in that case, not raise, and must say so rather than
    # silently doing nothing.
    assert "[fulcra-backup]" in result, (
        f"Expected a fulcra-backup status line in the commit result: {result}"
    )

    print("\n--- Test 2: add a FAILING test -> gate fails CLOSED, commit refused ---")
    write_file("tests/test_gate_smoke.py", "def test_this_fails():\n    assert False\n")
    write_file("gate_smoke_test.txt", "second change, should be blocked\n")
    try:
        git_commit("Smoke test: this commit should be REFUSED")
        raise AssertionError("Expected git_commit to raise RuntimeError, but it didn't!")
    except RuntimeError as e:
        print("correctly refused:", str(e)[:200], "...")
        assert "Refusing to commit" in str(e)

    # Confirm the working tree still shows the change as uncommitted —
    # i.e. the refusal genuinely didn't commit anything.
    status = _git("status", "--short")
    print("git status after refusal:", repr(status))
    assert "gate_smoke_test.txt" in status or "test_gate_smoke.py" in status, (
        "Expected uncommitted changes to still be present after a refused commit"
    )

    print("\n--- Test 3: fix the test -> gate reopens, commit succeeds ---")
    write_file("tests/test_gate_smoke.py", "def test_this_passes():\n    assert True\n")
    result = git_commit("Smoke test: gate reopens once tests pass")
    print(result)
    assert result.startswith("Committed as"), f"Expected commit to succeed: {result}"

    print("\n--- Cleanup: reset back to before this test's commits ---")
    # Use reset --soft rather than revert: this test always runs on a clean
    # slate (asserted at the top), so its two commits are always the tip of
    # history — a straightforward reset is simpler and avoids revert
    # merge-conflict edge cases entirely (e.g. if both commits touched the
    # same lines). Leaves no partial-revert state behind for whoever runs
    # this test next.
    pre_test_commit = _git("rev-parse", "HEAD~2").strip()
    subprocess.run(["git", "reset", "--soft", pre_test_commit], cwd=SANDBOX_ROOT, check=True)
    subprocess.run(
        ["git", "restore", "--staged", "gate_smoke_test.txt", "tests/test_gate_smoke.py"],
        cwd=SANDBOX_ROOT,
    )
    (SANDBOX_ROOT / "gate_smoke_test.txt").unlink(missing_ok=True)
    test_file = SANDBOX_ROOT / "tests" / "test_gate_smoke.py"
    test_file.unlink(missing_ok=True)
    if (SANDBOX_ROOT / "tests").exists() and not any((SANDBOX_ROOT / "tests").iterdir()):
        (SANDBOX_ROOT / "tests").rmdir()
    print("git log after cleanup:", _git("log", "-2", "--oneline"))
    print("git status after cleanup:", repr(_git("status", "--short")))

    print("\nAll git_commit test-gate smoke checks passed.")


if __name__ == "__main__":
    main()
