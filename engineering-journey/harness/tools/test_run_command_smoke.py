"""
Standalone smoke test for the run_command tool.

Run from repo root:
    .venv/bin/python -m harness.tools.test_run_command_smoke
"""

from harness.tools.filesystem import write_file
from harness.tools.run_command import run_command


def main():
    print("--- Test 1: basic command runs and captures stdout ---")
    output = run_command("echo hello from sandbox")
    print(output)
    assert "exit_code: 0" in output
    assert "hello from sandbox" in output

    print("\n--- Test 2: command runs with cwd locked to the sandbox ---")
    output = run_command("pwd")
    print(output)
    assert "app" in output  # cwd should end in .../app

    print("\n--- Test 3: python resolves to the harness's own venv ---")
    output = run_command("python -c \"import sys; print('python OK', sys.version)\"")
    print(output)
    assert "python OK" in output, (
        "Expected python to resolve correctly (see _HARNESS_VENV_BIN in "
        "run_command.py). Once your project has installed real "
        "dependencies into .venv, consider replacing this with an assert "
        "on one of those imports instead (e.g. `import <your main "
        "framework>`) for a stronger, project-specific signal."
    )

    print("\n--- Test 4: nonzero exit code is captured, not raised ---")
    output = run_command("exit 7")
    print(output)
    assert "exit_code: 7" in output

    print("\n--- Test 5: stderr is captured separately from stdout ---")
    output = run_command("echo to_stdout; echo to_stderr >&2")
    print(output)
    assert "to_stdout" in output
    assert "to_stderr" in output

    print("\n--- Test 6: real-world use case — syntax-check a written file ---")
    write_file("syntax_check_me.py", "def f():\n    return 1\n")
    output = run_command("python -m py_compile syntax_check_me.py")
    print(output)
    assert "exit_code: 0" in output

    write_file("broken_syntax.py", "def f(:\n    return 1\n")
    output = run_command("python -m py_compile broken_syntax.py")
    print(output)
    assert "exit_code: 0" not in output, "Expected a nonzero exit for broken syntax"

    print("\n--- Test 7: timeout is enforced ---")
    output = run_command("sleep 5", timeout_seconds=1)
    print(output)
    assert "TIMED OUT" in output

    print("\nAll run_command smoke checks passed.")


if __name__ == "__main__":
    main()
