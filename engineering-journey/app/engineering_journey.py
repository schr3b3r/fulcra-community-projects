"""Unified CLI entrypoint for Engineering Journey.

Provides two subcommands:
  - `backfill`: ingests GitHub activity for a user and date range, generates day/week/month/quarter/year
    rollups, and computes notability signals, storing all artifacts durably in Fulcra.
  - `generate`: reads stored rollups and notability signals from Fulcra and synthesizes a narrative Markdown document.
"""

import argparse
from datetime import datetime, timedelta, timezone
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# rollup.py / narrative.py do a deferred `from harness.providers.gemini
# import call_model` (harness/ lives at the REPO ROOT, one level above
# this file's own app/ directory). Running this file directly as a
# script (`python app/engineering_journey.py ...`, exactly the documented
# invocation in SKILL.md/README.md) puts THIS file's own directory
# (app/) on sys.path, not the repo root -- so that import fails with
# "ModuleNotFoundError: No module named 'harness'" unless the repo root
# is separately on PYTHONPATH or `harness` was pip-installed as a
# package (`pip install -e .` at the repo root; `pip install -r
# requirements.txt` alone does NOT do this). Fixing it here, once, means
# the documented command works regardless of how the venv was set up --
# don't rely on the caller getting PYTHONPATH/install order right.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dotenv import load_dotenv

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from github_client import GitHubClient
from github_activity import backfill_full_github_activity
from rollup import (
    generate_day_week_rollups,
    generate_month_rollups,
    generate_layer_rollups,
)
from notability import generate_notability_signals
from narrative import generate_journey_narrative

# Must match github_activity.generate_period_chunks' own default recent_days
# (90) -- this is the same "recent vs. decayed granularity" boundary from
# Interview decision #1: day/week rollups only make sense for the recent
# window, month rollups only for everything older. Duplicated as a
# constant here (rather than importing github_activity's default) because
# rollup.py's day/week/month rollup functions take an explicit date range
# and do NOT enforce this boundary themselves -- callers are responsible
# for splitting the range correctly before calling them.
RECENT_WINDOW_DAYS = 90

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("engineering_journey")


class ProgressReporter:
    """Renders structured progress events (from checkpoint.process_with_checkpoint
    and narrative.generate_journey_narrative) as live, human-readable status
    lines on stdout.

    This exists specifically so a user watching `backfill`/`generate` run
    always sees concrete, moving progress -- "item 42/104" and an ETA, not
    just a start message followed by minutes of silence and then a final
    summary. This is deliberately independent of whichever model/agent is
    driving the CLI call: the CLI itself narrates, so behavior is identical
    whether it's invoked by Sonnet, Flash, a human at a terminal, or a cron
    job with its output only reviewed later.

    Two throttles keep this from being noisy on large runs (hundreds of
    period x repo work items): a minimum wall-clock interval between
    "still working" lines, and always-print on phase/task boundaries
    (start/resume/complete) regardless of throttling.
    """

    def __init__(self, min_interval_seconds: float = 4.0) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last_emit_time: float = 0.0
        self._phase_start_time: float = 0.0
        self._phase_total: int = 0

    @staticmethod
    def _describe_item(item: Any) -> str:
        """Turn a work-item dict into a short, human-legible label."""
        if isinstance(item, dict):
            if "repo_name" in item and "start_date" in item:
                span = f"{item['start_date']}..{item.get('end_date', item['start_date'])}"
                gran = item.get("granularity")
                gran_str = f", {gran}" if gran else ""
                return f"{item['repo_name']} ({span}{gran_str})"
            if "period_type" in item and "start_date" in item:
                span = f"{item['start_date']}..{item.get('end_date', item['start_date'])}"
                return f"{item['period_type']} {span}"
        return str(item)

    def _eta_str(self, index: int, total: int) -> str:
        elapsed = time.time() - self._phase_start_time
        if index <= 0 or elapsed <= 0:
            return ""
        rate = elapsed / index
        remaining = rate * max(total - index, 0)
        if remaining < 60:
            return f", ~{int(remaining)}s remaining"
        return f", ~{int(remaining / 60)}m remaining"

    def __call__(self, event: Dict[str, Any]) -> None:
        kind = event.get("kind")
        now = time.time()

        if kind in ("task_started",):
            self._phase_start_time = now
            self._phase_total = event.get("total", 0)
            resumed = event.get("resumed_from_index")
            if resumed:
                print(
                    f"  -> Resuming {event.get('stage')} at item {resumed}/{self._phase_total} "
                    f"(already completed earlier in a prior run)..."
                )
            else:
                print(f"  -> Starting {event.get('stage')}: {self._phase_total} item(s) to process...")
            self._last_emit_time = now

        elif kind == "task_already_completed":
            print(f"  -> {event.get('stage')} already complete, nothing to do.")

        elif kind == "item_completed":
            index = event.get("index", 0)
            total = event.get("total", 0) or 1
            is_boundary = index == total
            if is_boundary or (now - self._last_emit_time) >= self.min_interval_seconds:
                pct = int(100 * index / total) if total else 0
                label = self._describe_item(event.get("item"))
                eta = self._eta_str(index, total)
                print(f"     [{index}/{total}] {pct}% - {label}{eta}")
                self._last_emit_time = now

        elif kind == "task_completed":
            print(f"  -> Finished {event.get('stage')}: {event.get('completed_items_count')} item(s) processed.")

        elif kind == "overview_started":
            self._phase_start_time = now
            print(f"  -> Writing executive overview ({event.get('total_sections')} section(s) to synthesize)...")

        elif kind == "section_started":
            print(
                f"     [{event.get('index')}/{event.get('total')}] Synthesizing section: {event.get('title')}..."
            )

        elif kind == "narrative_completed":
            print(
                f"  -> Narrative complete: {event.get('total_sections')} section(s), "
                f"{event.get('character_count')} characters."
            )


def run_backfill(
    username: str,
    token: str,
    start_date: str,
    end_date: str,
    fulcra_credentials: Optional[str] = None,
    repo_names: Optional[List[str]] = None,
    client: Optional[FulcraAPI] = None,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """Orchestrate full ingestion, rollup generation, and notability signal computation.

    Args:
        username: GitHub username.
        token: GitHub Personal Access Token.
        start_date: Start date string ("YYYY-MM-DD").
        end_date: End date string ("YYYY-MM-DD").
        fulcra_credentials: Optional path to Fulcra credentials JSON.
        repo_names: Optional list of repo names to restrict backfill to.
        client: Optional FulcraAPI client instance.
        progress_callback: Optional callable receiving structured progress
            events (see checkpoint.process_with_checkpoint's docstring for
            the event shape) as each of the six pipeline phases runs. If
            omitted, defaults to a `ProgressReporter()` printing live
            status lines to stdout -- pass an explicit no-op callable to
            suppress progress output entirely.

    Returns:
        Summary dict of execution stages.
    """
    if progress_callback is None:
        progress_callback = ProgressReporter()

    if client is None:
        client = get_fulcra_client(credentials_path=fulcra_credentials)

    gh_client = GitHubClient(token=token, username=username)

    print(f"[Phase 1/6] Raw GitHub activity ingestion for {username} ({start_date} to {end_date})")
    raw_res = backfill_full_github_activity(
        gh_client=gh_client,
        start_date=start_date,
        end_date=end_date,
        repo_names=repo_names,
        client=client,
        progress_callback=progress_callback,
    )
    if raw_res.get("is_delta"):
        logger.info(
            "Raw activity delta backfill completed: %s items processed for new repos: %s.",
            raw_res.get("completed_items_count"),
            raw_res.get("new_repos"),
        )
    else:
        logger.info(
            "Raw activity backfill completed: %s items processed.",
            raw_res.get("completed_items_count"),
        )

    # Split the full range at the same "recent 90 days" boundary
    # github_activity.generate_period_chunks already uses for raw ingestion
    # (Interview decision #1): day/week rollups only make sense for the
    # recent window; everything older gets month rollups instead. Passing
    # the FULL multi-year range straight to generate_day_week_rollups (no
    # internal cutoff of its own) would otherwise generate one daily rollup
    # -- and one LLM call -- per day across the entire backfill window,
    # defeating the whole point of decaying granularity for a 3-4 year run.
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    recent_cutoff_dt = end_dt - timedelta(days=RECENT_WINDOW_DAYS)
    recent_start_dt = max(start_dt, recent_cutoff_dt)
    recent_start_str = recent_start_dt.strftime("%Y-%m-%d")
    older_end_dt = recent_start_dt - timedelta(days=1)
    older_end_str = older_end_dt.strftime("%Y-%m-%d")

    print(f"[Phase 2/6] Day/week rollups for the recent window ({recent_start_str} to {end_date})")
    if recent_start_dt <= end_dt:
        day_week_res = generate_day_week_rollups(
            username=username,
            start_date=recent_start_str,
            end_date=end_date,
            client=client,
            progress_callback=progress_callback,
        )
    else:
        day_week_res = {"status": "skipped", "rollups_generated": 0}
        print("  -> Skipped: entire requested range falls within the recent window.")

    print(f"[Phase 3/6] Month rollups for older history ({start_date} to {older_end_str})")
    if start_dt <= older_end_dt:
        month_res = generate_month_rollups(
            username=username,
            start_date=start_date,
            end_date=older_end_str,
            client=client,
            progress_callback=progress_callback,
        )
    else:
        month_res = {"status": "skipped", "rollups_generated": 0}
        print("  -> Skipped: entire requested range falls within the recent window.")

    print("[Phase 4/6] Quarter rollups")
    quarter_res = generate_layer_rollups(
        username=username,
        period_type="quarter",
        start_date=start_date,
        end_date=end_date,
        client=client,
        progress_callback=progress_callback,
    )

    print("[Phase 5/6] Year rollups")
    year_res = generate_layer_rollups(
        username=username,
        period_type="year",
        start_date=start_date,
        end_date=end_date,
        client=client,
        progress_callback=progress_callback,
    )

    print("[Phase 6/6] Personal-baseline notability signals (day, week, month, quarter, year)")
    notability_results = {}
    for pt in ["day", "week", "month", "quarter", "year"]:
        sig_res = generate_notability_signals(
            username=username,
            period_type=pt,
            start_date=start_date,
            end_date=end_date,
            client=client,
            progress_callback=progress_callback,
        )
        notability_results[pt] = sig_res

    return {
        "username": username,
        "start_date": start_date,
        "end_date": end_date,
        "raw_backfill": raw_res,
        "day_week_rollups": day_week_res,
        "month_rollups": month_res,
        "quarter_rollups": quarter_res,
        "year_rollups": year_res,
        "notability_signals": notability_results,
    }


def run_generate(
    username: str,
    start_date: str,
    end_date: str,
    output_path: Optional[str] = None,
    fulcra_credentials: Optional[str] = None,
    client: Optional[FulcraAPI] = None,
    progress_callback: Optional[Any] = None,
) -> str:
    """Generate Markdown journey narrative from stored Fulcra rollups and signals.

    Args:
        username: GitHub username.
        start_date: Start date string ("YYYY-MM-DD").
        end_date: End date string ("YYYY-MM-DD").
        output_path: Optional file path to write Markdown document.
        fulcra_credentials: Optional path to Fulcra credentials JSON.
        client: Optional FulcraAPI client instance.
        progress_callback: Optional callable receiving structured progress
            events as each narrative section is synthesized (see
            narrative.generate_journey_narrative's docstring). If omitted,
            defaults to a `ProgressReporter()` printing live status lines
            to stdout -- pass an explicit no-op callable to suppress.

    Returns:
        Generated Markdown document content string.
    """
    if progress_callback is None:
        progress_callback = ProgressReporter()

    if client is None:
        client = get_fulcra_client(credentials_path=fulcra_credentials)

    if output_path is None:
        output_path = f"engineering_journey_{username}.md"

    print(f"Synthesizing narrative for {username} ({start_date} to {end_date})")
    markdown_content = generate_journey_narrative(
        username=username,
        start_date=start_date,
        end_date=end_date,
        client=client,
        output_path=output_path,
        progress_callback=progress_callback,
    )
    logger.info("Narrative generated successfully. Output saved to %s", output_path)
    return markdown_content


def _compute_date_range(
    start_date_arg: Optional[str],
    end_date_arg: Optional[str],
    years_arg: float,
) -> tuple[str, str]:
    """Calculate effective start and end dates from CLI arguments."""
    now = datetime.now(timezone.utc)
    if end_date_arg:
        end_str = end_date_arg
        end_dt = datetime.strptime(end_date_arg, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_dt = now
        end_str = end_dt.strftime("%Y-%m-%d")

    if start_date_arg:
        start_str = start_date_arg
    else:
        start_dt = end_dt - timedelta(days=int(years_arg * 365))
        start_str = start_dt.strftime("%Y-%m-%d")

    return start_str, end_str


def main() -> None:
    """CLI entrypoint parsing subcommands and running appropriate workflow."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Engineering Journey CLI: Backfill GitHub activity and generate journey narratives."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: backfill
    parser_backfill = subparsers.add_parser(
        "backfill",
        help="Run full GitHub backfill, rollup generation, and notability signal computation.",
    )
    parser_backfill.add_argument(
        "--username",
        type=str,
        default=os.environ.get("GITHUB_USERNAME"),
        help="GitHub username (defaults to GITHUB_USERNAME env var).",
    )
    parser_backfill.add_argument(
        "--token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub PAT (defaults to GITHUB_TOKEN env var).",
    )
    parser_backfill.add_argument(
        "--fulcra-credentials",
        type=str,
        default=os.environ.get("FULCRA_CREDENTIALS_PATH"),
        help="Path to Fulcra credentials JSON file.",
    )
    parser_backfill.add_argument(
        "--years",
        type=float,
        default=3.0,
        help="Number of years back to backfill if --start-date is not specified (default: 3.0).",
    )
    parser_backfill.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (overrides --years).",
    )
    parser_backfill.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (defaults to today).",
    )
    parser_backfill.add_argument(
        "--repo",
        type=str,
        action="append",
        dest="repos",
        help="Specify repo ('owner/repo'). Can be repeated. If omitted, enumerates all repos.",
    )

    # Subcommand: generate
    parser_generate = subparsers.add_parser(
        "generate",
        help="Generate Markdown journey narrative from ingested Fulcra data.",
    )
    parser_generate.add_argument(
        "--username",
        type=str,
        default=os.environ.get("GITHUB_USERNAME", "schr3b3r"),
        help="GitHub username to generate narrative for.",
    )
    parser_generate.add_argument(
        "--fulcra-credentials",
        type=str,
        default=os.environ.get("FULCRA_CREDENTIALS_PATH"),
        help="Path to Fulcra credentials JSON file.",
    )
    parser_generate.add_argument(
        "--years",
        type=float,
        default=3.0,
        help="Number of years back to cover if --start-date is not specified (default: 3.0).",
    )
    parser_generate.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format.",
    )
    parser_generate.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (defaults to today).",
    )
    parser_generate.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output Markdown file path (defaults to engineering_journey_<username>.md).",
    )

    args = parser.parse_args()

    start_date, end_date = _compute_date_range(
        args.start_date, args.end_date, args.years
    )

    if args.command == "backfill":
        if not args.username:
            parser.error("GitHub username is required. Pass --username or set GITHUB_USERNAME env var.")
        if not args.token:
            parser.error("GitHub token is required. Pass --token or set GITHUB_TOKEN env var.")

        print(f"Executing backfill for {args.username} from {start_date} to {end_date}...")
        results = run_backfill(
            username=args.username,
            token=args.token,
            start_date=start_date,
            end_date=end_date,
            fulcra_credentials=args.fulcra_credentials,
            repo_names=args.repos,
        )
        print("Backfill completed successfully!")
        if results["raw_backfill"].get("is_delta"):
            print(
                f"Raw delta items processed: {results['raw_backfill'].get('completed_items_count')} "
                f"(new repos: {results['raw_backfill'].get('new_repos')})"
            )
        else:
            print(f"Raw items processed: {results['raw_backfill'].get('completed_items_count')}")
        print(f"Day/Week rollups: {results['day_week_rollups'].get('rollups_generated')}")
        print(f"Month rollups: {results['month_rollups'].get('rollups_generated')}")
        print(f"Quarter rollups: {results['quarter_rollups'].get('rollups_generated')}")
        print(f"Year rollups: {results['year_rollups'].get('rollups_generated')}")

    elif args.command == "generate":
        if not args.username:
            parser.error("GitHub username is required. Pass --username or set GITHUB_USERNAME env var.")

        output_file = args.output or f"engineering_journey_{args.username}.md"
        print(f"Generating narrative for {args.username} from {start_date} to {end_date}...")
        content = run_generate(
            username=args.username,
            start_date=start_date,
            end_date=end_date,
            output_path=output_file,
            fulcra_credentials=args.fulcra_credentials,
        )
        print(f"Narrative document successfully created: {output_file} ({len(content)} characters)")


if __name__ == "__main__":
    main()
