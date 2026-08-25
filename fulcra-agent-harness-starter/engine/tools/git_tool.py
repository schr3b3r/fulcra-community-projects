"""
Git tools for the harness.

These let the agent record its own progress as real commits — durable
memory in the "git history" sense. Like the filesystem tools, these are
scoped hard: every operation only ever touches paths inside the sandbox
(`app/`), even though git itself operates at the repository root. We
enforce this by always passing `--` <sandbox-relative-path> to git commands,
never allowing the agent to stage or diff arbitrary repo paths (e.g.
harness/ or .env).

Two tools:
  - git_diff()   : show uncommitted changes scoped to app/ (read-only, safe)
  - git_commit(message): stage + commit only app/, with a required message

Deliberately NOT included (out of scope by default): push, branch, reset, or
anything that rewrites history or touches remotes. Those are higher-risk
and better done under explicit human control, at least until you've built
enough trust in a given project's harness to extend it.

Test gate (git_commit): this directly addresses a common failure mode in
agentic coding — an agent regressing previously-working functionality while
adding new features, with no reliable way to catch it. A system prompt
instruction to "run tests before committing" is only ever a request. This
tool makes it structural instead: git_commit runs the app's full pytest
suite (if one exists) before allowing a commit to succeed, and refuses —
raising an error the agent sees as a failed tool call — if any test fails.
It is not possible to commit through this tool while the test suite is red.

If no test suite exists yet (e.g. app/tests/ has no test files), the gate
fails OPEN: there's nothing to regress yet, so commits are allowed. The
moment any test file exists, the gate becomes active for every future
commit.

Fulcra backup (git_commit): after every successful commit, this tool ALSO
bundles the full local git history (`git bundle create --all`) and uploads
it to the user's own Fulcra file store, at
`/harness-projects/<repo-dir-name>.bundle`. This is deliberately automatic,
not a separate step a human or agent has to remember to run -- the exact
same "make it structural, not a request" reasoning as the test gate above
applies here: a system-prompt instruction to "back this up after
committing" is only ever a request, and real usage has shown agents skip
end-of-task steps like this when their iteration budget runs out right
before the end of a task. This gives a project scaffolded by this starter
kit real cross-session, cross-machine continuity WITHOUT requiring a
GitHub account or any other remote -- resuming on a totally fresh VM is
just: authenticate to Fulcra (already required for the app itself),
download one file, `git clone` it. See `fulcra-prototype-grill-me`'s own
"Resuming a Project" section for the same underlying pattern (this reuses
it, just extended past that skill's own Intake/Interview/Architecture/Plan
phases into the Build phase this harness is responsible for). A user who
additionally wants a GitHub-hosted, PR-able copy of the repo can still add
a GitHub remote on top of this at any time -- the two are not mutually
exclusive, and this mechanism does not assume or require GitHub at all.

The backup step is best-effort and NEVER blocks or fails a commit: if
Fulcra credentials aren't configured, the upload fails, or anything else
goes wrong, git_commit still returns success for the underlying commit
(which already happened, is real, and should not be treated as failed
because of an unrelated backup problem) -- it just includes a warning in
the returned message so the human/agent can see something needs
attention, without the whole workflow grinding to a halt over it.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from harness.tools.filesystem import SANDBOX_ROOT

TEST_RUNNER_TIMEOUT_SECONDS = 120

# Same trick as harness/tools/run_command.py: point at the harness's own
# venv so pytest resolves to an environment with the app's dependencies
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
    """Run pytest against the whole app/ sandbox and return the result.

    Deliberately invoked as `python -m pytest`, NOT the bare `pytest`
    executable. This matters, and got this exactly backwards once
    already: `python -m X` prepends the current working directory (as
    `''`) to `sys.path` (standard Python `-m` semantics), while the bare
    `pytest` entry-point script does not. Since app/tests/ has no
    `__init__.py` (a deliberate, normal choice, not a bug), pytest's
    default "prepend" import mode only adds `tests/` itself to
    `sys.path` -- never `app/`, its parent. Any test file that does a
    plain top-level `import fulcra_client` or `import <sibling module in
    app/>` -- which is exactly the pattern this starter kit's own
    `ENGINEERING_STANDARDS.md` and `app/fulcra_client.py` encourage --
    would then fail to import under bare `pytest`, but succeed under
    `python -m pytest`. This was found as a REAL failure: git_commit
    refused a commit with "ModuleNotFoundError: No module named
    'fulcra_client'" even though the exact same test suite passed cleanly
    moments earlier via `python -m pytest`.
    """
    python_bin = _HARNESS_VENV_BIN / "python"
    python = str(python_bin) if python_bin.exists() else "python"
    return subprocess.run(
        [python, "-m", "pytest", "-q"],
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


def _backup_repo_to_fulcra() -> Optional[str]:
    """Bundle the full local git history and upload it to the user's Fulcra
    file store, at /harness-projects/<repo-dir-name>.bundle.

    Best-effort: returns None on success, or a short human-readable warning
    string on any failure (missing credentials, upload error, etc.) -- this
    function must NEVER raise, since a backup failure must never be allowed
    to block or fail an otherwise-successful commit. Callers should surface
    the returned warning to the user/agent, not silently swallow it.
    """
    try:
        repo_root_result = _find_repo_root()
        repo_root = Path(repo_root_result.stdout.strip())
        repo_name = repo_root.name

        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_path = Path(tmp_dir) / f"{repo_name}.bundle"
            bundle_result = subprocess.run(
                ["git", "bundle", "create", str(bundle_path), "--all"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if bundle_result.returncode != 0:
                return (
                    f"[fulcra-backup] Skipped: `git bundle create` failed: "
                    f"{bundle_result.stderr.strip()}"
                )

            # Imported lazily so a harness with no app/fulcra_client.py yet
            # (e.g. mid-scaffold, before Build has started) doesn't fail to
            # import this whole module just because backup isn't possible yet.
            try:
                import sys

                sys.path.insert(0, str(SANDBOX_ROOT))
                from fulcra_client import FulcraAuthError, get_fulcra_client
            except ImportError:
                return (
                    "[fulcra-backup] Skipped: app/fulcra_client.py not found yet "
                    "(nothing to back up to without it)."
                )

            try:
                client = get_fulcra_client()
            except FulcraAuthError as exc:
                return f"[fulcra-backup] Skipped: not authenticated to Fulcra ({exc})."

            file_size = bundle_path.stat().st_size
            with open(bundle_path, "rb") as f:
                client.upload_file(
                    data=f,
                    file_type="application/octet-stream",
                    file_size=file_size,
                    filepath=f"/harness-projects/{repo_name}.bundle",
                )

        return None
    except Exception as exc:
        return f"[fulcra-backup] Skipped due to an unexpected error: {exc}"


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

    After a successful commit, also backs up the full local git history to
    the user's Fulcra file store as a git bundle (see the module docstring's
    "Fulcra backup" section) -- best-effort, never blocks the commit itself.

    Args:
        message: commit message. Required and must be non-empty.

    Returns:
        A short confirmation string including the new commit hash, or a
        message indicating there was nothing to commit. If the Fulcra
        backup step failed, a warning is appended to this string, but the
        commit itself is still reported as successful.

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

    backup_warning = _backup_repo_to_fulcra()
    if backup_warning:
        return f"Committed as {commit_hash}: {message}\n{backup_warning}"
    return f"Committed as {commit_hash}: {message}\n[fulcra-backup] Uploaded full repo history to your Fulcra file store."


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
        "test fails — fix failing tests before calling this. After a "
        "successful commit, also backs up the full repo history to the "
        "user's Fulcra file store as a git bundle (best-effort, never "
        "blocks the commit)."
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
