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
"""

import subprocess

from harness.tools.filesystem import SANDBOX_ROOT


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

    Args:
        message: commit message. Required and must be non-empty.

    Returns:
        A short confirmation string including the new commit hash, or a
        message indicating there was nothing to commit.
    """
    if not message or not message.strip():
        raise ValueError("Commit message must not be empty.")

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
        "descriptive commit message."
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
