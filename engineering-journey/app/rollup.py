"""Rollup record model and generation logic for Engineering Journey.

Computes day, week, month, quarter, and year activity rollups from raw GitHub activity records
and lower-layer rollups, generating structured volume stats, LLM narrative summaries,
and explicit provenance chains stored durably in Fulcra as custom data types.
"""

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from fulcra_types import get_custom_source_tag, get_or_create_tag_uuids
from checkpoint import process_with_checkpoint, _fetch_annotations_merged
from github_activity import GitHubActivityRaw, read_raw_activities

ROLLUP_RECORD_TYPE = "ActivityRollup"

logger = logging.getLogger(__name__)


class RollupStoreError(Exception):
    """Exception raised for errors in ActivityRollup persistence or generation."""


def _format_iso_timestamp(timestamp_str: str) -> str:
    """Ensure a date or ISO timestamp string is formatted as ISO 8601 UTC timestamp."""
    if len(timestamp_str) == 10 and timestamp_str[4] == "-" and timestamp_str[7] == "-":
        return f"{timestamp_str}T00:00:00Z"
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


@dataclass
class ActivityRollup:
    """Represents a period rollup (day, week, month, quarter, year) summarizing GitHub activity."""

    period_type: str  # "day", "week", "month", "quarter", "year"
    start_date: str  # ISO date string "YYYY-MM-DD"
    end_date: str  # ISO date string "YYYY-MM-DD"
    username: str  # GitHub username
    summary: str  # LLM-generated narrative text
    stats: Dict[str, Any] = field(default_factory=dict)
    source_record_ids: List[str] = field(default_factory=list)
    updated_at: Optional[str] = None
    id: Optional[str] = None  # Fulcra record ID if saved/retrieved

    def __post_init__(self) -> None:
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ActivityRollup into a dictionary."""
        return {
            "record_type": ROLLUP_RECORD_TYPE,
            "period_type": self.period_type,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "username": self.username,
            "summary": self.summary,
            "stats": self.stats,
            "source_record_ids": self.source_record_ids,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], record_id: Optional[str] = None
    ) -> "ActivityRollup":
        """Reconstruct an ActivityRollup instance from a dictionary."""
        return cls(
            period_type=data["period_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            username=data["username"],
            summary=data["summary"],
            stats=data.get("stats", {}),
            source_record_ids=data.get("source_record_ids", []),
            updated_at=data.get("updated_at"),
            id=record_id,
        )

    def to_fulcra_record(
        self,
        source_tag: Optional[str] = None,
        tag_ids: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Format into a Fulcra MomentAnnotation record dict."""
        rec: Dict[str, Any] = {
            "recorded_at": _format_iso_timestamp(self.start_date),
            "note": json.dumps(self.to_dict()),
        }
        if tag_ids:
            rec["tags"] = tag_ids

        if sources:
            rec["sources"] = sources
        elif source_tag:
            rec["sources"] = [
                "com.github",
                "agent.engineering-journey.rollup",
                source_tag,
            ]
        return rec


def write_rollups(
    rollups: List[ActivityRollup],
    client: Optional[FulcraAPI] = None,
) -> List[ActivityRollup]:
    """Write ActivityRollup records to Fulcra as MomentAnnotation records.

    Args:
        rollups: List of ActivityRollup instances to record.
        client: Optional authenticated FulcraAPI client.

    Returns:
        The input list of ActivityRollup objects.
    """
    if not rollups:
        return []

    if client is None:
        client = get_fulcra_client()

    source_tag = get_custom_source_tag(ROLLUP_RECORD_TYPE, client=client)

    all_tag_names = [r.period_type for r in rollups if r.period_type]
    tag_map = get_or_create_tag_uuids(all_tag_names, client=client)

    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    for r in rollups:
        if not r.updated_at:
            r.updated_at = now_iso

        r_tag_ids = []
        if r.period_type in tag_map:
            r_tag_ids.append(tag_map[r.period_type])

        records.append(r.to_fulcra_record(source_tag=source_tag, tag_ids=r_tag_ids))

    batch_size = 50
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        try:
            client.record_data_type(
                "MomentAnnotation",
                batch,
                api_version="v1alpha1",
            )
        except Exception as exc:
            raise RollupStoreError(
                f"Failed to write ActivityRollup batch to Fulcra: {exc}"
            ) from exc

    return rollups


def write_rollup(
    rollup: ActivityRollup,
    client: Optional[FulcraAPI] = None,
) -> ActivityRollup:
    """Convenience helper to write a single ActivityRollup record to Fulcra."""
    write_rollups([rollup], client=client)
    return rollup


def read_rollups(
    username: Optional[str] = None,
    period_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    client: Optional[FulcraAPI] = None,
    expected_min_count: int = 0,
    timeout_seconds: float = 0.0,
    poll_interval: float = 0.5,
) -> List[ActivityRollup]:
    """Read stored ActivityRollup records from Fulcra.

    Args:
        username: Optional username filter.
        period_type: Optional period type filter ("day", "week", "month", "quarter", "year").
        start_date: Optional start date string range filter ("YYYY-MM-DD").
        end_date: Optional end date string range filter ("YYYY-MM-DD").
        start_time: Start of Fulcra query window (defaults to 5 years ago).
        end_time: End of Fulcra query window (defaults to current time + 5 mins).
        client: Optional authenticated FulcraAPI client.
        expected_min_count: If > 0, poll until at least this many records exist.
        timeout_seconds: Max seconds to poll for expected_min_count.
        poll_interval: Interval between poll attempts.

    Returns:
        List of matching ActivityRollup objects whose date ranges overlap [start_date, end_date].
    """
    if client is None:
        client = get_fulcra_client()

    now = datetime.now(timezone.utc)
    if start_time is None:
        start_time = now - timedelta(days=365 * 5)
    if end_time is None:
        end_time = now + timedelta(minutes=5)

    start_iso = (
        start_time.isoformat() if isinstance(start_time, datetime) else start_time
    )
    end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

    start_poll_time = time.time()

    while True:
        try:
            annotations = _fetch_annotations_merged(
                client, ROLLUP_RECORD_TYPE, start_iso, end_iso
            )
        except Exception as exc:
            raise RollupStoreError(
                f"Failed to query rollups from Fulcra: {exc}"
            ) from exc

        results: List[ActivityRollup] = []

        for ann in annotations:
            note_str = ann.get("note")
            if not note_str:
                continue
            try:
                data = json.loads(note_str)
                if (
                    isinstance(data, dict)
                    and data.get("record_type") == ROLLUP_RECORD_TYPE
                ):
                    if username and data.get("username") != username:
                        continue
                    if period_type and data.get("period_type") != period_type:
                        continue
                    rec_start = data.get("start_date")
                    rec_end = data.get("end_date") or rec_start
                    if end_date and rec_start and rec_start > end_date:
                        continue
                    if start_date and rec_end and rec_end < start_date:
                        continue
                    rollup = ActivityRollup.from_dict(data, record_id=ann.get("id"))
                    results.append(rollup)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if len(results) >= expected_min_count:
            return results

        elapsed = time.time() - start_poll_time
        if elapsed >= timeout_seconds:
            return results

        time.sleep(poll_interval)


def clear_rollups(
    username: Optional[str] = None,
    period_type: Optional[str] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    client: Optional[FulcraAPI] = None,
) -> int:
    """Tombstone ActivityRollup records in Fulcra matching filters.

    Args:
        username: Optional username filter.
        period_type: Optional period_type filter.
        start_time: Optional query start time.
        end_time: Optional query end time.
        client: Optional authenticated FulcraAPI client.

    Returns:
        Number of tombstoned records.
    """
    if client is None:
        client = get_fulcra_client()

    now = datetime.now(timezone.utc)
    if start_time is None:
        start_time = now - timedelta(days=365 * 5)
    if end_time is None:
        end_time = now + timedelta(minutes=5)

    start_iso = (
        start_time.isoformat() if isinstance(start_time, datetime) else start_time
    )
    end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

    annotations = _fetch_annotations_merged(client, ROLLUP_RECORD_TYPE, start_iso, end_iso)
    tombstones = []

    for ann in annotations:
        note_str = ann.get("note")
        if not note_str:
            continue
        try:
            data = json.loads(note_str)
            if (
                isinstance(data, dict)
                and data.get("record_type") == ROLLUP_RECORD_TYPE
            ):
                if username and data.get("username") != username:
                    continue
                if period_type and data.get("period_type") != period_type:
                    continue
                ann_id = ann.get("id")
                if ann_id:
                    tombstones.append(
                        {"record_id": ann_id, "data_type": "MomentAnnotation"}
                    )
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    if tombstones:
        client.record_data_type("DeletedRecord", tombstones, api_version="v1alpha1")

    return len(tombstones)


def _parse_iso_date(val: Union[datetime, str]) -> datetime:
    """Parse date string ('YYYY-MM-DD') or ISO datetime into UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    val_clean = val.replace("Z", "+00:00")
    if len(val_clean) == 10:  # YYYY-MM-DD
        dt = datetime.strptime(val_clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromisoformat(val_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt


def generate_period_rollup(
    username: str,
    period_type: str,
    start_date: str,
    end_date: str,
    raw_records: Optional[List[GitHubActivityRaw]] = None,
    client: Optional[FulcraAPI] = None,
    llm_callable: Optional[Callable[..., Any]] = None,
) -> ActivityRollup:
    """Generate an ActivityRollup for a given period (day, week, month) from raw activity.

    Args:
        username: GitHub username.
        period_type: Period type ("day", "week", "month").
        start_date: Start date string ("YYYY-MM-DD").
        end_date: End date string ("YYYY-MM-DD").
        raw_records: Optional pre-fetched raw activity records. If None, queries Fulcra.
        client: Optional authenticated FulcraAPI client.
        llm_callable: Optional LLM model function (defaults to harness.providers.gemini.call_model).

    Returns:
        Generated ActivityRollup instance.
    """
    start_dt = _parse_iso_date(start_date)
    # end_dt is end of the end_date day (23:59:59.999999)
    end_dt_parsed = _parse_iso_date(end_date)
    end_dt = datetime(
        end_dt_parsed.year,
        end_dt_parsed.month,
        end_dt_parsed.day,
        23,
        59,
        59,
        999999,
        tzinfo=timezone.utc,
    )

    if raw_records is None:
        raw_records = read_raw_activities(username=username, client=client)

    # Filter raw records to those falling within [start_dt, end_dt] by timestamp
    matching_records: List[GitHubActivityRaw] = []
    for r in raw_records:
        if username and r.username != username:
            continue
        try:
            r_dt = _parse_iso_date(r.timestamp)
            if start_dt <= r_dt <= end_dt:
                matching_records.append(r)
        except (ValueError, TypeError):
            continue

    # Structured volume stats
    commit_count = sum(1 for r in matching_records if r.activity_type == "commit")
    pr_count = sum(1 for r in matching_records if r.activity_type == "pull_request")
    issue_count = sum(1 for r in matching_records if r.activity_type == "issue")
    comment_count = sum(
        1 for r in matching_records if r.activity_type in ("comment", "pr_review")
    )
    total_activities = len(matching_records)
    repos_touched = sorted(
        list({r.repo_name for r in matching_records if r.repo_name})
    )

    stats = {
        "commit_count": commit_count,
        "pr_count": pr_count,
        "issue_count": issue_count,
        "comment_count": comment_count,
        "total_activities": total_activities,
        "repos_touched": repos_touched,
    }

    # Provenance chain: raw activity record IDs
    source_record_ids: List[str] = []
    for r in matching_records:
        if r.id:
            source_record_ids.append(r.id)
        else:
            source_record_ids.append(
                f"{r.repo_name}:{r.activity_type}:{r.activity_id}"
            )

    # Narrative summary generation
    if not matching_records:
        summary = (
            f"No GitHub activity recorded for {username} during {period_type} "
            f"period ({start_date} to {end_date})."
        )
    else:
        if llm_callable is None:
            from harness.providers.gemini import call_model

            llm_callable = call_model

        activity_lines = []
        for r in matching_records:
            activity_lines.append(
                f"- [{r.activity_type}] in {r.repo_name} at {r.timestamp}: "
                f"{r.title_or_summary}"
                + (f" (body: {r.body[:150]}...)" if r.body and len(r.body) > 10 else "")
            )

        activity_text = "\n".join(activity_lines)

        prompt = (
            f"Summarize developer {username}'s GitHub activity for the {period_type} "
            f"period from {start_date} to {end_date}.\n\n"
            f"Stats: {commit_count} commits, {pr_count} PRs, {issue_count} issues, "
            f"{comment_count} reviews/comments across repos {repos_touched}.\n\n"
            f"Raw Activity Log:\n{activity_text}\n\n"
            "Write a concise, engaging 1-3 paragraph narrative summarizing key work, "
            "focus areas, repositories impacted, and notable features/fixes. "
            "Base your summary strictly on the activity details above."
        )

        try:
            response = llm_callable(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are an expert technical biographer building an engineering "
                    "journey summary."
                ),
            )
            if hasattr(response, "text") and response.text:
                summary = response.text.strip()
            elif isinstance(response, str) and response:
                summary = response.strip()
            else:
                summary = f"Activity summary for {username} ({start_date} to {end_date})."
        except Exception as exc:
            logger.warning(
                "LLM narrative summarization failed for %s (%s to %s); "
                "falling back to a stats-only summary. Error: %s",
                username,
                start_date,
                end_date,
                exc,
            )
            summary = (
                f"Activity summary for {username} ({start_date} to {end_date}): "
                f"{total_activities} activities across {len(repos_touched)} repos."
            )

    return ActivityRollup(
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
        username=username,
        summary=summary,
        stats=stats,
        source_record_ids=source_record_ids,
    )


def generate_layer_rollup(
    username: str,
    period_type: str,  # "quarter", "year"
    start_date: str,
    end_date: str,
    child_rollups: Optional[List[ActivityRollup]] = None,
    client: Optional[FulcraAPI] = None,
    llm_callable: Optional[Callable[..., Any]] = None,
    child_period_types: Optional[List[str]] = None,
) -> ActivityRollup:
    """Generate a higher-layer ActivityRollup (quarter, year) summarizing lower-layer rollups.

    Args:
        username: GitHub username.
        period_type: Target period type ("quarter" or "year").
        start_date: Start date string ("YYYY-MM-DD").
        end_date: End date string ("YYYY-MM-DD").
        child_rollups: Optional pre-fetched lower-layer rollups. If None, queries Fulcra.
        client: Optional authenticated FulcraAPI client.
        llm_callable: Optional LLM model function (defaults to harness.providers.gemini.call_model).
        child_period_types: List of acceptable child period types to aggregate
            from. Defaults to ["week", "month"] -- NOT "day": since
            generate_day_week_rollups always produces both a day AND a week
            rollup for every date in the recent-90-day window (see
            Milestone 4), including "day" here as well as "week" would
            double-count the same underlying activity. Pass an explicit
            list (e.g. ["week"] or ["month"]) to restrict further, e.g.
            when aggregating only the recent (week-based) or only the
            older (month-based) portion of a period that spans the
            90-day boundary.

    Returns:
        Generated ActivityRollup instance.
    """
    if child_period_types is None:
        child_period_types = ["week", "month"]

    start_dt = _parse_iso_date(start_date)
    end_dt_parsed = _parse_iso_date(end_date)
    end_dt = datetime(
        end_dt_parsed.year,
        end_dt_parsed.month,
        end_dt_parsed.day,
        23,
        59,
        59,
        999999,
        tzinfo=timezone.utc,
    )

    if child_rollups is None:
        child_rollups = read_rollups(username=username, client=client)

    matching_children: List[ActivityRollup] = []
    for c in child_rollups:
        if username and c.username != username:
            continue
        if c.period_type == period_type:
            continue
        if child_period_types and c.period_type not in child_period_types:
            continue
        try:
            c_start = _parse_iso_date(c.start_date)
            c_end = _parse_iso_date(c.end_date)
            if (
                (start_dt <= c_start <= end_dt)
                or (start_dt <= c_end <= end_dt)
                or (c_start <= start_dt and c_end >= end_dt)
            ):
                matching_children.append(c)
        except (ValueError, TypeError):
            continue

    matching_children.sort(key=lambda x: x.start_date)

    # Aggregate stats from child rollups
    commit_count = sum(c.stats.get("commit_count", 0) for c in matching_children)
    pr_count = sum(c.stats.get("pr_count", 0) for c in matching_children)
    issue_count = sum(c.stats.get("issue_count", 0) for c in matching_children)
    comment_count = sum(c.stats.get("comment_count", 0) for c in matching_children)
    total_activities = sum(c.stats.get("total_activities", 0) for c in matching_children)

    repos_set = set()
    for c in matching_children:
        for repo in c.stats.get("repos_touched", []):
            repos_set.add(repo)
    repos_touched = sorted(list(repos_set))

    stats = {
        "commit_count": commit_count,
        "pr_count": pr_count,
        "issue_count": issue_count,
        "comment_count": comment_count,
        "total_activities": total_activities,
        "repos_touched": repos_touched,
        "child_rollups_count": len(matching_children),
    }

    # Provenance chain: lower-layer ActivityRollup record IDs
    source_record_ids: List[str] = []
    for c in matching_children:
        if c.id:
            source_record_ids.append(c.id)
        else:
            source_record_ids.append(
                f"{c.period_type}:{c.username}:{c.start_date}_{c.end_date}"
            )

    if not matching_children:
        summary = (
            f"No prior activity rollups recorded for {username} during {period_type} "
            f"period ({start_date} to {end_date})."
        )
    else:
        if llm_callable is None:
            from harness.providers.gemini import call_model

            llm_callable = call_model

        child_lines = []
        for c in matching_children:
            child_lines.append(
                f"- Period {c.start_date} to {c.end_date} ({c.period_type}): {c.summary}"
            )
        child_text = "\n".join(child_lines)

        prompt = (
            f"Synthesize developer {username}'s engineering journey for the {period_type} "
            f"period from {start_date} to {end_date} based on the following lower-layer summaries.\n\n"
            f"Aggregate Stats: {commit_count} commits, {pr_count} PRs, {issue_count} issues, "
            f"{comment_count} reviews/comments across repos {repos_touched}.\n\n"
            f"Lower-layer Period Summaries:\n{child_text}\n\n"
            "Write an engaging, high-level 2-4 paragraph narrative capturing major themes, "
            "evolution of scope/focus, repository impact, and key accomplishments. "
            "Synthesize overarching progression rather than simply listing sub-periods."
        )

        try:
            response = llm_callable(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are an expert technical biographer building a high-level engineering "
                    "journey summary."
                ),
            )
            if hasattr(response, "text") and response.text:
                summary = response.text.strip()
            elif isinstance(response, str) and response:
                summary = response.strip()
            else:
                summary = (
                    f"{period_type.capitalize()} summary for {username} ({start_date} to {end_date})."
                )
        except Exception as exc:
            logger.warning(
                "LLM narrative synthesis failed for %s %s (%s to %s); "
                "falling back to stats summary. Error: %s",
                username,
                period_type,
                start_date,
                end_date,
                exc,
            )
            summary = (
                f"{period_type.capitalize()} summary for {username} ({start_date} to {end_date}): "
                f"{total_activities} activities across {len(repos_touched)} repos "
                f"from {len(matching_children)} lower-layer rollups."
            )

    return ActivityRollup(
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
        username=username,
        summary=summary,
        stats=stats,
        source_record_ids=source_record_ids,
    )


def generate_day_week_rollup_chunks(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    granularities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Divide a date range into day and/or week period chunks.

    Args:
        start_date: Start date string or datetime ("YYYY-MM-DD").
        end_date: End date string or datetime ("YYYY-MM-DD").
        granularities: List of period types to generate, e.g. ["day", "week"].

    Returns:
        List of chunk dicts: [{'period_type': 'day'|'week', 'start_date': ..., 'end_date': ...}]
    """
    if granularities is None:
        granularities = ["day", "week"]

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    if start_dt > end_dt:
        return []

    chunks: List[Dict[str, Any]] = []

    # Daily chunks
    if "day" in granularities:
        curr = start_dt
        while curr <= end_dt:
            date_str = curr.strftime("%Y-%m-%d")
            chunks.append(
                {
                    "period_type": "day",
                    "start_date": date_str,
                    "end_date": date_str,
                }
            )
            curr += timedelta(days=1)

    # Weekly chunks (7 days each)
    if "week" in granularities:
        curr = start_dt
        while curr <= end_dt:
            week_end = min(curr + timedelta(days=6), end_dt)
            chunks.append(
                {
                    "period_type": "week",
                    "start_date": curr.strftime("%Y-%m-%d"),
                    "end_date": week_end.strftime("%Y-%m-%d"),
                }
            )
            curr += timedelta(days=7)

    return chunks


def generate_month_rollup_chunks(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
) -> List[Dict[str, Any]]:
    """Divide a date range into calendar month period chunks.

    Args:
        start_date: Start date string or datetime ("YYYY-MM-DD").
        end_date: End date string or datetime ("YYYY-MM-DD").

    Returns:
        List of chunk dicts: [{'period_type': 'month', 'start_date': ..., 'end_date': ...}]
    """
    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    if start_dt > end_dt:
        return []

    chunks: List[Dict[str, Any]] = []
    curr = start_dt

    while curr <= end_dt:
        year = curr.year
        month = curr.month
        last_day = calendar.monthrange(year, month)[1]
        month_end_dt = datetime(year, month, last_day, tzinfo=timezone.utc)
        chunk_end = min(month_end_dt, end_dt)

        chunks.append(
            {
                "period_type": "month",
                "start_date": curr.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
            }
        )

        if month == 12:
            curr = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            curr = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    return chunks


def generate_quarter_rollup_chunks(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
) -> List[Dict[str, Any]]:
    """Divide a date range into calendar quarter period chunks.

    Args:
        start_date: Start date string or datetime ("YYYY-MM-DD").
        end_date: End date string or datetime ("YYYY-MM-DD").

    Returns:
        List of chunk dicts: [{'period_type': 'quarter', 'start_date': ..., 'end_date': ...}]
    """
    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    if start_dt > end_dt:
        return []

    chunks: List[Dict[str, Any]] = []
    curr = start_dt

    while curr <= end_dt:
        year = curr.year
        month = curr.month
        q_num = (month - 1) // 3 + 1
        q_end_month = q_num * 3
        last_day = calendar.monthrange(year, q_end_month)[1]
        q_end_dt = datetime(year, q_end_month, last_day, tzinfo=timezone.utc)
        chunk_end = min(q_end_dt, end_dt)

        chunks.append(
            {
                "period_type": "quarter",
                "start_date": curr.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
            }
        )

        if q_end_month == 12:
            curr = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            curr = datetime(year, q_end_month + 1, 1, tzinfo=timezone.utc)

    return chunks


def generate_year_rollup_chunks(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
) -> List[Dict[str, Any]]:
    """Divide a date range into calendar year period chunks.

    Args:
        start_date: Start date string or datetime ("YYYY-MM-DD").
        end_date: End date string or datetime ("YYYY-MM-DD").

    Returns:
        List of chunk dicts: [{'period_type': 'year', 'start_date': ..., 'end_date': ...}]
    """
    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)

    if start_dt > end_dt:
        return []

    chunks: List[Dict[str, Any]] = []
    curr = start_dt

    while curr <= end_dt:
        year = curr.year
        year_end_dt = datetime(year, 12, 31, tzinfo=timezone.utc)
        chunk_end = min(year_end_dt, end_dt)

        chunks.append(
            {
                "period_type": "year",
                "start_date": curr.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
            }
        )

        curr = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    return chunks


def build_rollup_work_items(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    granularities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build work items list for rollup generation, ordered chronologically.

    Returns:
        List of work items: [{'period_type': ..., 'start_date': ..., 'end_date': ...}]
    """
    if granularities is None:
        granularities = ["day", "week"]

    chunks: List[Dict[str, Any]] = []

    day_week_grans = [g for g in granularities if g in ("day", "week")]
    if day_week_grans:
        chunks.extend(
            generate_day_week_rollup_chunks(
                start_date, end_date, granularities=day_week_grans
            )
        )

    if "month" in granularities:
        chunks.extend(generate_month_rollup_chunks(start_date, end_date))

    if "quarter" in granularities:
        chunks.extend(generate_quarter_rollup_chunks(start_date, end_date))

    if "year" in granularities:
        chunks.extend(generate_year_rollup_chunks(start_date, end_date))

    # Sort by start_date, then by period_type
    return sorted(chunks, key=lambda x: (x["start_date"], x["period_type"]))


def generate_day_week_rollups(
    username: str,
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    granularities: Optional[List[str]] = None,
    client: Optional[FulcraAPI] = None,
    task_id: Optional[str] = None,
    interrupt_at_index: Optional[int] = None,
    stage: str = "day_week_rollups",
    llm_callable: Optional[Callable[..., Any]] = None,
    use_cache: bool = True,
    raw_records: Optional[List[GitHubActivityRaw]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute resumable day and week rollup generation for recent 90 days.

    Args:
        username: GitHub username.
        start_date: Start date ("YYYY-MM-DD").
        end_date: End date ("YYYY-MM-DD").
        granularities: Granularity list ("day", "week").
        client: Optional authenticated FulcraAPI client.
        task_id: Custom checkpoint task ID.
        interrupt_at_index: Simulated interrupt index.
        stage: Stage identifier for progress tracking.
        llm_callable: Optional custom LLM function.
        use_cache: Whether to use local memory cache for checkpoints.
        raw_records: Optional pre-fetched raw activity records.
        progress_callback: Optional callable forwarded to
            `checkpoint.process_with_checkpoint` -- see its docstring for
            the emitted event shape.

    Returns:
        Summary dict of execution.
    """
    if client is None:
        client = get_fulcra_client()

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    if not task_id:
        task_id = f"rollup_day_week:{username}:{start_str}_{end_str}"

    items = build_rollup_work_items(start_dt, end_dt, granularities)

    if raw_records is None:
        raw_records = read_raw_activities(username=username, client=client)

    generated_rollups: List[ActivityRollup] = []

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        rollup = generate_period_rollup(
            username=username,
            period_type=item["period_type"],
            start_date=item["start_date"],
            end_date=item["end_date"],
            raw_records=raw_records,
            client=client,
            llm_callable=llm_callable,
        )
        write_rollup(rollup, client=client)
        generated_rollups.append(rollup)

    checkpoint_result = process_with_checkpoint(
        task_id=task_id,
        items=items,
        process_fn=process_fn,
        client=client,
        interrupt_at_index=interrupt_at_index,
        stage=stage,
        use_cache=use_cache,
        progress_callback=progress_callback,
        metadata={
            "username": username,
            "start_date": start_str,
            "end_date": end_str,
        },
    )

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "completed_items_count": checkpoint_result["completed_items_count"],
        "total_items": len(items),
        "rollups_generated": len(generated_rollups),
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
    }


def generate_month_rollups(
    username: str,
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    client: Optional[FulcraAPI] = None,
    task_id: Optional[str] = None,
    interrupt_at_index: Optional[int] = None,
    stage: str = "month_rollups",
    llm_callable: Optional[Callable[..., Any]] = None,
    use_cache: bool = True,
    raw_records: Optional[List[GitHubActivityRaw]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute resumable month rollup generation for history older than 90 days.

    Args:
        username: GitHub username.
        start_date: Start date ("YYYY-MM-DD").
        end_date: End date ("YYYY-MM-DD").
        client: Optional authenticated FulcraAPI client.
        task_id: Custom checkpoint task ID.
        interrupt_at_index: Simulated interrupt index.
        stage: Stage identifier.
        llm_callable: Optional custom LLM function.
        use_cache: Whether to use local memory cache for checkpoints.
        raw_records: Optional pre-fetched raw activity records.
        progress_callback: Optional callable forwarded to
            `checkpoint.process_with_checkpoint` -- see its docstring for
            the emitted event shape.

    Returns:
        Summary dict of execution.
    """
    if client is None:
        client = get_fulcra_client()

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    if not task_id:
        task_id = f"rollup_month:{username}:{start_str}_{end_str}"

    items = generate_month_rollup_chunks(start_dt, end_dt)

    if raw_records is None:
        raw_records = read_raw_activities(username=username, client=client)

    generated_rollups: List[ActivityRollup] = []

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        rollup = generate_period_rollup(
            username=username,
            period_type="month",
            start_date=item["start_date"],
            end_date=item["end_date"],
            raw_records=raw_records,
            client=client,
            llm_callable=llm_callable,
        )
        write_rollup(rollup, client=client)
        generated_rollups.append(rollup)

    checkpoint_result = process_with_checkpoint(
        task_id=task_id,
        items=items,
        process_fn=process_fn,
        client=client,
        interrupt_at_index=interrupt_at_index,
        stage=stage,
        use_cache=use_cache,
        progress_callback=progress_callback,
        metadata={
            "username": username,
            "start_date": start_str,
            "end_date": end_str,
        },
    )

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "completed_items_count": checkpoint_result["completed_items_count"],
        "total_items": len(items),
        "rollups_generated": len(generated_rollups),
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
    }


def generate_layer_rollups(
    username: str,
    period_type: str,  # "quarter" or "year"
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    client: Optional[FulcraAPI] = None,
    task_id: Optional[str] = None,
    interrupt_at_index: Optional[int] = None,
    stage: Optional[str] = None,
    llm_callable: Optional[Callable[..., Any]] = None,
    use_cache: bool = True,
    child_rollups: Optional[List[ActivityRollup]] = None,
    child_period_types: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute resumable higher-layer (quarter, year) rollup generation from child rollups.

    Args:
        username: GitHub username.
        period_type: "quarter" or "year".
        start_date: Start date ("YYYY-MM-DD").
        end_date: End date ("YYYY-MM-DD").
        client: Optional authenticated FulcraAPI client.
        task_id: Custom checkpoint task ID.
        interrupt_at_index: Simulated interrupt index.
        stage: Stage identifier.
        llm_callable: Optional custom LLM function.
        use_cache: Whether to use local memory cache for checkpoints.
        child_rollups: Optional pre-fetched lower-layer rollups.
        child_period_types: List of acceptable child period types to
            aggregate from -- see generate_layer_rollup's docstring.
            Defaults to ["week", "month"] (excludes "day" to avoid
            double-counting against week rollups covering the same
            dates).
        progress_callback: Optional callable forwarded to
            `checkpoint.process_with_checkpoint` -- see its docstring for
            the emitted event shape.

    Returns:
        Summary dict of execution.
    """
    if client is None:
        client = get_fulcra_client()

    start_dt = _parse_iso_date(start_date)
    end_dt = _parse_iso_date(end_date)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    if not stage:
        stage = f"{period_type}_rollups"

    if not task_id:
        task_id = f"rollup_{period_type}:{username}:{start_str}_{end_str}"

    if period_type == "quarter":
        items = generate_quarter_rollup_chunks(start_dt, end_dt)
    elif period_type == "year":
        items = generate_year_rollup_chunks(start_dt, end_dt)
    else:
        raise ValueError(f"Unsupported period_type for layer rollups: {period_type}")

    if child_rollups is None:
        child_rollups = read_rollups(username=username, client=client)

    generated_rollups: List[ActivityRollup] = []

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        rollup = generate_layer_rollup(
            username=username,
            period_type=item["period_type"],
            start_date=item["start_date"],
            end_date=item["end_date"],
            child_rollups=child_rollups,
            client=client,
            llm_callable=llm_callable,
            child_period_types=child_period_types,
        )
        write_rollup(rollup, client=client)
        generated_rollups.append(rollup)

    checkpoint_result = process_with_checkpoint(
        task_id=task_id,
        items=items,
        process_fn=process_fn,
        client=client,
        interrupt_at_index=interrupt_at_index,
        stage=stage,
        use_cache=use_cache,
        progress_callback=progress_callback,
        metadata={
            "username": username,
            "period_type": period_type,
            "start_date": start_str,
            "end_date": end_str,
        },
    )

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "completed_items_count": checkpoint_result["completed_items_count"],
        "total_items": len(items),
        "rollups_generated": len(generated_rollups),
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
    }
