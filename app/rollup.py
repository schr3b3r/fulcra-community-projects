"""Rollup record model and generation logic for Engineering Journey.

Computes day and week activity rollups from raw GitHub activity records, generating
structured volume stats, LLM narrative summaries, and explicit provenance chains
stored durably in Fulcra.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from checkpoint import process_with_checkpoint
from github_activity import GitHubActivityRaw, read_raw_activities

ROLLUP_RECORD_TYPE = "ActivityRollup"

logger = logging.getLogger(__name__)


class RollupStoreError(Exception):
    """Exception raised for errors in ActivityRollup persistence or generation."""


@dataclass
class ActivityRollup:
    """Represents a period rollup (day, week, etc.) summarizing GitHub activity."""

    period_type: str  # "day", "week" ("month", "quarter", "year" in Milestone 5)
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

    def to_fulcra_record(self) -> Dict[str, Any]:
        """Format into a Fulcra MomentAnnotation record dict."""
        return {
            "recorded_at": self.updated_at or datetime.now(timezone.utc).isoformat(),
            "note": json.dumps(self.to_dict()),
        }


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

    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    for r in rollups:
        if not r.updated_at:
            r.updated_at = now_iso
        records.append(r.to_fulcra_record())

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
        period_type: Optional period type filter ("day", "week").
        start_date: Optional start date string filter ("YYYY-MM-DD").
        end_date: Optional end date string filter ("YYYY-MM-DD").
        start_time: Start of Fulcra query window (defaults to 3 years ago).
        end_time: End of Fulcra query window (defaults to current time + 5 mins).
        client: Optional authenticated FulcraAPI client.
        expected_min_count: If > 0, poll until at least this many records exist.
        timeout_seconds: Max seconds to poll for expected_min_count.
        poll_interval: Interval between poll attempts.

    Returns:
        List of matching ActivityRollup objects.
    """
    if client is None:
        client = get_fulcra_client()

    now = datetime.now(timezone.utc)
    if start_time is None:
        start_time = now - timedelta(days=365 * 3)
    if end_time is None:
        end_time = now + timedelta(minutes=5)

    start_iso = (
        start_time.isoformat() if isinstance(start_time, datetime) else start_time
    )
    end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

    start_poll_time = time.time()

    while True:
        try:
            annotations = client.moment_annotations(start_iso, end_iso)
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
                    if start_date and data.get("start_date") != start_date:
                        continue
                    if end_date and data.get("end_date") != end_date:
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
        start_time = now - timedelta(days=365 * 3)
    if end_time is None:
        end_time = now + timedelta(minutes=5)

    start_iso = (
        start_time.isoformat() if isinstance(start_time, datetime) else start_time
    )
    end_iso = end_time.isoformat() if isinstance(end_time, datetime) else end_time

    annotations = client.moment_annotations(start_iso, end_iso)
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
    """Generate an ActivityRollup for a given period and user.

    Args:
        username: GitHub username.
        period_type: Period type ("day" or "week").
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
        # Fetch raw activities for username from Fulcra
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

    # Provenance chain
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


def build_rollup_work_items(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    granularities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build work items list for rollup generation, ordered chronologically.

    Returns:
        List of work items: [{'period_type': ..., 'start_date': ..., 'end_date': ...}]
    """
    chunks = generate_day_week_rollup_chunks(start_date, end_date, granularities)
    # Sort by start_date, then by period_type ("day" before "week")
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

    # Pre-fetch raw records if not provided
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
