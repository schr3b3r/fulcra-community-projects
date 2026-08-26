"""Notability signal computation and persistence for Engineering Journey.

Computes personal-baseline-relative notability scores and categorical flags
(high volume, firsts/new repos, focus switches, streaks, gaps) for ActivityRollup periods,
recording structured signals durably in Fulcra as custom data types with provenance links back to rollups.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from fulcra_types import get_custom_source_tag, get_or_create_tag_uuids
from checkpoint import process_with_checkpoint, _fetch_annotations_merged
from rollup import ActivityRollup, read_rollups

NOTABILITY_RECORD_TYPE = "NotabilitySignal"

logger = logging.getLogger(__name__)


class NotabilityStoreError(Exception):
    """Exception raised for errors in NotabilitySignal persistence or computation."""


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
class NotabilitySignal:
    """Represents a computed notability signal for a period rollup."""

    period_type: str  # "day", "week", "month", "quarter", "year"
    start_date: str  # ISO date string "YYYY-MM-DD"
    end_date: str  # ISO date string "YYYY-MM-DD"
    username: str  # GitHub username
    notability_score: float  # Score between 0.0 (routine) and 1.0 (highly notable)
    flags: List[str] = field(default_factory=list)  # e.g. ["high_volume", "new_repo", "focus_switch", "streak", "low_volume_gap"]
    explanation: str = ""  # Human-readable explanation text
    source_rollup_id: str = ""  # ID or reference of the ActivityRollup source
    baseline_stats: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[str] = None
    id: Optional[str] = None  # Fulcra record ID if saved/retrieved

    def __post_init__(self) -> None:
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize NotabilitySignal into a dictionary."""
        return {
            "record_type": NOTABILITY_RECORD_TYPE,
            "period_type": self.period_type,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "username": self.username,
            "notability_score": round(self.notability_score, 3),
            "flags": self.flags,
            "explanation": self.explanation,
            "source_rollup_id": self.source_rollup_id,
            "baseline_stats": self.baseline_stats,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], record_id: Optional[str] = None
    ) -> "NotabilitySignal":
        """Reconstruct a NotabilitySignal instance from a dictionary."""
        return cls(
            period_type=data["period_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            username=data["username"],
            notability_score=float(data.get("notability_score", 0.0)),
            flags=data.get("flags", []),
            explanation=data.get("explanation", ""),
            source_rollup_id=data.get("source_rollup_id", ""),
            baseline_stats=data.get("baseline_stats", {}),
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
                "agent.engineering-journey.notability",
                source_tag,
            ]
        return rec


def write_notability_signals(
    signals: List[NotabilitySignal],
    client: Optional[FulcraAPI] = None,
) -> List[NotabilitySignal]:
    """Write NotabilitySignal records to Fulcra as MomentAnnotation records.

    Args:
        signals: List of NotabilitySignal instances to record.
        client: Optional authenticated FulcraAPI client.

    Returns:
        The input list of NotabilitySignal objects.
    """
    if not signals:
        return []

    if client is None:
        client = get_fulcra_client()

    source_tag = get_custom_source_tag(NOTABILITY_RECORD_TYPE, client=client)

    all_tag_names: List[str] = []
    for s in signals:
        if s.period_type:
            all_tag_names.append(s.period_type)
        if s.flags:
            all_tag_names.extend(s.flags)

    tag_map = get_or_create_tag_uuids(all_tag_names, client=client)

    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        if not s.updated_at:
            s.updated_at = now_iso

        s_tag_names = []
        if s.period_type:
            s_tag_names.append(s.period_type)
        if s.flags:
            s_tag_names.extend(s.flags)

        s_tag_ids = [tag_map[tn] for tn in s_tag_names if tn in tag_map]
        records.append(s.to_fulcra_record(source_tag=source_tag, tag_ids=s_tag_ids))

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
            raise NotabilityStoreError(
                f"Failed to write NotabilitySignal batch to Fulcra: {exc}"
            ) from exc

    return signals


def write_notability_signal(
    signal: NotabilitySignal,
    client: Optional[FulcraAPI] = None,
) -> NotabilitySignal:
    """Convenience helper to write a single NotabilitySignal record to Fulcra."""
    write_notability_signals([signal], client=client)
    return signal


def read_notability_signals(
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
) -> List[NotabilitySignal]:
    """Read stored NotabilitySignal records from Fulcra.

    Args:
        username: Optional username filter.
        period_type: Optional period type filter.
        start_date: Optional start date string range filter ("YYYY-MM-DD").
        end_date: Optional end date string range filter ("YYYY-MM-DD").
        start_time: Start of Fulcra query window (defaults to 5 years ago).
        end_time: End of Fulcra query window (defaults to current time + 5 mins).
        client: Optional authenticated FulcraAPI client.
        expected_min_count: If > 0, poll until at least this many records exist.
        timeout_seconds: Max seconds to poll for expected_min_count.
        poll_interval: Interval between poll attempts.

    Returns:
        List of matching NotabilitySignal objects whose date ranges overlap [start_date, end_date].
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
                client, NOTABILITY_RECORD_TYPE, start_iso, end_iso
            )
        except Exception as exc:
            raise NotabilityStoreError(
                f"Failed to query notability signals from Fulcra: {exc}"
            ) from exc

        results: List[NotabilitySignal] = []

        for ann in annotations:
            note_str = ann.get("note")
            if not note_str:
                continue
            try:
                data = json.loads(note_str)
                if (
                    isinstance(data, dict)
                    and data.get("record_type") == NOTABILITY_RECORD_TYPE
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
                    signal = NotabilitySignal.from_dict(data, record_id=ann.get("id"))
                    results.append(signal)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if len(results) >= expected_min_count:
            return results

        elapsed = time.time() - start_poll_time
        if elapsed >= timeout_seconds:
            return results

        time.sleep(poll_interval)


def clear_notability_signals(
    username: Optional[str] = None,
    period_type: Optional[str] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    client: Optional[FulcraAPI] = None,
) -> int:
    """Tombstone NotabilitySignal records in Fulcra matching filters."""
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

    annotations = _fetch_annotations_merged(client, NOTABILITY_RECORD_TYPE, start_iso, end_iso)
    tombstones = []

    for ann in annotations:
        note_str = ann.get("note")
        if not note_str:
            continue
        try:
            data = json.loads(note_str)
            if (
                isinstance(data, dict)
                and data.get("record_type") == NOTABILITY_RECORD_TYPE
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


def compute_baseline_stats(rollups: List[ActivityRollup]) -> Dict[str, Any]:
    """Compute personal baseline statistical metrics across a list of rollups of the same period_type.

    Args:
        rollups: List of ActivityRollup instances to compute baseline stats over.

    Returns:
        Dict containing mean_total_activities, std_total_activities, mean_commits, etc.
    """
    if not rollups:
        return {
            "rollup_count": 0,
            "mean_total_activities": 0.0,
            "std_total_activities": 0.0,
            "mean_commit_count": 0.0,
            "mean_pr_count": 0.0,
        }

    totals = [r.stats.get("total_activities", 0) for r in rollups]
    commits = [r.stats.get("commit_count", 0) for r in rollups]
    prs = [r.stats.get("pr_count", 0) for r in rollups]

    n = len(totals)
    mean_total = sum(totals) / n
    mean_commit = sum(commits) / n
    mean_pr = sum(prs) / n

    if n > 1:
        variance = sum((x - mean_total) ** 2 for x in totals) / (n - 1)
        std_total = math.sqrt(variance)
    else:
        std_total = 0.0

    return {
        "rollup_count": n,
        "mean_total_activities": round(mean_total, 2),
        "std_total_activities": round(std_total, 2),
        "mean_commit_count": round(mean_commit, 2),
        "mean_pr_count": round(mean_pr, 2),
    }


def _get_dominant_repo(rollup: ActivityRollup) -> Optional[str]:
    """Determine the primary/dominant repository touched during a rollup period."""
    repos = rollup.stats.get("repos_touched", [])
    if not repos:
        return None
    return repos[0]


def generate_notability_signal(
    target_rollup: ActivityRollup,
    history_rollups: List[ActivityRollup],
    llm_callable: Optional[Callable[..., Any]] = None,
) -> NotabilitySignal:
    """Compute personal-baseline notability score, flags, and explanation for a target rollup period.

    Args:
        target_rollup: The ActivityRollup instance to evaluate.
        history_rollups: Complete set of rollups for baseline comparison (same period_type & username).
        llm_callable: Optional custom LLM function if narrative phrasing is desired.

    Returns:
        NotabilitySignal instance with scores, categorical flags, explanation, and baseline stats.
    """
    # 1. Filter history rollups to matching period_type and username
    matching_history = [
        r
        for r in history_rollups
        if r.period_type == target_rollup.period_type
        and r.username == target_rollup.username
    ]

    # Compute baseline using other history periods if available, so target spike doesn't distort baseline
    other_history = [
        r
        for r in matching_history
        if not (
            r.start_date == target_rollup.start_date
            and r.end_date == target_rollup.end_date
        )
    ]
    baseline_history = other_history if other_history else matching_history
    baseline = compute_baseline_stats(baseline_history)

    target_total = target_rollup.stats.get("total_activities", 0)
    target_commits = target_rollup.stats.get("commit_count", 0)
    target_prs = target_rollup.stats.get("pr_count", 0)
    target_repos = target_rollup.stats.get("repos_touched", [])

    mean_total = baseline["mean_total_activities"]
    std_total = baseline["std_total_activities"]

    flags: List[str] = []
    explanation_parts: List[str] = []

    # Sort history rollups chronologically by start_date for sequence checks
    sorted_history = sorted(matching_history, key=lambda x: x.start_date)

    # Find prior rollups (strictly earlier start_date)
    prior_rollups = [r for r in sorted_history if r.start_date < target_rollup.start_date]

    # Signal Check 1: High Volume / Variance
    activity_ratio = target_total / max(1.0, mean_total) if mean_total > 0 else 1.0

    if mean_total > 0 and (
        activity_ratio >= 1.8 or (std_total > 0 and target_total >= mean_total + 1.5 * std_total)
    ):
        flags.append("high_volume")
        explanation_parts.append(
            f"High activity volume ({target_total} total activities, "
            f"{activity_ratio:.1f}x baseline average of {mean_total:.1f})"
        )

    # Signal Check 2: Low Volume / Gap
    # A gap is significant if prior stretch was active (mean_total >= 2.0 or recent prior total >= 2.0)
    # and this period has zero or unusually low activity relative to baseline
    prior_avg_total = (
        sum(r.stats.get("total_activities", 0) for r in prior_rollups[-3:]) / len(prior_rollups[-3:])
        if prior_rollups
        else mean_total
    )

    if (prior_avg_total >= 2.0 or mean_total >= 2.0) and (
        target_total == 0 or (activity_ratio <= 0.25 and prior_avg_total >= 3.0)
    ):
        flags.append("low_volume_gap")
        explanation_parts.append(
            f"Activity gap ({target_total} activities following an active stretch with "
            f"average {prior_avg_total:.1f} activities/period)"
        )

    # Signal Check 3: Firsts (New Repository)
    prior_repos = set()
    for p in prior_rollups:
        for r in p.stats.get("repos_touched", []):
            prior_repos.add(r)

    new_repos = sorted([r for r in target_repos if r not in prior_repos]) if prior_rollups else []
    if new_repos:
        flags.append("new_repo")
        explanation_parts.append(
            f"First activity in new repository/repositories: {', '.join(new_repos)}"
        )

    # Signal Check 4: Focus Switch (Dominant repo changed from prior period)
    if prior_rollups:
        immediately_prior = prior_rollups[-1]
        prior_dominant = _get_dominant_repo(immediately_prior)
        target_dominant = _get_dominant_repo(target_rollup)

        if (
            prior_dominant
            and target_dominant
            and prior_dominant != target_dominant
            and target_total > 0
            and immediately_prior.stats.get("total_activities", 0) > 0
        ):
            flags.append("focus_switch")
            explanation_parts.append(
                f"Primary repo focus switched from '{prior_dominant}' to '{target_dominant}'"
            )

    # Signal Check 5: Streak (Sustained active stretch across 3+ consecutive periods)
    if len(prior_rollups) >= 2:
        last_2_prior = prior_rollups[-2:]
        streak_threshold = max(1.0, 0.75 * mean_total)
        if (
            target_total >= streak_threshold
            and all(r.stats.get("total_activities", 0) >= streak_threshold for r in last_2_prior)
        ):
            flags.append("streak")
            explanation_parts.append(
                f"Sustained activity streak (3 consecutive {target_rollup.period_type}s at or above baseline)"
            )

    # Calculate Notability Score (0.0 to 1.0)
    # Base score derived from volume relative to baseline
    base_score = min(0.4, (activity_ratio - 0.5) * 0.2) if activity_ratio >= 0.5 else 0.05

    # Incremental score boosts per detected flag
    flag_weights = {
        "high_volume": 0.35,
        "new_repo": 0.25,
        "focus_switch": 0.20,
        "low_volume_gap": 0.30,
        "streak": 0.20,
    }

    score_boost = sum(flag_weights.get(f, 0.1) for f in flags)
    raw_score = base_score + score_boost
    final_score = max(0.05, min(1.0, raw_score))

    # Format final explanation
    if explanation_parts:
        explanation = "; ".join(explanation_parts) + "."
    else:
        explanation = (
            f"Routine activity level aligned with personal baseline "
            f"({target_total} total activities vs {mean_total:.1f} baseline average)."
        )

    source_rollup_id = (
        target_rollup.id
        if target_rollup.id
        else f"{target_rollup.period_type}:{target_rollup.username}:{target_rollup.start_date}"
    )

    return NotabilitySignal(
        period_type=target_rollup.period_type,
        start_date=target_rollup.start_date,
        end_date=target_rollup.end_date,
        username=target_rollup.username,
        notability_score=final_score,
        flags=flags,
        explanation=explanation,
        source_rollup_id=source_rollup_id,
        baseline_stats={
            "mean_total_activities": baseline["mean_total_activities"],
            "std_total_activities": baseline["std_total_activities"],
            "activity_ratio": round(activity_ratio, 2),
            "target_total_activities": target_total,
        },
    )


def generate_notability_signals(
    username: str,
    period_type: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client: Optional[FulcraAPI] = None,
    task_id: Optional[str] = None,
    interrupt_at_index: Optional[int] = None,
    stage: str = "notability_signals",
    use_cache: bool = True,
    rollups: Optional[List[ActivityRollup]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute resumable NotabilitySignal generation across rollups for a user and period_type.

    Args:
        username: GitHub username.
        period_type: Period type ("day", "week", "month", "quarter", "year").
        start_date: Optional start date string ("YYYY-MM-DD").
        end_date: Optional end date string ("YYYY-MM-DD").
        client: Optional authenticated FulcraAPI client.
        task_id: Custom checkpoint task ID.
        interrupt_at_index: Simulated interrupt index.
        stage: Stage identifier for progress tracking.
        use_cache: Whether to use local memory cache for checkpoints.
        rollups: Optional pre-fetched list of ActivityRollup records.
        progress_callback: Optional callable forwarded to
            `checkpoint.process_with_checkpoint` -- see its docstring for
            the emitted event shape.

    Returns:
        Summary dict of execution.
    """
    if client is None:
        client = get_fulcra_client()

    if rollups is None:
        rollups = read_rollups(
            username=username,
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            client=client,
        )

    # Filter to matching period_type & username, sorted chronologically
    matching_rollups = [
        r for r in rollups if r.period_type == period_type and r.username == username
    ]
    if start_date:
        matching_rollups = [r for r in matching_rollups if r.start_date >= start_date]
    if end_date:
        matching_rollups = [r for r in matching_rollups if r.end_date <= end_date]

    matching_rollups.sort(key=lambda x: x.start_date)

    if not task_id:
        task_id = f"notability_{period_type}:{username}:{start_date or 'all'}_{end_date or 'all'}"

    work_items = [
        {
            "period_type": r.period_type,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "index": i,
        }
        for i, r in enumerate(matching_rollups)
    ]

    generated_signals: List[NotabilitySignal] = []

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        target_rollup = matching_rollups[idx]
        signal = generate_notability_signal(
            target_rollup=target_rollup,
            history_rollups=matching_rollups,
        )
        write_notability_signal(signal, client=client)
        generated_signals.append(signal)

    checkpoint_result = process_with_checkpoint(
        task_id=task_id,
        items=work_items,
        process_fn=process_fn,
        client=client,
        interrupt_at_index=interrupt_at_index,
        stage=stage,
        use_cache=use_cache,
        progress_callback=progress_callback,
        metadata={
            "username": username,
            "period_type": period_type,
        },
    )

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "completed_items_count": checkpoint_result["completed_items_count"],
        "total_items": len(work_items),
        "signals_generated": len(generated_signals),
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
    }
