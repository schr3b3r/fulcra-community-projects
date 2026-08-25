"""Narrative generation module for Engineering Journey.

Reads ActivityRollup and NotabilitySignal records from Fulcra, structures the journey
chronologically into top-level periods (quarter or month backbone), paces narrative depth
according to notability scores and flags, synthesizes grounded prose using Gemini LLM,
and produces a well-formatted Markdown document complete with a provenance appendix.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from rollup import ActivityRollup, read_rollups, _parse_iso_date
from notability import NotabilitySignal, read_notability_signals

logger = logging.getLogger(__name__)


@dataclass
class SectionContext:
    """Represents a top-level chronological section (e.g. Quarter or Month) for narrative synthesis."""

    title: str  # Section title (e.g. "Q3 2026 (July 2026 - September 2026)")
    period_type: str  # "quarter", "month", "year", "week"
    start_date: str  # ISO date string "YYYY-MM-DD"
    end_date: str  # ISO date string "YYYY-MM-DD"
    top_rollup: Optional[ActivityRollup] = None
    top_signal: Optional[NotabilitySignal] = None
    child_rollups: List[ActivityRollup] = field(default_factory=list)
    child_signals: List[NotabilitySignal] = field(default_factory=list)
    max_notability_score: float = 0.0
    all_flags: List[str] = field(default_factory=list)


def _format_section_title(period_type: str, start_date: str, end_date: str) -> str:
    """Format a human-friendly section title based on period type and date range."""
    try:
        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
        e_dt = datetime.strptime(end_date, "%Y-%m-%d")
        s_month_name = s_dt.strftime("%B")
        e_month_name = e_dt.strftime("%B")
        year = s_dt.year

        if period_type == "quarter":
            q_num = (s_dt.month - 1) // 3 + 1
            return f"Q{q_num} {year} ({s_month_name} {year} – {e_month_name} {year})"
        elif period_type == "month":
            return f"{s_month_name} {year}"
        elif period_type == "year":
            return f"Year {year}"
        else:
            return f"{start_date} to {end_date}"
    except ValueError:
        return f"{start_date} to {end_date}"


def build_section_contexts(
    username: str,
    start_date: str,
    end_date: str,
    rollups: List[ActivityRollup],
    signals: List[NotabilitySignal],
) -> List[SectionContext]:
    """Group rollups and signals into chronological top-level SectionContext blocks.

    Args:
        username: GitHub username.
        start_date: Start date filter ("YYYY-MM-DD").
        end_date: End date filter ("YYYY-MM-DD").
        rollups: List of ActivityRollup records.
        signals: List of NotabilitySignal records.

    Returns:
        List of SectionContext objects sorted chronologically.
    """
    user_rollups = [
        r
        for r in rollups
        if r.username == username
        and r.start_date >= start_date
        and r.end_date <= end_date
    ]
    user_signals = [
        s
        for s in signals
        if s.username == username
        and s.start_date >= start_date
        and s.end_date <= end_date
    ]

    # Map signals by (period_type, start_date, end_date)
    signal_map: Dict[tuple, NotabilitySignal] = {}
    for s in user_signals:
        signal_map[(s.period_type, s.start_date, s.end_date)] = s

    # Determine backbone period type
    quarter_rollups = [r for r in user_rollups if r.period_type == "quarter"]
    month_rollups = [r for r in user_rollups if r.period_type == "month"]

    backbone_rollups: List[ActivityRollup] = []
    backbone_type = ""

    if quarter_rollups:
        backbone_rollups = sorted(quarter_rollups, key=lambda x: x.start_date)
        backbone_type = "quarter"
    elif month_rollups:
        backbone_rollups = sorted(month_rollups, key=lambda x: x.start_date)
        backbone_type = "month"
    else:
        # Fallback to week or day rollups grouped by month
        backbone_rollups = sorted(user_rollups, key=lambda x: x.start_date)
        backbone_type = "custom"

    section_contexts: List[SectionContext] = []

    if backbone_type in ("quarter", "month"):
        for top_r in backbone_rollups:
            top_s = signal_map.get((top_r.period_type, top_r.start_date, top_r.end_date))
            # Find child rollups whose date ranges fall inside this top rollup
            children = [
                r
                for r in user_rollups
                if r.period_type in ("week", "day", "month")
                and r.period_type != top_r.period_type
                and r.start_date >= top_r.start_date
                and r.end_date <= top_r.end_date
            ]
            children.sort(key=lambda x: (x.start_date, x.period_type))

            # Filter out days if week rollups exist for those dates to avoid duplicate listing
            has_weeks = any(c.period_type == "week" for c in children)
            if has_weeks:
                filtered_children = [c for c in children if c.period_type != "day"]
            else:
                filtered_children = children

            child_sigs = [
                signal_map[(c.period_type, c.start_date, c.end_date)]
                for c in filtered_children
                if (c.period_type, c.start_date, c.end_date) in signal_map
            ]

            scores = [top_s.notability_score if top_s else 0.0] + [
                cs.notability_score for cs in child_sigs
            ]
            max_score = max(scores) if scores else 0.0

            flags_set = set()
            if top_s:
                flags_set.update(top_s.flags)
            for cs in child_sigs:
                flags_set.update(cs.flags)

            title = _format_section_title(
                top_r.period_type, top_r.start_date, top_r.end_date
            )

            section_contexts.append(
                SectionContext(
                    title=title,
                    period_type=top_r.period_type,
                    start_date=top_r.start_date,
                    end_date=top_r.end_date,
                    top_rollup=top_r,
                    top_signal=top_s,
                    child_rollups=filtered_children,
                    child_signals=child_sigs,
                    max_notability_score=max_score,
                    all_flags=sorted(list(flags_set)),
                )
            )
    else:
        # Fallback grouping by calendar month
        months_dict: Dict[str, List[ActivityRollup]] = {}
        for r in user_rollups:
            month_key = r.start_date[:7]  # YYYY-MM
            months_dict.setdefault(month_key, []).append(r)

        for month_key in sorted(months_dict.keys()):
            m_rollups = months_dict[month_key]
            m_rollups.sort(key=lambda x: x.start_date)
            s_date = m_rollups[0].start_date
            e_date = m_rollups[-1].end_date

            m_sigs = [
                signal_map[(r.period_type, r.start_date, r.end_date)]
                for r in m_rollups
                if (r.period_type, r.start_date, r.end_date) in signal_map
            ]

            scores = [ms.notability_score for ms in m_sigs]
            max_score = max(scores) if scores else 0.0

            flags_set = set()
            for ms in m_sigs:
                flags_set.update(ms.flags)

            title = _format_section_title("month", s_date, e_date)

            section_contexts.append(
                SectionContext(
                    title=title,
                    period_type="month",
                    start_date=s_date,
                    end_date=e_date,
                    child_rollups=m_rollups,
                    child_signals=m_sigs,
                    max_notability_score=max_score,
                    all_flags=sorted(list(flags_set)),
                )
            )

    return section_contexts


def _synthesize_overview(
    username: str,
    start_date: str,
    end_date: str,
    sections: List[SectionContext],
    llm_callable: Optional[Callable[..., Any]] = None,
) -> str:
    """Synthesize an executive narrative overview for the entire journey range."""
    if llm_callable is None:
        from harness.providers.gemini import call_model

        llm_callable = call_model

    section_summaries = []
    total_commits = 0
    total_prs = 0
    total_issues = 0
    total_comments = 0
    total_activities = 0
    all_repos = set()

    for sec in sections:
        if sec.top_rollup:
            s = sec.top_rollup.stats
            total_commits += s.get("commit_count", 0)
            total_prs += s.get("pr_count", 0)
            total_issues += s.get("issue_count", 0)
            total_comments += s.get("comment_count", 0)
            total_activities += s.get("total_activities", 0)
            for repo in s.get("repos_touched", []):
                all_repos.add(repo)
            summary_text = sec.top_rollup.summary
        else:
            sec_activities = sum(
                c.stats.get("total_activities", 0) for c in sec.child_rollups
            )
            total_activities += sec_activities
            summary_text = f"Activity across {len(sec.child_rollups)} period rollups."

        section_summaries.append(
            f"### {sec.title} (Max Notability Score: {sec.max_notability_score:.2f}, Flags: {sec.all_flags})\n{summary_text}"
        )

    sections_text = "\n\n".join(section_summaries)

    prompt = (
        f"Write an engaging 2-3 paragraph executive summary introduce developer {username}'s "
        f"engineering journey from {start_date} to {end_date}.\n\n"
        f"Aggregate Stats: {total_activities} total activities ({total_commits} commits, {total_prs} PRs, "
        f"{total_issues} issues, {total_comments} comments/reviews) across repositories: {sorted(list(all_repos))}.\n\n"
        f"Period Breakdown:\n{sections_text}\n\n"
        "Capture overarching themes, primary focus shifts, significant technical milestones, "
        "and pacing over time. Maintain a polished, narrative tone suitable for reading or sharing."
    )

    try:
        response = llm_callable(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are an expert technical biographer creating a high-level engineering "
                "journey introduction."
            ),
        )
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        elif isinstance(response, str) and response:
            return response.strip()
    except Exception as exc:
        logger.warning("Overview LLM synthesis failed: %s", exc)

    return (
        f"This document traces the engineering journey of **{username}** from {start_date} to {end_date}. "
        f"Over this period, {username} logged **{total_activities} total activities** across "
        f"**{len(all_repos)} repositories** ({', '.join(sorted(list(all_repos)))})."
    )


def _synthesize_section_narrative(
    username: str,
    section: SectionContext,
    llm_callable: Optional[Callable[..., Any]] = None,
) -> str:
    """Synthesize narrative prose for a chronological section, pacing detail by notability.

    Args:
        username: GitHub username.
        section: SectionContext object for the period.
        llm_callable: Optional custom LLM function.

    Returns:
        Generated markdown narrative prose for the section.
    """
    if llm_callable is None:
        from harness.providers.gemini import call_model

        llm_callable = call_model

    # Build context detail from child rollups and signals
    child_lines = []
    notable_periods = []
    quiet_periods = []

    # Pair child rollups with their notability signals
    sig_map = {
        (s.period_type, s.start_date, s.end_date): s for s in section.child_signals
    }

    for child in section.child_rollups:
        sig = sig_map.get((child.period_type, child.start_date, child.end_date))
        score = sig.notability_score if sig else 0.0
        flags = sig.flags if sig else []
        explanation = sig.explanation if sig else ""

        line = (
            f"- [{child.period_type.upper()}] {child.start_date} to {child.end_date} | "
            f"Notability Score: {score:.2f} | Flags: {flags}\n"
            f"  Stats: {child.stats.get('total_activities', 0)} activities "
            f"({child.stats.get('commit_count', 0)} commits, {child.stats.get('pr_count', 0)} PRs) "
            f"in repos {child.stats.get('repos_touched', [])}\n"
            f"  Explanation: {explanation}\n"
            f"  Summary: {child.summary}"
        )
        child_lines.append(line)

        is_notable = score >= 0.4 or any(
            f in flags
            for f in ("high_volume", "new_repo", "focus_switch", "streak")
        )
        if is_notable:
            notable_periods.append(child)
        else:
            quiet_periods.append(child)

    child_detail_text = (
        "\n".join(child_lines)
        if child_lines
        else "No granular child period rollups recorded."
    )

    top_summary = section.top_rollup.summary if section.top_rollup else ""
    top_stats = section.top_rollup.stats if section.top_rollup else {}

    prompt = (
        f"Write the narrative prose section for developer {username}'s engineering journey during "
        f"**{section.title}** ({section.start_date} to {section.end_date}).\n\n"
        f"Section High-Level Summary: {top_summary}\n"
        f"Section Stats: {top_stats}\n"
        f"Overall Section Notability Flags: {section.all_flags} (Max Score: {section.max_notability_score:.2f})\n\n"
        f"Sub-Period Breakdown:\n{child_detail_text}\n\n"
        "PACING AND STRUCTURE INSTRUCTIONS:\n"
        "1. For sub-periods flagged as NOTABLE (high_volume, new_repo, focus_switch, streak, high score), "
        "dedicate detailed, engaging narrative space (1-3 paragraphs) describing specific repository work, "
        "features built, PRs reviewed, or architectural shifts grounded in the details above.\n"
        "2. For sub-periods flagged as QUIET or ROUTINE (low activity volume, low_volume_gap, low score), "
        "condense them into a single brief transition sentence or clause (e.g. 'Work slowed during early August as focus shifted offline before resuming...'). "
        "Do NOT silently omit quiet stretches, but do NOT pad them with false significance.\n"
        "3. Write cohesive markdown prose with natural transitions. Do NOT list bullet points or raw key-value stats dumps."
    )

    try:
        response = llm_callable(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are an expert technical biographer building an engineering journey story. "
                "Base all narrative statements strictly on provided activity details."
            ),
        )
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        elif isinstance(response, str) and response:
            return response.strip()
    except Exception as exc:
        logger.warning(
            "Section narrative LLM synthesis failed for %s: %s", section.title, exc
        )

    # Fallback prose if LLM fails
    fallback_parts = []
    if section.top_rollup:
        fallback_parts.append(section.top_rollup.summary)

    for c in section.child_rollups:
        fallback_parts.append(
            f"From {c.start_date} to {c.end_date}: {c.summary}"
        )

    return "\n\n".join(fallback_parts)


def generate_journey_narrative(
    username: str,
    start_date: str,
    end_date: str,
    client: Optional[FulcraAPI] = None,
    output_path: Optional[str] = None,
    llm_callable: Optional[Callable[..., Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """Generate a single, paced, engaging Markdown journey document from Fulcra rollups and signals.

    Args:
        username: GitHub username.
        start_date: Start date ("YYYY-MM-DD").
        end_date: End date ("YYYY-MM-DD").
        client: Optional authenticated FulcraAPI client.
        output_path: Optional file path to write markdown output.
        llm_callable: Optional custom LLM function.
        progress_callback: Optional callable invoked with a structured event
            dict as each backbone section's prose is synthesized (event
            "kind" values: "overview_started", "section_started",
            "section_completed", "narrative_completed"). Never raises out
            of this function -- a failing callback is caught and ignored.

    Returns:
        Full generated Markdown text string.
    """

    def _emit(event: Dict[str, Any]) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:
            pass

    if client is None:
        client = get_fulcra_client()

    rollups = read_rollups(username=username, client=client)
    signals = read_notability_signals(username=username, client=client)

    sections = build_section_contexts(
        username=username,
        start_date=start_date,
        end_date=end_date,
        rollups=rollups,
        signals=signals,
    )

    _emit({"kind": "overview_started", "total_sections": len(sections)})

    overview_text = _synthesize_overview(
        username=username,
        start_date=start_date,
        end_date=end_date,
        sections=sections,
        llm_callable=llm_callable,
    )

    # Build document header
    doc_lines = [
        f"# Engineering Journey: {username}",
        f"*Period: {start_date} to {end_date}*",
        "",
        "## Overview",
        overview_text,
        "",
    ]

    # Build chronological sections
    for i, sec in enumerate(sections):
        _emit(
            {
                "kind": "section_started",
                "index": i + 1,
                "total": len(sections),
                "title": sec.title,
            }
        )
        doc_lines.append(f"## {sec.title}")
        sec_prose = _synthesize_section_narrative(
            username=username,
            section=sec,
            llm_callable=llm_callable,
        )
        doc_lines.append(sec_prose)
        doc_lines.append("")
        _emit(
            {
                "kind": "section_completed",
                "index": i + 1,
                "total": len(sections),
                "title": sec.title,
            }
        )

    # Build Provenance Appendix
    doc_lines.append("## Appendix: Provenance & Data References")
    doc_lines.append(
        "This narrative document was derived from durable `ActivityRollup` and `NotabilitySignal` "
        "records stored in Fulcra, maintaining an explicit chain of evidence down to raw GitHub activity."
    )
    doc_lines.append("")
    doc_lines.append("### Data Inventory")
    doc_lines.append(f"- **Developer:** `{username}`")
    doc_lines.append(f"- **Timeframe:** `{start_date}` to `{end_date}`")
    doc_lines.append(f"- **Total Rollups Evaluated:** {len(rollups)}")
    doc_lines.append(f"- **Total Notability Signals Evaluated:** {len(signals)}")
    doc_lines.append("")
    doc_lines.append("### Section Provenance Mapping")
    doc_lines.append(
        "| Section / Period | Top-Level Rollup ID | Max Notability Score | Flags Detected | Child Rollup Count | Source Rollup IDs |"
    )
    doc_lines.append(
        "| --- | --- | --- | --- | --- | --- |"
    )

    for sec in sections:
        top_id = (
            sec.top_rollup.id
            if (sec.top_rollup and sec.top_rollup.id)
            else f"{sec.period_type}:{username}:{sec.start_date}_{sec.end_date}"
        )
        flags_str = ", ".join(sec.all_flags) if sec.all_flags else "none"
        child_ids = [
            c.id if c.id else f"{c.period_type}:{c.start_date}_{c.end_date}"
            for c in sec.child_rollups
        ]
        child_ids_str = ", ".join(child_ids[:3]) + (
            f" (+{len(child_ids)-3} more)" if len(child_ids) > 3 else ""
        )
        if not child_ids_str:
            child_ids_str = "N/A"

        doc_lines.append(
            f"| {sec.title} | `{top_id}` | {sec.max_notability_score:.2f} | `{flags_str}` | {len(sec.child_rollups)} | `{child_ids_str}` |"
        )

    doc_lines.append("")
    markdown_content = "\n".join(doc_lines)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info("Saved journey narrative markdown to %s", output_path)

    _emit(
        {
            "kind": "narrative_completed",
            "total_sections": len(sections),
            "output_path": output_path,
            "character_count": len(markdown_content),
        }
    )

    return markdown_content


def main() -> None:
    """CLI entrypoint for running narrative generation."""
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate Engineering Journey Markdown document from Fulcra rollups and signals."
    )
    parser.add_argument(
        "--username",
        type=str,
        default="schr3b3r",
        help="GitHub username to generate narrative for.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2026-07-01",
        help="Start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-09-30",
        help="End date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="engineering_journey_schr3b3r.md",
        help="Path where markdown file should be saved.",
    )

    args = parser.parse_args()

    print(
        f"Generating narrative for {args.username} ({args.start_date} to {args.end_date})..."
    )
    markdown_text = generate_journey_narrative(
        username=args.username,
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=args.output,
    )
    print(f"Narrative generated successfully! Output written to {args.output}")
    print(f"Total document length: {len(markdown_text)} characters")


if __name__ == "__main__":
    main()
