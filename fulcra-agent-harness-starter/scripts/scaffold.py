#!/usr/bin/env python3
"""
scaffold.py — turns fulcra-prototype-grill-me artifacts into a real,
ready-to-run agent harness + app skeleton for a new project.

WHAT THIS SCRIPT ASSUMES ALREADY EXISTS (read these before running):
    - intake/brief.md        (fulcra-prototype-grill-me: Intake phase)
    - architecture.md        (fulcra-prototype-grill-me: Architecture phase,
                               approved by the user — this is a gate in
                               that skill, don't skip it)
    - plan.md                (fulcra-prototype-grill-me: Plan phase)
If any of these don't exist yet, STOP and run those phases of
fulcra-prototype-grill-me first — this script does not gather requirements,
it only turns already-gathered requirements into a running harness.

WHAT THIS SCRIPT PRODUCES, inside --output-dir (a NEW directory, sibling
to this starter kit, not inside it):
    harness/                 — copied verbatim from engine/ (this starter
                                kit's project-agnostic agent loop, tools,
                                and provider adapter)
      prompts/
        system_prompt.md     — hydrated from templates/system_prompt.md.template
        task_001_<slug>.md   — hydrated from templates/task.md.template,
                                using the FIRST milestone in plan.md
    app/
      CONTEXT.md             — hydrated from templates/app/CONTEXT.md.template
      ENGINEERING_STANDARDS.md — hydrated from templates/app/ENGINEERING_STANDARDS.md.template
      fulcra_client.py       — copied verbatim (real, working credential-
                                loading helper, not a template -- see the
                                file's own docstring for why this exists
                                as a starter-kit file rather than
                                something each project's agent writes
                                itself from scratch)
      features/
        INDEX.md             — hydrated from templates/app/features/INDEX.md.template
        _TEMPLATE.md          — copied verbatim (per-feature file skeleton)
    README.md                 — hydrated from templates/README.md.template
    pyproject.toml            — hydrated from templates/pyproject.toml.template
    .gitignore                — copied verbatim from templates/.gitignore.template
    .env.example              — copied verbatim from templates/.env.example.template

GIT HISTORY: fulcra-prototype-grill-me tracks each phase (Intake, Interview,
Architecture, Plan) as a real commit in its own repo. By default
(--history=auto) this script PRESERVES that history: if
--rapid-prototype-dir is itself a git working tree, the new project is
created by cloning it (so every phase commit becomes real history in the
new repo), then harness/ and app/ are added on top as one new commit.
If --rapid-prototype-dir is NOT a git repo (e.g. plain files, or a
not-yet-unpacked .bundle -- unpack it first with
`git clone <bundle> <dir>`, per fulcra-prototype-grill-me's own "Resuming a
Project" instructions), this script falls back to --history=copy: a
fresh repo is initialized and the artifact files are copied in as plain
content in a single "Initial scaffold" commit, with no phase-by-phase
history. Force either behavior explicitly with --history=preserve or
--history=copy; preserve will error out clearly if the source isn't a
real git working tree rather than silently falling back.

CAVEAT when --history=preserve/auto-preserving: this script writes
harness/, app/, README.md, pyproject.toml, .gitignore, and .env.example
directly into the cloned repo, OVERWRITING any same-named files that
happen to already exist there without asking. This is a non-issue for a
typical fulcra-prototype-grill-me repo (it produces intake/, interview/,
architecture.md, plan.md — none of which collide with what this script
writes), but if your rapid-prototype repo happens to already have its own
README.md, .gitignore, etc. at the root, review `git diff` after
scaffolding before committing, since those would be silently replaced.

Usage:
    python scripts/scaffold.py \\
        --project-name "Acme Widget Tracker" \\
        --rapid-prototype-dir /path/to/rapid-prototype-artifacts \\
        --output-dir /path/to/new-project-repo

Run with --dry-run first to see what would be written without touching
disk — recommended before the real run, especially the first few times
you use this script.

TEMPLATING MECHANISM: plain Python str.replace() on {{PLACEHOLDER}}
tokens. Deliberately NOT Jinja2 or any templating library/framework — the
whole point of this starter kit is to stay as simple and inspectable as
the harness it produces. If you need conditionals or loops in a template,
that's a signal to either hand-edit the generated file afterward (this is
expected and normal — see README.md.template's own advice) or extend this
script with a small, explicit Python function, not to reach for a
templating engine.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

STARTER_KIT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = STARTER_KIT_ROOT / "engine"
TEMPLATES_DIR = STARTER_KIT_ROOT / "templates"


class ScaffoldError(Exception):
    """Raised when scaffolding cannot proceed (missing prerequisite
    artifact, invalid arguments, etc.) — always with a message explaining
    exactly what's missing and what to do about it."""


def is_git_working_tree(path: Path) -> bool:
    """Whether `path` is (the root of) a real, checked-out git working
    tree — used to decide whether history-preserving scaffolding
    (--history=preserve/auto) is possible.

    Deliberately does NOT understand raw .bundle files directly (per
    fulcra-prototype-grill-me's own "Resuming a Project" instructions, a
    downloaded bundle is meant to be unpacked with
    `git clone <bundle> <dir>` before being resumed from) — keeping this
    script's git handling to "clone a working tree" only, rather than
    also parsing bundle files itself, keeps this one script simple and
    inspectable rather than duplicating fulcra-prototype-grill-me's own
    resume mechanism.
    """
    if not path.is_dir():
        return False
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def clone_with_history(source: Path, dest: Path, dry_run: bool) -> None:
    """Clone `source`'s full git history into `dest`, so every
    fulcra-prototype-grill-me phase commit (Intake, Interview, Architecture,
    Plan) becomes real, inspectable git history in the new project —
    rather than flattening that work into a single "Initial scaffold"
    commit with the artifact files copied in as plain content (which is
    what --history=copy does instead).

    Raises:
        ScaffoldError: if the clone itself fails (e.g. `source` turned
            out not to be a valid git repo after all).
    """
    print(
        f"  {'[dry-run] would' if dry_run else ''} git clone (preserving "
        f"full rapid-prototype history): {source} -> {dest}"
    )
    if dry_run:
        return

    result = subprocess.run(
        ["git", "clone", str(source), str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ScaffoldError(f"git clone failed: {result.stderr.strip()}")

    # The cloned repo's "origin" remote points at the rapid-prototype
    # directory's local filesystem path -- meaningless anywhere else, and
    # likely to stop existing once that scratch directory is cleaned up.
    # Remove it so nothing later accidentally tries to push/pull from it;
    # the user adds their own real remote (e.g. a fresh GitHub repo) once
    # they're ready to publish this project.
    subprocess.run(
        ["git", "remote", "remove", "origin"],
        cwd=dest,
        capture_output=True,
        text=True,
    )


def read_required_artifact(path: Path, phase_name: str) -> str:
    """Read a required fulcra-prototype-grill-me artifact file, failing with
    a clear, actionable error if it doesn't exist yet — rather than
    silently proceeding with empty/placeholder content, which would
    produce a harness that looks scaffolded but is missing the actual
    project understanding that phase was supposed to capture."""
    if not path.is_file():
        raise ScaffoldError(
            f"Missing required artifact: {path}\n"
            f"This should have been produced by fulcra-prototype-grill-me's "
            f"{phase_name} phase. Run that phase (and get it approved, if "
            f"it has a user gate) before running this script."
        )
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ScaffoldError(f"Artifact exists but is empty: {path}")
    return content


def extract_first_plan_milestone(plan_md: str) -> tuple[str, str]:
    """Pull the first actionable milestone out of plan.md for hydrating
    the first task prompt.

    fulcra-prototype-grill-me's plan.md format is prose/markdown, not a
    strict machine-readable schema, so this is intentionally a
    best-effort heuristic (first level-2 or level-3 heading, plus the
    paragraph(s) under it) rather than a strict parser. It is expected
    that whoever runs this script will read the generated task file
    afterward and correct/expand it by hand if the heuristic picked a
    poor starting point — this saves you from writing the first task
    prompt entirely from scratch, it doesn't need to be perfect.

    Returns:
        (title, body) — title is the heading text, body is everything
        until the next heading of the same or higher level.
    """
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(plan_md))

    if not headings:
        raise ScaffoldError(
            "plan.md has no markdown headings to extract a first milestone "
            "from. Add at least one heading (e.g. '## Milestone 1: ...') "
            "describing the first concrete piece of work, or write "
            "harness/prompts/task_001_*.md by hand instead of relying on "
            "this script to generate it."
        )

    # Skip a top-level "# Plan" title if present; look for the first
    # heading that reads like an actual milestone/spike, not the doc title.
    for i, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        if level == 1 and i == 0 and len(headings) > 1:
            continue  # likely just the document's own top-level title
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(plan_md)
        body = plan_md[start:end].strip()
        return title, body

    # Only one heading total and it was a level-1 -- use it anyway.
    title = headings[0].group(2).strip()
    body = plan_md[headings[0].end():].strip()
    return title, body


def extract_brief_description(brief_md: str) -> str:
    """Derive a one-paragraph project description from intake/brief.md,
    for hydrating PROJECT_DESCRIPTION.

    fulcra-prototype-grill-me's Intake template typically starts brief.md
    with a markdown heading (e.g. "# Intake Brief: <name>") before the
    actual summary prose. Naively taking "the first \\n\\n-delimited
    block" without skipping that heading previously produced a
    PROJECT_DESCRIPTION that was just the heading text itself (a few
    words), which then caused a second bug downstream: because that
    "description" was so short, later string-concatenation logic that
    assumed a substantial description ended up looking broken. This
    function skips any leading '#'-prefixed heading lines before taking
    the first real paragraph.

    Falls back to a whole-brief excerpt (truncated at a word boundary,
    not a blind character slice that could cut mid-word) if the first
    real paragraph is implausibly long (e.g. the brief has no blank-line
    paragraph breaks at all).
    """
    lines = brief_md.strip().splitlines()
    # Skip leading heading lines (and any blank lines directly after
    # them) to find where the real prose starts.
    start_idx = 0
    while start_idx < len(lines) and (
        lines[start_idx].strip() == "" or lines[start_idx].lstrip().startswith("#")
    ):
        start_idx += 1
    remaining = "\n".join(lines[start_idx:]).strip()

    if not remaining:
        # The whole brief was headings/blank lines (degenerate input) --
        # fall back to the raw brief text rather than returning an empty
        # description.
        remaining = brief_md.strip()

    first_paragraph = remaining.split("\n\n", 1)[0].strip()

    if len(first_paragraph) <= 500:
        return first_paragraph

    # Too long -- truncate at the last word boundary before 500 chars
    # rather than cutting mid-word.
    truncated = first_paragraph[:500]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "..."


def extract_architecture_summary(architecture_md: str) -> str:
    """Derive a short architecture summary for CONTEXT.md's "The Product"
    section, rather than embedding the FULL architecture.md verbatim.

    architecture.md is already copied into the new project's repo root
    (via history preservation or the plain-copy fallback), so duplicating
    its entire contents inside CONTEXT.md too is pure redundancy --
    previously this made CONTEXT.md unwieldy for any project whose real
    architecture doc was more than a paragraph or two (which is the
    common case for anything non-trivial).

    Looks for a "## Summary" section (the convention this starter kit's
    own architecture.md.template-adjacent docs use) and returns just
    that section's text. Falls back to the first paragraph of the whole
    document if no such section exists, so this still produces something
    reasonable for an architecture.md that doesn't follow that exact
    convention.
    """
    summary_heading_pattern = re.compile(
        r"^#{1,3}\s+Summary\s*$", re.MULTILINE | re.IGNORECASE
    )
    match = summary_heading_pattern.search(architecture_md)
    if match is None:
        # No "## Summary" section -- fall back to the first real
        # paragraph of the document (reusing the same heading-skipping
        # logic as extract_brief_description, since architecture.md
        # typically starts with its own "# Architecture: <name>" title).
        return extract_brief_description(architecture_md)

    start = match.end()
    next_heading_pattern = re.compile(r"^#{1,3}\s+\S", re.MULTILINE)
    next_match = next_heading_pattern.search(architecture_md, start)
    end = next_match.start() if next_match else len(architecture_md)
    return architecture_md[start:end].strip()


def slugify(text: str) -> str:
    """Turn a project name into a filesystem/package-safe slug, e.g.
    'Acme Widget Tracker' -> 'acme-widget-tracker'. Deliberately simple
    (no unicode normalization) since project names are expected to be
    plain ASCII."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    if not slug:
        raise ScaffoldError(f"Could not derive a usable slug from {text!r}")
    return slug


def hydrate(template_text: str, values: dict[str, str]) -> str:
    """Replace every {{KEY}} placeholder in template_text with values[KEY].

    Raises ScaffoldError if the template references a placeholder that
    isn't in `values` — better to fail loudly at scaffold time than to
    silently ship a generated file with a literal "{{SOMETHING}}" still
    in it that nobody notices until much later.
    """
    remaining = set(re.findall(r"\{\{([A-Z_]+)\}\}", template_text))
    missing = remaining - set(values.keys())
    if missing:
        raise ScaffoldError(
            f"Template references placeholder(s) with no supplied value: "
            f"{sorted(missing)}. Add them to the `values` dict in "
            f"scaffold.py's main()."
        )

    result = template_text
    for key, value in values.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def write_file(path: Path, content: str, dry_run: bool) -> None:
    print(f"  {'[dry-run] would write' if dry_run else 'writing'}: {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_tree(src: Path, dst: Path, dry_run: bool) -> None:
    """Copy a directory tree verbatim (used for engine/ -> harness/, since
    that content is 100% project-agnostic and needs no hydration)."""
    for src_file in sorted(src.rglob("*")):
        if src_file.is_dir():
            continue
        if "__pycache__" in src_file.parts:
            continue
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        print(f"  {'[dry-run] would copy' if dry_run else 'copying'}: "
              f"{src_file.relative_to(STARTER_KIT_ROOT)} -> {dst_file}")
        if dry_run:
            continue
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--project-name", required=True,
        help="Human-readable project name, e.g. 'Acme Widget Tracker'.",
    )
    parser.add_argument(
        "--rapid-prototype-dir", required=True, type=Path,
        help=(
            "Directory containing intake/brief.md, architecture.md, and "
            "plan.md (the fulcra-prototype-grill-me artifacts for this "
            "project)."
        ),
    )
    parser.add_argument(
        "--output-dir", required=True, type=Path,
        help=(
            "Where to write the new harness/ + app/ skeleton. Must not "
            "already exist (this script refuses to overwrite an existing "
            "directory, to avoid accidentally clobbering real work)."
        ),
    )
    parser.add_argument(
        "--domain-library-guidance", default="",
        help=(
            "Optional: a markdown bullet list (as a single string, one "
            "bullet per line) describing which established libraries this "
            "project should prefer for its actual domain — e.g. audio/DSP, "
            "web framework, etc. Left blank, ENGINEERING_STANDARDS.md will "
            "have a placeholder reminding you to fill this in by hand. "
            "Do NOT include your own 'Fulcra integration' bullet here -- "
            "the generated ENGINEERING_STANDARDS.md.template already has "
            "one immediately after this guidance is inserted; duplicating "
            "it produces two conflicting bullets back to back."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching disk.",
    )
    parser.add_argument(
        "--history", choices=["auto", "preserve", "copy"], default="auto",
        help=(
            "How to handle fulcra-prototype-grill-me's git history. "
            "'auto' (default): preserve it if --rapid-prototype-dir is a "
            "git working tree, otherwise fall back to 'copy'. 'preserve': "
            "require history preservation, erroring out if "
            "--rapid-prototype-dir isn't a real git repo (e.g. an "
            "unpacked .bundle). 'copy': always flatten to a single "
            "'Initial scaffold' commit with artifact files copied in as "
            "plain content, even if history preservation would be "
            "possible."
        ),
    )
    args = parser.parse_args()

    # Resolve --history=auto to a concrete mode up front, so the rest of
    # this function only ever has to handle the two real cases.
    rapid_prototype_is_git_repo = is_git_working_tree(args.rapid_prototype_dir)
    if args.history == "preserve" and not rapid_prototype_is_git_repo:
        print(
            f"ERROR: --history=preserve was requested, but "
            f"{args.rapid_prototype_dir} is not a git working tree "
            f"(no history to preserve). If you have a fulcra-rapid-"
            f"prototype .bundle backup instead of a live checkout, unpack "
            f"it first with `git clone <bundle> <dir>` (see that skill's "
            f"own 'Resuming a Project' instructions), then point "
            f"--rapid-prototype-dir at the unpacked directory. Otherwise, "
            f"use --history=copy (or --history=auto) to proceed without "
            f"phase-by-phase history.",
            file=sys.stderr,
        )
        return 1
    preserve_history = args.history == "preserve" or (
        args.history == "auto" and rapid_prototype_is_git_repo
    )

    if preserve_history:
        # git clone itself refuses to clone into an existing non-empty
        # directory (and will even refuse an existing EMPTY directory in
        # some git versions) -- so for this mode --output-dir must not
        # exist at all yet, not just be empty. Check explicitly for a
        # clearer error than whatever git's own message would say.
        if args.output_dir.exists():
            print(
                f"ERROR: --output-dir {args.output_dir} already exists. "
                f"History-preserving scaffolding (--history=preserve/auto) "
                f"clones into --output-dir, which requires the path to not "
                f"exist yet at all (not even as an empty directory). "
                f"Choose a new path, or pass --history=copy if you want to "
                f"scaffold into an existing empty directory instead.",
                file=sys.stderr,
            )
            return 1
    elif args.output_dir.exists() and any(args.output_dir.iterdir()):
        print(
            f"ERROR: --output-dir {args.output_dir} already exists and is "
            f"non-empty. Refusing to scaffold into it (this script never "
            f"overwrites existing work). Choose a new directory.",
            file=sys.stderr,
        )
        return 1

    try:
        brief = read_required_artifact(
            args.rapid_prototype_dir / "intake" / "brief.md", "Intake"
        )
        architecture = read_required_artifact(
            args.rapid_prototype_dir / "architecture.md", "Architecture"
        )
        plan = read_required_artifact(
            args.rapid_prototype_dir / "plan.md", "Plan"
        )
    except ScaffoldError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    project_name = args.project_name
    project_slug = slugify(project_name)

    # Derive a one-paragraph description from the brief (its first real
    # paragraph is expected to be a short summary per fulcra-rapid-
    # prototype's Intake template) -- fall back to a truncated version of
    # the whole brief if that paragraph is too long.
    project_description = extract_brief_description(brief)

    try:
        task_title, task_body = extract_first_plan_milestone(plan)
    except ScaffoldError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    domain_library_guidance = args.domain_library_guidance or (
        "- (TODO: fill this in by hand based on your actual project's "
        "domain -- e.g. for audio/DSP: `librosa`, `scipy`, `numpy`; for a "
        "web backend: pick one framework and don't introduce a competing "
        "one without a real reason.)"
    )

    values = {
        "PROJECT_NAME": project_name,
        "PROJECT_SLUG": project_slug,
        "PROJECT_DESCRIPTION": project_description,
        "ARCHITECTURE_SUMMARY": (
            extract_architecture_summary(architecture)
            + "\n\n(See `architecture.md` at the repo root for the full "
            "architecture writeup this summary was excerpted from.)"
        ),
        "CURRENT_STATE": (
            "Freshly scaffolded — no code written yet. See `plan.md` "
            "(at the repo root) for the intended build sequence."
        ),
        "DOMAIN_LIBRARY_GUIDANCE": domain_library_guidance,
        "INITIAL_FEATURE_ROWS": (
            "| _(none yet — add a row per feature as you define them; "
            "see `_TEMPLATE.md` in this directory)_ | not_started | |"
        ),
        "TASK_TITLE": task_title,
        "TASK_CONTEXT": (
            f"This is the first task, generated from plan.md's first "
            f"milestone. Full architecture context is in "
            f"`architecture.md` and `app/CONTEXT.md` if you need more "
            f"than the summary below."
        ),
        "TASK_INSTRUCTIONS": task_body,
    }

    print(f"Scaffolding {project_name!r} into {args.output_dir}\n")

    if preserve_history:
        print("Preserving fulcra-prototype-grill-me git history...")
        try:
            clone_with_history(args.rapid_prototype_dir, args.output_dir, args.dry_run)
        except ScaffoldError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print()

    # 1. harness/ <- engine/ (verbatim copy, no hydration needed)
    print("Copying project-agnostic harness engine...")
    copy_tree(ENGINE_DIR, args.output_dir / "harness", args.dry_run)

    # 2. harness/prompts/system_prompt.md <- templates/system_prompt.md.template
    print("\nHydrating system prompt...")
    system_prompt_template = (TEMPLATES_DIR / "system_prompt.md.template").read_text()
    write_file(
        args.output_dir / "harness" / "prompts" / "system_prompt.md",
        hydrate(system_prompt_template, values),
        args.dry_run,
    )

    # 3. harness/prompts/task_001_<slug>.md <- templates/task.md.template
    print("\nHydrating first task prompt from plan.md's first milestone...")
    task_template = (TEMPLATES_DIR / "task.md.template").read_text()
    task_slug = slugify(task_title)
    write_file(
        args.output_dir / "harness" / "prompts" / f"task_001_{task_slug}.md",
        hydrate(task_template, values),
        args.dry_run,
    )

    # 4. app/CONTEXT.md, app/ENGINEERING_STANDARDS.md, app/features/*
    print("\nHydrating app/ scaffolding...")
    context_template = (TEMPLATES_DIR / "app" / "CONTEXT.md.template").read_text()
    write_file(
        args.output_dir / "app" / "CONTEXT.md",
        hydrate(context_template, values),
        args.dry_run,
    )

    standards_template = (
        TEMPLATES_DIR / "app" / "ENGINEERING_STANDARDS.md.template"
    ).read_text()
    write_file(
        args.output_dir / "app" / "ENGINEERING_STANDARDS.md",
        hydrate(standards_template, values),
        args.dry_run,
    )

    index_template = (
        TEMPLATES_DIR / "app" / "features" / "INDEX.md.template"
    ).read_text()
    write_file(
        args.output_dir / "app" / "features" / "INDEX.md",
        hydrate(index_template, values),
        args.dry_run,
    )

    feature_template_skeleton = (
        TEMPLATES_DIR / "app" / "features" / "_TEMPLATE.md"
    ).read_text()
    write_file(
        args.output_dir / "app" / "features" / "_TEMPLATE.md",
        feature_template_skeleton,  # verbatim, no hydration needed
        args.dry_run,
    )

    fulcra_client_source = (TEMPLATES_DIR / "app" / "fulcra_client.py").read_text()
    write_file(
        args.output_dir / "app" / "fulcra_client.py",
        fulcra_client_source,  # verbatim, no hydration needed -- this is
        # real, working, project-agnostic code (the exact credential-
        # loading pattern already proven in flow-state-app-v2), not a
        # template that needs per-project values filled in.
        args.dry_run,
    )

    # 5. Top-level repo files: README.md, pyproject.toml, .gitignore, .env.example
    print("\nHydrating top-level project files...")
    readme_template = (TEMPLATES_DIR / "README.md.template").read_text()
    write_file(
        args.output_dir / "README.md",
        hydrate(readme_template, values),
        args.dry_run,
    )

    pyproject_template = (TEMPLATES_DIR / "pyproject.toml.template").read_text()
    write_file(
        args.output_dir / "pyproject.toml",
        hydrate(pyproject_template, values),
        args.dry_run,
    )

    gitignore_content = (TEMPLATES_DIR / ".gitignore.template").read_text()
    write_file(args.output_dir / ".gitignore", gitignore_content, args.dry_run)

    env_example_content = (TEMPLATES_DIR / ".env.example.template").read_text()
    write_file(args.output_dir / ".env.example", env_example_content, args.dry_run)

    # 6. Copy the rapid-prototype artifacts themselves into the new repo
    # root, so the new project's history includes the reasoning that
    # produced it (per fulcra-for-agents.md's "Durable Handoff" pattern —
    # a future agent/session should be able to see how this project's
    # architecture was decided, not just the result). Skipped when
    # preserve_history is True: clone_with_history() already brought
    # these files in (along with every phase's individual commit, which
    # plain copying can never reproduce).
    if not preserve_history:
        print("\nCopying fulcra-prototype-grill-me artifacts into the new repo...")
        for artifact_name in ("intake", "interview", "architecture.md", "plan.md"):
            src = args.rapid_prototype_dir / artifact_name
            if not src.exists():
                continue
            dst = args.output_dir / artifact_name
            if src.is_dir():
                for f in sorted(src.rglob("*")):
                    if f.is_file():
                        rel = f.relative_to(args.rapid_prototype_dir)
                        write_file(args.output_dir / rel, f.read_text(), args.dry_run)
            else:
                write_file(dst, src.read_text(), args.dry_run)

    print(
        f"\n{'[dry-run] Nothing was written.' if args.dry_run else 'Done.'}\n"
    )
    if not args.dry_run:
        print("Next steps:")
        step = 1
        print(f"  {step}. cd {args.output_dir}")
        step += 1
        if preserve_history:
            print(
                f"  {step}. git log --oneline  # confirm your "
                f"fulcra-prototype-grill-me phase history came through, then "
                f"git add -A && git commit -m 'Scaffold harness + app'"
            )
        else:
            print(f"  {step}. git init && git add -A && git commit -m 'Initial scaffold'")
        step += 1
        print(f"  {step}. python -m venv .venv && .venv/bin/pip install -e .")
        step += 1
        print(f"  {step}. cp .env.example .env  # fill in GEMINI_API_KEY")
        step += 1
        print(f"  {step}. .venv/bin/python -m harness.test_loop_smoke  # confirm the harness works")
        step += 1
        print(
            f"  {step}. Review harness/prompts/system_prompt.md and "
            f"harness/prompts/task_001_{task_slug}.md by hand -- the "
            f"heuristics that generated them are a starting point, not a "
            f"substitute for your own judgment about what the project "
            f"actually needs first."
        )
        step += 1
        print(f"  {step}. .venv/bin/python -m harness.run_task task_001_" + task_slug + ".md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
