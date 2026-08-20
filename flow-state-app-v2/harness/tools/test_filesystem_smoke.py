"""
Standalone smoke test for the filesystem tools, with an emphasis on proving
the sandbox boundary actually holds — this is the part that matters most,
since a bug here means the agent could write outside app/.

Run directly (this needs to be run as a module so package-relative imports
resolve, matching how the other harness tests are run):
    .venv/bin/python -m harness.tools.test_filesystem_smoke
"""

from harness.tools.filesystem import (
    SANDBOX_ROOT,
    SandboxViolation,
    list_files,
    read_file,
    write_file,
)


def main():
    print("Sandbox root:", SANDBOX_ROOT)
    assert SANDBOX_ROOT.name == "app"

    print("\n--- Test 1: write then read a file ---")
    msg = write_file("hello.txt", "hello from the harness\n")
    print(msg)
    content = read_file("hello.txt")
    print("read back:", repr(content))
    assert content == "hello from the harness\n"

    print("\n--- Test 2: write creates nested directories ---")
    write_file("nested/dir/file.txt", "nested content")
    content = read_file("nested/dir/file.txt")
    assert content == "nested content"
    print("nested write/read OK")

    print("\n--- Test 3: list_files ---")
    entries = list_files(".")
    print("entries:", entries)
    assert "hello.txt" in entries
    assert "nested/" in entries

    print("\n--- Test 4: reject absolute paths ---")
    try:
        read_file("/etc/passwd")
        raise AssertionError("Should have rejected absolute path!")
    except SandboxViolation as e:
        print("correctly rejected:", e)

    print("\n--- Test 5: reject path traversal out of sandbox ---")
    try:
        read_file("../../../etc/passwd")
        raise AssertionError("Should have rejected traversal!")
    except SandboxViolation as e:
        print("correctly rejected:", e)

    print("\n--- Test 6: reject traversal even via a subdirectory ---")
    try:
        write_file("nested/../../outside.txt", "should not be written")
        raise AssertionError("Should have rejected nested traversal!")
    except SandboxViolation as e:
        print("correctly rejected:", e)

    # Confirm nothing leaked outside despite the attempt above.
    leaked_path = SANDBOX_ROOT.parent / "outside.txt"
    assert not leaked_path.exists(), "Sandbox breach: file escaped app/!"
    print("confirmed: no file escaped the sandbox")

    print("\nAll filesystem tool smoke checks passed.")


if __name__ == "__main__":
    main()
