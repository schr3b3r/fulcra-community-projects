"""
Command execution tool for the harness — the first tool that lets the agent
actually RUN and verify its own code, rather than just writing files and
asserting success in text.

Security posture (read this before extending the allowed scope):
  - The command's working directory is hard-locked to the app/ sandbox, same
    as the filesystem and git tools.
  - Every invocation has a hard timeout (default 30s, capped at 60s) so a
    hung or long-running process (e.g. a server started in the foreground)
    can't stall the control loop indefinitely.
  - PATH is pointed at the harness's own .venv so `python`/`pip` resolve to
    an environment that already has your project's typical dependencies
    available, without the agent needing to create or manage its own
    virtual environment.

What this tool does NOT do, and should not be assumed to do:
  - It does NOT prevent a malicious or buggy command from affecting things
    outside app/ (e.g. `rm -rf /`, network calls, etc.) — cwd scoping limits
    where relative paths land, but an absolute-path or destructive command
    string is not blocked by inspection. This is an intentional, documented
    limitation appropriate for a learning/prototyping project under direct
    human supervision — NOT something to hand to an untrusted agent
    unsupervised.
"""

import os
import subprocess
from pathlib import Path

from harness.tools.filesystem import SANDBOX_ROOT

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60

# The harness's own virtual environment, whose bin/ directory we prepend to
# PATH so that `python`, `pip`, `uvicorn`, etc. resolve to an environment
# with the app's usual dependencies already installed.
_HARNESS_VENV_BIN = (
    Path(__file__).resolve().parent.parent.parent / ".venv" / "bin"
)


def run_command(command: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run a shell command inside the app/ sandbox directory and return its
    output.

    Use this to verify your own work: run a syntax check, execute a test,
    import a module to confirm it doesn't error, etc. Do not use this to
    start long-running foreground servers (they will be killed at the
    timeout) — prefer short, one-shot verification commands.

    Args:
        command: the shell command to run (executed via the system shell,
            with cwd locked to the app/ sandbox directory).
        timeout_seconds: how long to allow the command to run before it is
            killed. Capped at 60 seconds regardless of the requested value.

    Returns:
        A formatted string containing the exit code, stdout, and stderr.
    """
    timeout = min(timeout_seconds, MAX_TIMEOUT_SECONDS)

    env = os.environ.copy()
    if _HARNESS_VENV_BIN.exists():
        env["PATH"] = f"{_HARNESS_VENV_BIN}{os.pathsep}{env.get('PATH', '')}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=SANDBOX_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (
            f"TIMED OUT after {timeout}s. The command was likely still "
            f"running (e.g. a foreground server) — this tool is for "
            f"short verification commands only, not for starting servers "
            f"that don't exit on their own."
        )

    return (
        f"exit_code: {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


RUN_COMMAND_SCHEMA = {
    "name": "run_command",
    "description": (
        "Run a shell command inside the app/ sandbox directory to verify "
        "your own work (e.g. syntax-check a file, run a quick import test, "
        "run a test suite). The command's working directory is the "
        "sandbox root; `python`/`pip` resolve to an environment with "
        "your project's dependencies already installed. Has a hard "
        "timeout — do NOT use this to start long-running foreground "
        "servers, only for short one-shot verification commands."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run, e.g. 'python -m py_compile main.py'.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": (
                    "Max seconds to allow before killing the command. "
                    "Defaults to 30, capped at 60."
                ),
            },
        },
        "required": ["command"],
    },
}


TOOLS = {
    "run_command": (run_command, RUN_COMMAND_SCHEMA),
}
