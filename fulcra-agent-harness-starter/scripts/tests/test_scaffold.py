"""
Tests for scripts/scaffold.py — the core of this starter kit.

These are real, runnable tests (per the same testing philosophy this
starter kit asks scaffolded projects to follow): they invoke the actual
scaffold() logic against real fake rapid-prototype artifacts on disk and
assert on the real files it produces, not on mocked-out internals.

Run with:
    python -m pytest scripts/tests/
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
SCAFFOLD_SCRIPT = SCRIPT_DIR / "scaffold.py"

# Import the module directly (rather than only shelling out to the CLI) so
# unit-level tests (hydrate, slugify, extract_first_plan_milestone) can
# exercise internals directly, while a couple of integration-style tests
# still shell out to prove the actual CLI entry point works end-to-end.
sys.path.insert(0, str(SCRIPT_DIR))
import scaffold  # noqa: E402


FAKE_BRIEF = (
    "A CLI tool that watches a user's Fulcra calendar events and sends a "
    "daily digest summarizing tomorrow's schedule.\n\n"
    "## Goals\n- Summarize tomorrow's events every evening.\n"
)
FAKE_ARCHITECTURE = (
    "# Architecture\n\nMaps CalendarEvent to a new DailyDigest annotation "
    "type. No gaps identified.\n"
)
FAKE_PLAN = (
    "# Plan\n\n"
    "## Milestone 1: Fetch and print tomorrow's events\n"
    "Write a script that queries CalendarEvent records for the next 24 "
    "hours and prints them to stdout.\n\n"
    "## Milestone 2: Generate and store the digest\n"
    "Summarize the events and record a DailyDigest annotation.\n"
)


@pytest.fixture()
def fake_rapid_prototype_dir(tmp_path: Path) -> Path:
    rp_dir = tmp_path / "rapid_prototype"
    (rp_dir / "intake").mkdir(parents=True)
    (rp_dir / "intake" / "brief.md").write_text(FAKE_BRIEF)
    (rp_dir / "architecture.md").write_text(FAKE_ARCHITECTURE)
    (rp_dir / "plan.md").write_text(FAKE_PLAN)
    return rp_dir


# --- Unit tests for individual helper functions -----------------------


def test_slugify_basic():
    assert scaffold.slugify("Acme Widget Tracker") == "acme-widget-tracker"
    assert scaffold.slugify("  Calendar   Digest!! ") == "calendar-digest"


def test_slugify_rejects_empty_result():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.slugify("!!!")


def test_hydrate_replaces_all_placeholders():
    template = "Hello {{NAME}}, welcome to {{PROJECT}}."
    result = scaffold.hydrate(template, {"NAME": "Ada", "PROJECT": "Acme Widget Tracker"})
    assert result == "Hello Ada, welcome to Acme Widget Tracker."


def test_hydrate_raises_on_missing_value():
    template = "Hello {{NAME}}, {{UNKNOWN_PLACEHOLDER}}."
    with pytest.raises(scaffold.ScaffoldError, match="UNKNOWN_PLACEHOLDER"):
        scaffold.hydrate(template, {"NAME": "Ada"})


def test_extract_first_plan_milestone_skips_document_title():
    title, body = scaffold.extract_first_plan_milestone(FAKE_PLAN)
    assert title == "Milestone 1: Fetch and print tomorrow's events"
    assert "CalendarEvent" in body
    assert "Milestone 2" not in body  # body should stop before the next heading


def test_extract_first_plan_milestone_raises_on_no_headings():
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.extract_first_plan_milestone("just some prose, no headings at all")


def test_read_required_artifact_raises_clear_error_when_missing(tmp_path: Path):
    missing_path = tmp_path / "does_not_exist.md"
    with pytest.raises(scaffold.ScaffoldError, match="Architecture"):
        scaffold.read_required_artifact(missing_path, "Architecture")


def test_read_required_artifact_raises_on_empty_file(tmp_path: Path):
    empty_path = tmp_path / "empty.md"
    empty_path.write_text("   \n  ")
    with pytest.raises(scaffold.ScaffoldError):
        scaffold.read_required_artifact(empty_path, "Intake")


# --- Integration tests: run the real CLI end-to-end ---------------------


def test_dry_run_writes_nothing(fake_rapid_prototype_dir: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_dir),
            "--output-dir", str(output_dir),
            "--dry-run",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "would write" in result.stdout or "would copy" in result.stdout
    assert not output_dir.exists() or not any(output_dir.iterdir())


def test_real_run_produces_expected_files(fake_rapid_prototype_dir: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_dir),
            "--output-dir", str(output_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    # Engine files copied verbatim.
    assert (output_dir / "harness" / "loop.py").is_file()
    assert (output_dir / "harness" / "tools" / "filesystem.py").is_file()
    assert (output_dir / "harness" / "providers" / "gemini.py").is_file()

    # Hydrated files exist and contain the project name, not a
    # placeholder token.
    system_prompt = (output_dir / "harness" / "prompts" / "system_prompt.md").read_text()
    assert "Calendar Digest" in system_prompt
    assert "{{" not in system_prompt

    context = (output_dir / "app" / "CONTEXT.md").read_text()
    assert "Calendar Digest" in context
    assert "{{" not in context

    standards = (output_dir / "app" / "ENGINEERING_STANDARDS.md").read_text()
    assert "{{" not in standards

    # First task prompt generated from plan.md's first milestone.
    task_files = list((output_dir / "harness" / "prompts").glob("task_001_*.md"))
    assert len(task_files) == 1
    task_content = task_files[0].read_text()
    assert "CalendarEvent" in task_content
    assert "{{" not in task_content

    # Rapid-prototype artifacts copied into the new repo for provenance.
    assert (output_dir / "architecture.md").is_file()
    assert (output_dir / "plan.md").is_file()
    assert (output_dir / "intake" / "brief.md").is_file()

    # Top-level project files.
    assert (output_dir / "README.md").is_file()
    assert (output_dir / "pyproject.toml").is_file()
    assert (output_dir / ".gitignore").is_file()
    assert (output_dir / ".env.example").is_file()


def test_refuses_to_overwrite_existing_nonempty_output_dir(
    fake_rapid_prototype_dir: Path, tmp_path: Path
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "existing_file.txt").write_text("don't touch me")

    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_dir),
            "--output-dir", str(output_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr
    # Confirm nothing was touched.
    assert (output_dir / "existing_file.txt").read_text() == "don't touch me"
    assert not (output_dir / "harness").exists()


def test_fails_clearly_when_architecture_missing(tmp_path: Path):
    rp_dir = tmp_path / "incomplete_rapid_prototype"
    (rp_dir / "intake").mkdir(parents=True)
    (rp_dir / "intake" / "brief.md").write_text(FAKE_BRIEF)
    # architecture.md and plan.md deliberately NOT created.

    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(rp_dir),
            "--output-dir", str(output_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "architecture.md" in result.stderr
    assert "Architecture" in result.stderr
