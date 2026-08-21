#!/usr/bin/env python3
"""
scaffold.py — turns fulcra-rapid-prototype artifacts into a real,
ready-to-run agent harness + app skeleton for a new project.

WHAT THIS SCRIPT ASSUMES ALREADY EXISTS (read these before running):
    - intake/brief.md        (fulcra-rapid-prototype: Intake phase)
    - architecture.md        (fulcra-rapid-prototype: Architecture phase,
                               approved by the user — this is a gate in
                               that skill, don't skip it)
    - plan.md                (fulcra-rapid-prototype: Plan phase)
If any of these don't exist yet, STOP and run those phases of
fulcra-rapid-prototype first — this script does not gather requirements,
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
      features/
        INDEX.md             — hydrated from templates/app/features/INDEX.md.template
        _TEMPLATE.md          — copied verbatim (per-feature file skeleton)
    README.md                 — hydrated from templates/README.md.template
    pyproject.toml            — hydrated from templates/pyproject.toml.template
    .gitignore                — copied verbatim from templates/.gitignore.template
    .env.example              — copied verbatim from templates/.env.example.template

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
import sys
from pathlib import Path

STARTER_KIT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = STARTER_KIT_ROOT / "engine"
TEMPLATES_DIR = STARTER_KIT_ROOT / "templates"


class ScaffoldError(Exception):
    """Raised when scaffolding cannot proceed (missing prerequisite
    artifact, invalid arguments, etc.) — always with a message explaining
    exactly what's missing and what to do about it."""


def read_required_artifact(path: Path, phase_name: str) -> str:
    """Read a required fulcra-rapid-prototype artifact file, failing with
    a clear, actionable error if it doesn't exist yet — rather than
    silently proceeding with empty/placeholder content, which would
    produce a harness that looks scaffolded but is missing the actual
    project understanding that phase was supposed to capture."""
    if not path.is_file():
        raise ScaffoldError(
            f"Missing required artifact: {path}\n"
            f"This should have been produced by fulcra-rapid-prototype's "
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

    fulcra-rapid-prototype's plan.md format is prose/markdown, not a
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
            "plan.md (the fulcra-rapid-prototype artifacts for this "
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
            "have a placeholder reminding you to fill this in by hand."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching disk.",
    )
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
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

    # Derive a one-paragraph description from the brief (its first
    # paragraph is expected to be a short summary per fulcra-rapid-
    # prototype's Intake template) -- fall back to the whole brief if it's
    # already short.
    first_paragraph = brief.split("\n\n", 1)[0].strip()
    project_description = first_paragraph if len(first_paragraph) < 500 else brief[:500]

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
        "ARCHITECTURE_SUMMARY": architecture,
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
    # root, so the new project's git history includes the reasoning that
    # produced it (per fulcra-for-agents.md's "Durable Handoff" pattern —
    # a future agent/session should be able to see how this project's
    # architecture was decided, not just the result).
    print("\nCopying fulcra-rapid-prototype artifacts into the new repo...")
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
        print(f"  1. cd {args.output_dir}")
        print("  2. git init && git add -A && git commit -m 'Initial scaffold'")
        print("  3. python -m venv .venv && .venv/bin/pip install -e .")
        print("  4. cp .env.example .env  # fill in GEMINI_API_KEY")
        print("  5. .venv/bin/python -m harness.test_loop_smoke  # confirm the harness works")
        print(
            f"  6. Review harness/prompts/system_prompt.md and "
            f"harness/prompts/task_001_{task_slug}.md by hand -- the "
            f"heuristics that generated them are a starting point, not a "
            f"substitute for your own judgment about what the project "
            f"actually needs first."
        )
        print("  7. .venv/bin/python -m harness.run_task task_001_" + task_slug + ".md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
