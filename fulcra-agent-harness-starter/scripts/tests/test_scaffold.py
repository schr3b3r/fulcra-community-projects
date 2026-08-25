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
    "# Intake Brief: Calendar Digest\n\n"
    "A CLI tool that watches a user's Fulcra calendar events and sends a "
    "daily digest summarizing tomorrow's schedule.\n\n"
    "## Goals\n- Summarize tomorrow's events every evening.\n"
)
FAKE_ARCHITECTURE = (
    "# Architecture: Calendar Digest\n\n"
    "## Summary\n"
    "Maps CalendarEvent to a new DailyDigest annotation type. No gaps identified.\n"
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


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture()
def fake_rapid_prototype_git_repo(tmp_path: Path) -> Path:
    """Like fake_rapid_prototype_dir, but a REAL git repo with one commit
    per fulcra-prototype-grill-me phase -- mirrors what that skill actually
    produces, so history-preservation tests exercise real git history,
    not just files that happen to be JSON/text-identical to it."""
    rp_dir = tmp_path / "rapid_prototype_git"
    rp_dir.mkdir()
    _git("init", "-q", cwd=rp_dir)
    _git("config", "user.email", "test@example.com", cwd=rp_dir)
    _git("config", "user.name", "Test User", cwd=rp_dir)

    (rp_dir / "intake").mkdir()
    (rp_dir / "intake" / "brief.md").write_text(FAKE_BRIEF)
    _git("add", "-A", cwd=rp_dir)
    _git("commit", "-q", "-m", "Intake: initial brief", cwd=rp_dir)

    (rp_dir / "architecture.md").write_text(FAKE_ARCHITECTURE)
    _git("add", "-A", cwd=rp_dir)
    _git("commit", "-q", "-m", "Architecture: approved by user", cwd=rp_dir)

    (rp_dir / "plan.md").write_text(FAKE_PLAN)
    _git("add", "-A", cwd=rp_dir)
    _git("commit", "-q", "-m", "Plan: define milestones", cwd=rp_dir)

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


def test_is_git_working_tree_true_for_real_repo(fake_rapid_prototype_git_repo: Path):
    assert scaffold.is_git_working_tree(fake_rapid_prototype_git_repo) is True


def test_is_git_working_tree_false_for_plain_directory(fake_rapid_prototype_dir: Path):
    assert scaffold.is_git_working_tree(fake_rapid_prototype_dir) is False


def test_is_git_working_tree_false_for_nonexistent_path(tmp_path: Path):
    assert scaffold.is_git_working_tree(tmp_path / "does_not_exist") is False


def test_extract_brief_description_skips_leading_heading():
    """Regression test for a real bug found using this script on a real
    project: a brief.md starting with '# Intake Brief: <name>' (the
    literal fulcra-prototype-grill-me convention) before any real prose
    previously produced a PROJECT_DESCRIPTION that was just the heading
    text itself, since the old logic took 'the first \\n\\n-delimited
    block' without skipping the heading line first."""
    brief = (
        "# Intake Brief: Engineering Journey\n\n"
        "A tool that summarizes a developer's GitHub activity into a "
        "readable retrospective.\n\n"
        "## Goals\n- Show the journey over time.\n"
    )
    description = scaffold.extract_brief_description(brief)
    assert description == (
        "A tool that summarizes a developer's GitHub activity into a "
        "readable retrospective."
    )
    assert "Intake Brief" not in description


def test_extract_brief_description_no_heading_at_all():
    brief = "Just a plain first paragraph with no heading.\n\nMore text."
    assert scaffold.extract_brief_description(brief) == (
        "Just a plain first paragraph with no heading."
    )


def test_extract_brief_description_truncates_long_paragraph_at_word_boundary():
    long_paragraph = "word " * 200  # ~1000 chars, well over the 500 cutoff
    description = scaffold.extract_brief_description(long_paragraph.strip())
    assert len(description) <= 504  # 500 + "..." plus a little slack
    assert description.endswith("...")
    # Must not have cut off mid-word -- every "word" in the truncated
    # portion (before the ellipsis) should be a complete, real "word".
    body = description[:-3].strip()
    assert all(token == "word" for token in body.split())


def test_extract_brief_description_degenerate_heading_only_input():
    """A brief that's ONLY a heading (no real prose at all) shouldn't
    produce an empty description -- fall back to the raw text rather
    than returning nothing."""
    brief = "# Intake Brief: Nothing Else Here"
    description = scaffold.extract_brief_description(brief)
    assert description != ""


def test_extract_architecture_summary_pulls_summary_section_only():
    """Regression test for a real bug: ARCHITECTURE_SUMMARY previously
    embedded the ENTIRE architecture.md verbatim into CONTEXT.md, making
    it unwieldy for any non-trivial architecture doc and duplicating
    content already present in the separately-copied architecture.md
    file. This should extract just the '## Summary' section."""
    architecture = (
        "# Architecture: Engineering Journey\n\n"
        "## Summary\n"
        "A tool that backfills GitHub activity and generates a narrative.\n\n"
        "## Capability map\n"
        "Lots of detail here that should NOT appear in the short summary, "
        "including a very long capability breakdown that goes on for a "
        "while and would make CONTEXT.md unwieldy if embedded in full.\n"
    )
    summary = scaffold.extract_architecture_summary(architecture)
    assert "A tool that backfills GitHub activity" in summary
    assert "Capability map" not in summary
    assert "unwieldy" not in summary  # from the (excluded) Capability map section


def test_extract_architecture_summary_falls_back_without_summary_heading():
    """If architecture.md doesn't follow the '## Summary' convention,
    fall back to a short excerpt rather than either erroring or
    embedding the whole document."""
    architecture = (
        "# Architecture: Something\n\n"
        "This project maps X to Y with no gaps.\n\n"
        "## Some Other Section\nMore detail.\n"
    )
    summary = scaffold.extract_architecture_summary(architecture)
    assert summary == "This project maps X to Y with no gaps."


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

    # app/fulcra_client.py: copied verbatim (real, working, project-
    # agnostic code, not a template needing per-project hydration) --
    # regression coverage for a real failure mode where a fresh agent
    # with no credential-loading helper burned its entire task iteration
    # budget rediscovering the correct FulcraCredentials/FulcraAPI wiring
    # from scratch and never got to write any real feature code.
    fulcra_client = output_dir / "app" / "fulcra_client.py"
    assert fulcra_client.is_file()
    fulcra_client_source = fulcra_client.read_text()
    assert "{{" not in fulcra_client_source
    assert "def get_fulcra_client(" in fulcra_client_source
    assert "FulcraCredentials.from_json" in fulcra_client_source

    # Hydrated files exist and contain the project name, not a
    # placeholder token.
    system_prompt = (output_dir / "harness" / "prompts" / "system_prompt.md").read_text()
    assert "Calendar Digest" in system_prompt
    assert "{{" not in system_prompt

    context = (output_dir / "app" / "CONTEXT.md").read_text()
    assert "Calendar Digest" in context
    assert "{{" not in context
    # Regression checks for two real bugs found scaffolding a real
    # project: (1) PROJECT_DESCRIPTION must not be just the brief's own
    # leading heading text; (2) ARCHITECTURE_SUMMARY must not embed the
    # ENTIRE architecture.md verbatim (making CONTEXT.md unwieldy and
    # duplicating the separately-copied architecture.md file) -- see
    # test_extract_brief_description_* and
    # test_extract_architecture_summary_* for focused unit coverage of
    # both fixes; this just confirms the real CLI path doesn't regress
    # to leaking the raw heading text into the hydrated CONTEXT.md.
    assert "# Intake Brief" not in context
    assert "# Architecture:" not in context

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


# --- Integration tests: git history preservation -------------------------


def test_history_auto_preserves_real_phase_commits(
    fake_rapid_prototype_git_repo: Path, tmp_path: Path
):
    """--history=auto (the default) should detect that the
    rapid-prototype dir is a real git repo and preserve its full commit
    history in the new project, rather than flattening it -- this is the
    whole point of the feature: a future session can `git log` the new
    project and see the real Intake/Architecture/Plan phase commits, not
    just their content copied into a single scaffold commit."""
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_git_repo),
            "--output-dir", str(output_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Preserving fulcra-prototype-grill-me git history" in result.stdout

    log = _git("log", "--format=%s", cwd=output_dir).stdout
    assert "Intake: initial brief" in log
    assert "Architecture: approved by user" in log
    assert "Plan: define milestones" in log

    # The rapid-prototype artifacts should be present via the cloned
    # history, not re-copied as a separate step (no "Copying
    # fulcra-prototype-grill-me artifacts" message for this path).
    assert "Copying fulcra-prototype-grill-me artifacts" not in result.stdout
    assert (output_dir / "architecture.md").is_file()
    assert (output_dir / "plan.md").is_file()

    # The cloned repo's "origin" remote (pointing at a throwaway local
    # tmp_path that won't exist later) must be removed.
    remotes = _git("remote", cwd=output_dir).stdout.strip()
    assert remotes == ""

    # Scaffolded files land as new, uncommitted content on top of the
    # preserved history -- the user commits them themselves (see the
    # printed "Next steps").
    status = _git("status", "--short", cwd=output_dir).stdout
    assert "harness/" in status or "?? harness" in status


def test_history_preserve_fails_clearly_on_non_git_source(
    fake_rapid_prototype_dir: Path, tmp_path: Path
):
    """--history=preserve must fail loudly (not silently fall back to
    copy) when the source isn't actually a git repo -- silently
    downgrading would defeat the purpose of explicitly requesting
    preservation."""
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_dir),
            "--output-dir", str(output_dir),
            "--history", "preserve",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not a git working tree" in result.stderr
    assert not output_dir.exists()


def test_history_copy_flattens_even_when_source_is_a_git_repo(
    fake_rapid_prototype_git_repo: Path, tmp_path: Path
):
    """--history=copy should force the flattened (single scaffold
    commit, artifacts copied as plain content) behavior even when the
    source IS a real git repo whose history could have been preserved --
    this is an explicit user override, not just a fallback."""
    output_dir = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_git_repo),
            "--output-dir", str(output_dir),
            "--history", "copy",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Preserving fulcra-prototype-grill-me git history" not in result.stdout
    assert "Copying fulcra-prototype-grill-me artifacts" in result.stdout
    # No git repo should have been created at all by this script -- git
    # init is a step the user runs themselves afterward (see the printed
    # "Next steps"), same as in the always-plain-directory case.
    assert not scaffold.is_git_working_tree(output_dir)
    assert (output_dir / "architecture.md").is_file()


def test_history_preserve_refuses_existing_output_dir(
    fake_rapid_prototype_git_repo: Path, tmp_path: Path
):
    """Preserving history clones into --output-dir, which requires the
    path to not exist at all yet (git clone's own constraint) -- this
    should be a clear, specific error, not git's own possibly-confusing
    message."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()  # exists, even though empty

    result = subprocess.run(
        [
            sys.executable, str(SCAFFOLD_SCRIPT),
            "--project-name", "Calendar Digest",
            "--rapid-prototype-dir", str(fake_rapid_prototype_git_repo),
            "--output-dir", str(output_dir),
            "--history", "preserve",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr


def test_history_auto_falls_back_to_copy_for_non_git_source(
    fake_rapid_prototype_dir: Path, tmp_path: Path
):
    """--history=auto (default) should behave exactly like --history=copy
    when the source isn't a git repo -- this is the pre-existing behavior
    from before history preservation was added, and must not regress."""
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
    assert "Preserving fulcra-prototype-grill-me git history" not in result.stdout
    assert "Copying fulcra-prototype-grill-me artifacts" in result.stdout
    assert (output_dir / "architecture.md").is_file()
