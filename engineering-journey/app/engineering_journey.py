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
from typing import Any, Dict, List, Optional

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


def run_backfill(
    username: str,
    token: str,
    start_date: str,
    end_date: str,
    fulcra_credentials: Optional[str] = None,
    repo_names: Optional[List[str]] = None,
    client: Optional[FulcraAPI] = None,
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

    Returns:
        Summary dict of execution stages.
    """
    if client is None:
        client = get_fulcra_client(credentials_path=fulcra_credentials)

    gh_client = GitHubClient(token=token, username=username)

    logger.info(
        "Starting raw GitHub activity backfill for %s (%s to %s)...",
        username,
        start_date,
        end_date,
    )
    raw_res = backfill_full_github_activity(
        gh_client=gh_client,
        start_date=start_date,
        end_date=end_date,
        repo_names=repo_names,
        client=client,
    )
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

    if recent_start_dt <= end_dt:
        logger.info(
            "Generating day and week activity rollups for the recent window (%s to %s)...",
            recent_start_str,
            end_date,
        )
        day_week_res = generate_day_week_rollups(
            username=username,
            start_date=recent_start_str,
            end_date=end_date,
            client=client,
        )
    else:
        day_week_res = {"status": "skipped", "rollups_generated": 0}

    if start_dt <= older_end_dt:
        logger.info(
            "Generating month activity rollups for older history (%s to %s)...",
            start_date,
            older_end_str,
        )
        month_res = generate_month_rollups(
            username=username,
            start_date=start_date,
            end_date=older_end_str,
            client=client,
        )
    else:
        month_res = {"status": "skipped", "rollups_generated": 0}

    logger.info("Generating quarter activity rollups...")
    quarter_res = generate_layer_rollups(
        username=username,
        period_type="quarter",
        start_date=start_date,
        end_date=end_date,
        client=client,
    )

    logger.info("Generating year activity rollups...")
    year_res = generate_layer_rollups(
        username=username,
        period_type="year",
        start_date=start_date,
        end_date=end_date,
        client=client,
    )

    logger.info("Computing personal-baseline notability signals across all period types...")
    notability_results = {}
    for pt in ["day", "week", "month", "quarter", "year"]:
        sig_res = generate_notability_signals(
            username=username,
            period_type=pt,
            start_date=start_date,
            end_date=end_date,
            client=client,
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
) -> str:
    """Generate Markdown journey narrative from stored Fulcra rollups and signals.

    Args:
        username: GitHub username.
        start_date: Start date string ("YYYY-MM-DD").
        end_date: End date string ("YYYY-MM-DD").
        output_path: Optional file path to write Markdown document.
        fulcra_credentials: Optional path to Fulcra credentials JSON.
        client: Optional FulcraAPI client instance.

    Returns:
        Generated Markdown document content string.
    """
    if client is None:
        client = get_fulcra_client(credentials_path=fulcra_credentials)

    if output_path is None:
        output_path = f"engineering_journey_{username}.md"

    logger.info(
        "Generating narrative journey for %s (%s to %s)...",
        username,
        start_date,
        end_date,
    )
    markdown_content = generate_journey_narrative(
        username=username,
        start_date=start_date,
        end_date=end_date,
        client=client,
        output_path=output_path,
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
