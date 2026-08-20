"""
Git tools for the harness.

These let the agent record its own progress as real commits — durable
memory in the "git history" sense from our original harness design (piece
#4: state/memory). Like the filesystem tools, these are scoped hard: every
operation only ever touches paths inside the sandbox (`app/`), even though
git itself operates at the repository root. We enforce this by always
passing `--` <sandbox-relative-path> to git commands, never allowing the
agent to stage or diff arbitrary repo paths (e.g. harness/ or .env).

Two tools:
  - git_diff()   : show uncommitted changes scoped to app/ (read-only,safe)
  - git_commit(message): stage + commit only app/, with a required message

Deliberately NOT included (out of scope for now): push, branch, reset, or
anything that rewrites history or touches remotes. Those are higher-risk
and better done under explicit human control for the time being.

Test gate (git_commit): this directly addresses a real, observed failure
mode from an earlier version of this concept — the agent kept regressing
previously-working functionality while adding new features, with no
reliable way to catch it. The system prompt already instructs the agent to
run the full test suite before considering a task done, but a prompt
instruction is only ever a request. This tool makes it structural instead:
git_commit runs the app's full pytest suite (if one exists) before
allowing a commit to succeed, and refuses — raising an error the agent
sees as a failed tool call — if any test fails. It is not possible to
commit through this tool while the test suite is red.

If no test suite exists yet (e.g. app/tests/ has no test files), the gate
fails OPEN: there's nothing to regress yet, so commits are allowed. The
moment any test file exists, the gate becomes active for every future
commit.
"""

import subprocess

from harness.tools.filesystem import SANDBOX_ROOT

TEST_RUNNER_TIMEOUT_SECONDS = 120

# Same trick as harness/tools/run_command.py: point at the harness's own
# venv so `pytest` resolves to an environment with the app's dependencies
# already installed, without the agent needing to manage its own venv.
_HARNESS_VENV_BIN = SANDBOX_ROOT.parent / ".venv" / "bin"


def _test_suite_exists() -> bool:
    """Whether there's any pytest-discoverable test file under app/ yet.

    Used to decide whether the commit gate should be enforced (fail
    closed) or skipped because there's nothing to regress yet (fail open).
    """
    tests_dir = SANDBOX_ROOT / "tests"
    if not tests_dir.exists():
        return False
    return any(tests_dir.rglob("test_*.py")) or any(tests_dir.rglob("*_test.py"))


def _run_test_suite() -> subprocess.CompletedProcess:
    """Run pytest against the whole app/ sandbox and return the result."""
    pytest_bin = _HARNESS_VENV_BIN / "pytest"
    command = str(pytest_bin) if pytest_bin.exists() else "pytest"
    return subprocess.run(
        [command, "-q"],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
        timeout=TEST_RUNNER_TIMEOUT_SECONDS,
    )


def _find_repo_root() -> "subprocess.CompletedProcess":
    """Locate the git repo root that contains the sandbox, once per call."""
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )


def git_diff() -> str:
    """Show uncommitted changes scoped to the app/ sandbox directory only.

    Returns:
        The diff text (empty string if there are no changes).
    """
    result = subprocess.run(
        ["git", "diff", "--", str(SANDBOX_ROOT)],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout or "(no uncommitted changes)"


def git_commit(message: str) -> str:
    """Stage and commit changes, scoped ONLY to the app/ sandbox directory.

    Never stages or commits anything outside app/ (e.g. the harness's own
    code, .env, or unrelated repo files) even if such changes exist.

    Before committing, runs the app's full pytest suite (if any test files
    exist under app/tests/) and refuses to commit if any test fails. This
    is a hard gate, not a suggestion — see the module docstring for why.

    Args:
        message: commit message. Required and must be non-empty.

    Returns:
        A short confirmation string including the new commit hash, or a
        message indicating there was nothing to commit.

    Raises:
        RuntimeError: if the test suite exists and fails, or if a git
            command itself fails.
    """
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

    if _test_suite_exists():
        try:
            test_result = _run_test_suite()
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Refusing to commit: the test suite did not finish within "
                f"{TEST_RUNNER_TIMEOUT_SECONDS}s. Fix whatever is hanging "
                f"before committing."
            )
        if test_result.returncode != 0:
            raise RuntimeError(
                "Refusing to commit: the test suite is failing. Fix the "
                "failing test(s) before committing — committing broken "
                "code is not allowed.\n"
                f"--- pytest output ---\n{test_result.stdout}\n{test_result.stderr}"
            )

    add_result = subprocess.run(
        ["git", "add", "--", str(SANDBOX_ROOT)],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        raise RuntimeError(f"git add failed: {add_result.stderr.strip()}")

    # Check whether there's actually anything staged before attempting a
    # commit, so we can give a clear, honest result either way.
    status_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", str(SANDBOX_ROOT)],
        cwd=SANDBOX_ROOT,
    )
    if status_result.returncode == 0:
        return "Nothing to commit (no staged changes in app/)."

    commit_result = subprocess.run(
        ["git", "commit", "-m", message, "--", str(SANDBOX_ROOT)],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
    )
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")

    hash_result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=SANDBOX_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    commit_hash = hash_result.stdout.strip()
    return f"Committed as {commit_hash}: {message}"


# --- Schemas (Gemini function-calling format) ---------------------------

GIT_DIFF_SCHEMA = {
    "name": "git_diff",
    "description": (
        "Show uncommitted changes, scoped only to the app/ sandbox "
        "directory. Read-only and always safe to call."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

GIT_COMMIT_SCHEMA = {
    "name": "git_commit",
    "description": (
        "Stage and commit all current changes inside the app/ sandbox "
        "directory only. Never touches files outside app/. Requires a "
        "descriptive commit message. If a test suite exists under "
        "app/tests/, this tool runs it first and REFUSES to commit if any "
        "test fails — fix failing tests before calling this."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "A short, descriptive commit message.",
            },
        },
        "required": ["message"],
    },
}


TOOLS = {
    "git_diff": (git_diff, GIT_DIFF_SCHEMA),
    "git_commit": (git_commit, GIT_COMMIT_SCHEMA),
}
