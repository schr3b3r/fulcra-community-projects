"""
Filesystem tools for the harness.

These are the first tools the agent is given, and deliberately the most
dangerous category (arbitrary file read/write) — so they're scoped hard to a
single sandbox directory (the `app/` folder where your project's actual code
lives). The agent cannot use these tools to read or write anything outside
that boundary, including the harness's own code, its `.env` secrets, or the
rest of the git repo.

Each tool is:
  1. A plain Python function (independently callable/testable, no model
     involved).
  2. A JSON schema `dict`, in the shape Gemini's function-calling expects,
     describing the tool for the model.

The dispatcher (`TOOLS`) maps tool name -> (function, schema) so the control
loop can look up and execute whatever the model asks for by name.
"""

from pathlib import Path

# The one and only directory these tools are allowed to touch.
# Resolved once, at import time, relative to this file's location:
#   harness/tools/filesystem.py -> <project root>/ -> app/
# This assumes the standard layout this starter kit scaffolds:
#   <project>/harness/...  and  <project>/app/...
# If you ever restructure the project layout, this is the one line to
# change — everything else in the harness derives from SANDBOX_ROOT.
SANDBOX_ROOT = (Path(__file__).resolve().parent.parent.parent / "app").resolve()


class SandboxViolation(Exception):
    """Raised when a tool call tries to access a path outside SANDBOX_ROOT."""


def _resolve_in_sandbox(relative_path: str) -> Path:
    """Resolve a user/model-supplied relative path safely inside SANDBOX_ROOT.

    Rejects absolute paths and any traversal (e.g. "../../etc/passwd") that
    would escape the sandbox, even after symlink/`..` resolution.
    """
    if Path(relative_path).is_absolute():
        raise SandboxViolation(
            f"Absolute paths are not allowed: {relative_path!r}"
        )

    candidate = (SANDBOX_ROOT / relative_path).resolve()

    # is_relative_to requires Python 3.9+; this starter kit targets 3.11+.
    if not candidate.is_relative_to(SANDBOX_ROOT):
        raise SandboxViolation(
            f"Path {relative_path!r} resolves outside the sandbox "
            f"({SANDBOX_ROOT}): {candidate}"
        )

    return candidate


def read_file(path: str) -> str:
    """Read a UTF-8 text file from within the sandbox directory.

    Args:
        path: path relative to the sandbox root (the app/ directory).

    Returns:
        The file's contents as a string.
    """
    full_path = _resolve_in_sandbox(path)
    if not full_path.exists():
        raise FileNotFoundError(f"No such file in sandbox: {path!r}")
    if not full_path.is_file():
        raise IsADirectoryError(f"Not a file: {path!r}")
    return full_path.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    """Write (create or overwrite) a UTF-8 text file within the sandbox.

    Creates parent directories as needed, but only inside the sandbox.

    Args:
        path: path relative to the sandbox root (the app/ directory).
        content: full text content to write.

    Returns:
        A short confirmation message.
    """
    full_path = _resolve_in_sandbox(path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


def list_files(path: str = ".") -> list[str]:
    """List files and directories at a given path within the sandbox.

    Args:
        path: path relative to the sandbox root. Defaults to the sandbox
            root itself.

    Returns:
        A sorted list of entry names relative to `path` (directories suffixed
        with "/").
    """
    full_path = _resolve_in_sandbox(path)
    if not full_path.exists():
        raise FileNotFoundError(f"No such directory in sandbox: {path!r}")
    if not full_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {path!r}")

    entries = []
    for entry in sorted(full_path.iterdir()):
        name = entry.name + ("/" if entry.is_dir() else "")
        entries.append(name)
    return entries


# --- Schemas (Gemini function-calling format) ---------------------------

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": (
        "Read the contents of a text file inside the app sandbox directory. "
        "Paths are relative to the sandbox root; absolute paths and paths "
        "that escape the sandbox are rejected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file, e.g. 'main.py'.",
            },
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": (
        "Create or overwrite a text file inside the app sandbox directory. "
        "Creates parent directories as needed. Paths must resolve inside the "
        "sandbox."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file, e.g. 'main.py'.",
            },
            "content": {
                "type": "string",
                "description": "Full text content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
}

LIST_FILES_SCHEMA = {
    "name": "list_files",
    "description": (
        "List files and subdirectories at a given path inside the app "
        "sandbox directory. Directory entries are suffixed with '/'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Relative path to list. Defaults to the sandbox root."
                ),
            },
        },
        "required": [],
    },
}


# --- Dispatcher registry --------------------------------------------------
# Maps tool name -> (callable, schema). The control loop uses this to look up
# and execute whatever tool name the model asks for.

TOOLS = {
    "read_file": (read_file, READ_FILE_SCHEMA),
    "write_file": (write_file, WRITE_FILE_SCHEMA),
    "list_files": (list_files, LIST_FILES_SCHEMA),
}
