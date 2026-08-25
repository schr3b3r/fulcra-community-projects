"""GitHub raw activity record model and Fulcra persistence for Engineering Journey."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from fulcra_types import get_custom_source_tag
from checkpoint import (
    process_with_checkpoint,
    read_checkpoint,
    write_checkpoint,
    _fetch_annotations_merged,
)
from github_client import GitHubClient

RAW_RECORD_TYPE = "GitHubActivityRaw"
logger = logging.getLogger("github_activity")


class ActivityStoreError(Exception):
    """Exception raised for errors in raw activity persistence."""


def compute_deterministic_activity_id(
    activity_type: str, activity_id: str, repo_name: str
) -> str:
    """Compute a deterministic UUID string for a GitHub activity item."""
    key = f"{activity_type}:{activity_id}:{repo_name}"
    return str(uuid.UUID(bytes=hashlib.md5(key.encode("utf-8")).digest()))


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
class GitHubActivityRaw:
    """Represents a single raw GitHub activity record (commit, PR, issue, review, comment)."""

    activity_type: str  # "commit", "pull_request", "issue", "pr_review", "comment"
    activity_id: str  # sha for commits, issue/PR number or node id
    repo_name: str  # owner/repo
    username: str  # github login
    timestamp: str  # ISO 8601 string of activity creation/commit date
    title_or_summary: str  # commit headline or PR/issue title
    body: Optional[str] = None  # commit message, PR body, or issue body
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[str] = None
    id: Optional[str] = None  # Fulcra record ID if saved/retrieved

    def __post_init__(self) -> None:
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize activity data into a JSON-compatible dictionary."""
        return {
            "record_type": RAW_RECORD_TYPE,
            "activity_type": self.activity_type,
            "activity_id": self.activity_id,
            "repo_name": self.repo_name,
            "username": self.username,
            "timestamp": self.timestamp,
            "title_or_summary": self.title_or_summary,
            "body": self.body,
            "url": self.url,
            "metadata": self.metadata,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], record_id: Optional[str] = None
    ) -> "GitHubActivityRaw":
        """Reconstruct a GitHubActivityRaw instance from a dictionary."""
        return cls(
            activity_type=data["activity_type"],
            activity_id=data["activity_id"],
            repo_name=data["repo_name"],
            username=data["username"],
            timestamp=data["timestamp"],
            title_or_summary=data["title_or_summary"],
            body=data.get("body"),
            url=data.get("url"),
            metadata=data.get("metadata", {}),
            updated_at=data.get("updated_at"),
            id=record_id,
        )

    def to_fulcra_record(self, source_tag: Optional[str] = None) -> Dict[str, Any]:
        """Format into a Fulcra MomentAnnotation record dict."""
        record_id = self.id or compute_deterministic_activity_id(
            self.activity_type, self.activity_id, self.repo_name
        )
        rec = {
            "id": record_id,
            "recorded_at": _format_iso_timestamp(self.timestamp),
            "note": json.dumps(self.to_dict()),
        }
        if source_tag:
            rec["sources"] = [source_tag]
        return rec


def write_raw_activities(
    activities: List[GitHubActivityRaw],
    client: Optional[FulcraAPI] = None,
) -> List[GitHubActivityRaw]:
    """Write a list of GitHubActivityRaw records to Fulcra as MomentAnnotation records.

    Args:
        activities: List of GitHubActivityRaw objects to record.
        client: Optional authenticated FulcraAPI client.

    Returns:
        The input list of GitHubActivityRaw objects.
    """
    if not activities:
        return []

    if client is None:
        client = get_fulcra_client()

    source_tag = get_custom_source_tag(RAW_RECORD_TYPE, client=client)
    now_iso = datetime.now(timezone.utc).isoformat()
    records = []
    for act in activities:
        if not act.updated_at:
            act.updated_at = now_iso
        records.append(act.to_fulcra_record(source_tag=source_tag))

    # Batch write in chunks of 50
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
            raise ActivityStoreError(
                f"Failed to write activity batch to Fulcra: {exc}"
            ) from exc

    return activities


def read_raw_activities(
    username: Optional[str] = None,
    repo_name: Optional[str] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    client: Optional[FulcraAPI] = None,
    expected_min_count: int = 0,
    timeout_seconds: float = 0.0,
    poll_interval: float = 0.5,
) -> List[GitHubActivityRaw]:
    """Read stored GitHubActivityRaw records from Fulcra.

    Args:
        username: Optional username filter.
        repo_name: Optional repository name filter.
        start_time: Start of query window (defaults to 5 years ago).
        end_time: End of query window (defaults to current time + 5 mins).
        client: Optional authenticated FulcraAPI client.
        expected_min_count: If > 0, poll (up to timeout_seconds) until at
            least this many matching records are found.
        timeout_seconds: Max seconds to poll for expected_min_count.
        poll_interval: Seconds between poll attempts.

    Returns:
        List of matching GitHubActivityRaw records.
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
                client, RAW_RECORD_TYPE, start_iso, end_iso
            )
        except Exception as exc:
            raise ActivityStoreError(
                f"Failed to query activities from Fulcra: {exc}"
            ) from exc

        results: List[GitHubActivityRaw] = []

        for ann in annotations:
            note_str = ann.get("note")
            if not note_str:
                continue
            try:
                data = json.loads(note_str)
                if isinstance(data, dict) and data.get("record_type") == RAW_RECORD_TYPE:
                    if username and data.get("username") != username:
                        continue
                    if repo_name and data.get("repo_name") != repo_name:
                        continue
                    act = GitHubActivityRaw.from_dict(data, record_id=ann.get("id"))
                    results.append(act)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if len(results) >= expected_min_count:
            return results

        elapsed = time.time() - start_poll_time
        if elapsed >= timeout_seconds:
            return results

        time.sleep(poll_interval)


def clear_raw_activities(
    username: Optional[str] = None,
    repo_name: Optional[str] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    client: Optional[FulcraAPI] = None,
) -> int:
    """Tombstone GitHubActivityRaw records in Fulcra.

    Args:
        username: Optional username filter.
        repo_name: Optional repository name filter.
        start_time: Start of query window.
        end_time: End of query window.
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

    annotations = _fetch_annotations_merged(client, RAW_RECORD_TYPE, start_iso, end_iso)
    tombstones = []

    for ann in annotations:
        note_str = ann.get("note")
        if not note_str:
            continue
        try:
            data = json.loads(note_str)
            if isinstance(data, dict) and data.get("record_type") == RAW_RECORD_TYPE:
                if username and data.get("username") != username:
                    continue
                if repo_name and data.get("repo_name") != repo_name:
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


def _parse_datetime(val: Union[datetime, str]) -> datetime:
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_period_chunks(
    start_date: Union[datetime, str],
    end_date: Union[datetime, str],
    recent_days: int = 90,
    recent_step_days: int = 7,
    older_step_days: int = 30,
) -> List[Dict[str, Any]]:
    """Divide a date window into period chunks with decaying granularity.

    The most recent `recent_days` (default 90) are chunked at `recent_step_days` (default 7/weekly).
    Older periods are chunked at `older_step_days` (default 30/monthly).

    Returns:
        List of dicts: [{'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD', 'granularity': 'monthly'|'weekly'}]
    """
    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)

    if start_dt >= end_dt:
        return []

    cutoff_90d = end_dt - timedelta(days=recent_days)
    chunks: List[Dict[str, Any]] = []

    # Older window: monthly chunks (~30 days)
    curr = start_dt
    while curr < cutoff_90d:
        chunk_end = min(curr + timedelta(days=older_step_days - 1), cutoff_90d - timedelta(days=1))
        if chunk_end < curr:
            break
        chunks.append(
            {
                "start_date": curr.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
                "granularity": "monthly",
            }
        )
        curr = chunk_end + timedelta(days=1)

    # Recent window: weekly chunks (~7 days)
    curr = max(cutoff_90d, start_dt)
    while curr < end_dt:
        chunk_end = min(curr + timedelta(days=recent_step_days - 1), end_dt)
        if chunk_end < curr:
            break
        chunks.append(
            {
                "start_date": curr.strftime("%Y-%m-%d"),
                "end_date": chunk_end.strftime("%Y-%m-%d"),
                "granularity": "weekly",
            }
        )
        curr = chunk_end + timedelta(days=1)

    return chunks


def build_backfill_work_items(
    repo_names: List[str], period_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Build the ordered work item list combining repositories and period chunks.

    Work items are ordered chronologically by period, then by repository name.

    Returns:
        List of work item dicts: [{'repo_name': ..., 'start_date': ..., 'end_date': ..., 'granularity': ...}]
    """
    items: List[Dict[str, Any]] = []
    sorted_repos = sorted(repo_names)

    for chunk in period_chunks:
        for repo in sorted_repos:
            items.append(
                {
                    "repo_name": repo,
                    "start_date": chunk["start_date"],
                    "end_date": chunk["end_date"],
                    "granularity": chunk.get("granularity", "unknown"),
                }
            )

    return items


def _ingest_single_item_activity(
    gh_client: GitHubClient,
    repo_name: str,
    start_date: str,
    end_date: str,
    client: Optional[FulcraAPI] = None,
) -> int:
    """Fetch commits, PRs, issues for a single repo and date range, storing in Fulcra."""
    username = gh_client.username
    activities: List[GitHubActivityRaw] = []

    # Fetch commits
    commits = gh_client.fetch_commits(repo_name, start_date, end_date)
    for c in commits:
        msg = c.get("commit", {}).get("message", "")
        summary = msg.split("\n")[0] if msg else ""
        activities.append(
            GitHubActivityRaw(
                activity_type="commit",
                activity_id=c.get("sha", ""),
                repo_name=repo_name,
                username=username,
                timestamp=c.get("commit", {}).get("author", {}).get("date")
                or datetime.now(timezone.utc).isoformat(),
                title_or_summary=summary,
                body=msg,
                url=c.get("html_url"),
                metadata={
                    "sha": c.get("sha"),
                    "author": c.get("commit", {}).get("author"),
                },
            )
        )

    # Fetch PRs
    prs = gh_client.fetch_pull_requests(repo_name, start_date, end_date)
    for pr in prs:
        activities.append(
            GitHubActivityRaw(
                activity_type="pull_request",
                activity_id=str(pr.get("number", "")),
                repo_name=repo_name,
                username=username,
                timestamp=pr.get("created_at")
                or datetime.now(timezone.utc).isoformat(),
                title_or_summary=pr.get("title", ""),
                body=pr.get("body"),
                url=pr.get("html_url"),
                metadata={
                    "number": pr.get("number"),
                    "state": pr.get("state"),
                },
            )
        )

    # Fetch Issues
    issues = gh_client.fetch_issues(repo_name, start_date, end_date)
    for iss in issues:
        activities.append(
            GitHubActivityRaw(
                activity_type="issue",
                activity_id=str(iss.get("number", "")),
                repo_name=repo_name,
                username=username,
                timestamp=iss.get("created_at")
                or datetime.now(timezone.utc).isoformat(),
                title_or_summary=iss.get("title", ""),
                body=iss.get("body"),
                url=iss.get("html_url"),
                metadata={
                    "number": iss.get("number"),
                    "state": iss.get("state"),
                },
            )
        )

    if activities:
        write_raw_activities(activities, client=client)

    return len(activities)


def ingest_github_activity(
    gh_client: GitHubClient,
    start_date: str,
    end_date: str,
    repo_names: Optional[List[str]] = None,
    client: Optional[FulcraAPI] = None,
    stage: str = "raw_ingestion",
    interrupt_at_index: Optional[int] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingest GitHub activity for a date range into Fulcra, using checkpointing.

    Args:
        gh_client: Configured GitHubClient instance.
        start_date: Start date string (e.g. '2026-06-01').
        end_date: End date string (e.g. '2026-07-01').
        repo_names: Explicit list of repositories. If None, queries contributionsCollection.
        client: Optional authenticated FulcraAPI client.
        stage: Backfill stage name.
        interrupt_at_index: Index at which to simulate a process failure/interrupt.
        task_id: Optional custom checkpoint task ID.

    Returns:
        Summary dict of ingestion execution.
    """
    if client is None:
        client = get_fulcra_client()

    username = gh_client.username

    if repo_names is None:
        contributions = gh_client.get_contributions_collection(start_date, end_date)
        repo_names = contributions.get("repositories", [])

    if not task_id:
        task_id = f"raw_ingestion:{username}:{start_date[:10]}_{end_date[:10]}"

    items = [
        {"repo_name": repo, "start_date": start_date, "end_date": end_date}
        for repo in sorted(repo_names)
    ]

    ingested_count = 0

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        nonlocal ingested_count
        count = _ingest_single_item_activity(
            gh_client,
            repo_name=item["repo_name"],
            start_date=item["start_date"],
            end_date=item["end_date"],
            client=client,
        )
        ingested_count += count

    checkpoint_result = process_with_checkpoint(
        task_id=task_id,
        items=items,
        process_fn=process_fn,
        client=client,
        interrupt_at_index=interrupt_at_index,
        stage=stage,
        metadata={
            "repo_names": sorted(repo_names),
            "total_repos": len(repo_names),
            "username": username,
        },
    )

    completed_count = checkpoint_result["completed_items_count"]

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "completed_items_count": completed_count,
        "total_items": len(items),
        "repos_processed": [it["repo_name"] for it in items[:completed_count]],
        "activities_count": ingested_count,
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
    }


def backfill_full_github_activity(
    gh_client: GitHubClient,
    start_date: Optional[Union[datetime, str]] = None,
    end_date: Optional[Union[datetime, str]] = None,
    repo_names: Optional[List[str]] = None,
    client: Optional[FulcraAPI] = None,
    stage: str = "full_3year_backfill",
    interrupt_at_index: Optional[int] = None,
    task_id: Optional[str] = None,
    use_cache: bool = True,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Execute a full ~3-year multi-repo, multi-period activity backfill with checkpointing.

    Pre-checks all discovered repositories using `gh_client.has_author_activity` across the
    full date range to filter out repositories with zero author activity prior to creating
    per-period work items.

    Args:
        gh_client: Configured GitHubClient instance.
        start_date: Start date (defaults to ~3 years before end_date).
        end_date: End date (defaults to current time in UTC).
        repo_names: Explicit list of repositories. If None, enumerates across full window.
        client: Optional authenticated FulcraAPI client.
        stage: Backfill stage identifier.
        interrupt_at_index: Optional 0-based index at which to simulate process failure.
        task_id: Custom checkpoint task ID.
        use_cache: Whether to use process-local memory cache when reading checkpoints.
        progress_callback: Optional callable forwarded straight through to
            `checkpoint.process_with_checkpoint` -- see that function's
            docstring for the event shape emitted per work item.

    Returns:
        Summary dict of backfill execution.
    """
    if client is None:
        client = get_fulcra_client()

    now = datetime.now(timezone.utc)
    if end_date is None:
        end_dt = now
    else:
        end_dt = _parse_datetime(end_date)

    if start_date is None:
        start_dt = end_dt - timedelta(days=365 * 3)
    else:
        start_dt = _parse_datetime(start_date)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    if repo_names is None:
        repo_names = gh_client.enumerate_repositories(start_dt, end_dt)

    if not task_id:
        task_id = f"backfill_3yr:{gh_client.username}:{start_str}_{end_str}"

    period_chunks = generate_period_chunks(start_dt, end_dt)
    sorted_discovered = sorted(repo_names)

    # Check for existing completed checkpoint and perform delta evaluation if new repos are found
    existing = read_checkpoint(
        task_id, client=client, use_cache=use_cache, timeout_seconds=5.0
    )

    if existing and existing.status == "completed":
        stored_repos = (
            existing.metadata.get("repo_names") if existing.metadata else None
        )
        if stored_repos is not None and isinstance(stored_repos, list):
            stored_set = set(stored_repos)
        else:
            # Legacy checkpoint missing repo_names: treat coverage as unknown (empty set)
            # so any discovered repo is ingested via delta backfill.
            logger.info(
                "Existing completed checkpoint %s lacks stored repo_names metadata; treating all %d discovered repos as unverified.",
                task_id,
                len(sorted_discovered),
            )
            stored_set = set()

        new_repos = [r for r in sorted_discovered if r not in stored_set]

        if not new_repos:
            return {
                "status": "completed",
                "task_id": task_id,
                "is_delta": False,
                "completed_items_count": len(sorted_discovered),
                "total_items": len(sorted_discovered),
                "repo_names": sorted_discovered,
                "active_repo_names": sorted(
                    existing.metadata.get("active_repo_names", sorted_discovered)
                    if existing.metadata
                    else sorted_discovered
                ),
                "repos_skipped_no_activity": existing.metadata.get(
                    "repos_skipped_no_activity", []
                )
                if existing.metadata
                else [],
                "period_chunks_count": len(period_chunks),
                "processed_indices": [],
                "resumed_from_index": None,
                "activities_count": 0,
            }

        # New repos discovered that were not covered by prior completed checkpoint.
        # Run author activity pre-check across full range on new_repos.
        active_new_repos = [
            r for r in new_repos if gh_client.has_author_activity(r, start_dt, end_dt)
        ]
        skipped_new_repos = [r for r in new_repos if r not in active_new_repos]

        if skipped_new_repos:
            logger.info(
                "Delta backfill skipped %d new repos with no author activity in range: %s",
                len(skipped_new_repos),
                skipped_new_repos,
            )

        if not active_new_repos:
            # All newly discovered repos had 0 author activity. Update parent metadata so they are marked evaluated.
            all_repos = sorted(list(stored_set | set(new_repos)))
            existing.metadata["repo_names"] = all_repos
            existing.metadata["total_repos"] = len(all_repos)
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            write_checkpoint(existing, client=client)

            return {
                "status": "completed",
                "task_id": task_id,
                "is_delta": True,
                "new_repos": new_repos,
                "active_new_repos": [],
                "repos_skipped_no_activity": skipped_new_repos,
                "completed_items_count": 0,
                "total_items": 0,
                "repo_names": sorted_discovered,
                "period_chunks_count": len(period_chunks),
                "processed_indices": [],
                "resumed_from_index": None,
                "activities_count": 0,
            }

        delta_hash = hashlib.sha256(
            ",".join(sorted(active_new_repos)).encode("utf-8")
        ).hexdigest()[:8]
        delta_task_id = f"{task_id}:delta:{delta_hash}"
        delta_items = build_backfill_work_items(active_new_repos, period_chunks)

        logger.info(
            "Found %d new repos with author activity not covered by prior backfill task %s: %s; ingesting delta now.",
            len(active_new_repos),
            task_id,
            active_new_repos,
        )
        print(
            f"Found {len(active_new_repos)} new repos with author activity not covered by prior backfill: {active_new_repos}. Ingesting delta now..."
        )

        ingested_count = 0

        def process_fn(item: Dict[str, Any], idx: int) -> None:
            nonlocal ingested_count
            count = _ingest_single_item_activity(
                gh_client,
                repo_name=item["repo_name"],
                start_date=item["start_date"],
                end_date=item["end_date"],
                client=client,
            )
            ingested_count += count

        delta_checkpoint_result = process_with_checkpoint(
            task_id=delta_task_id,
            items=delta_items,
            process_fn=process_fn,
            client=client,
            interrupt_at_index=interrupt_at_index,
            stage=f"{stage}_delta",
            use_cache=use_cache,
            progress_callback=progress_callback,
            metadata={
                "parent_task_id": task_id,
                "repo_names": sorted(new_repos),
                "active_repo_names": sorted(active_new_repos),
                "repos_skipped_no_activity": sorted(skipped_new_repos),
                "total_repos": len(new_repos),
                "total_periods": len(period_chunks),
                "username": gh_client.username,
                "is_delta": True,
            },
        )

        if delta_checkpoint_result["status"] == "completed":
            all_repos = sorted(list(stored_set | set(new_repos)))
            existing.metadata["repo_names"] = all_repos
            existing.metadata["total_repos"] = len(all_repos)
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            write_checkpoint(existing, client=client)

        return {
            "status": delta_checkpoint_result["status"],
            "task_id": task_id,
            "is_delta": True,
            "delta_task_id": delta_task_id,
            "new_repos": new_repos,
            "active_new_repos": active_new_repos,
            "repos_skipped_no_activity": skipped_new_repos,
            "completed_items_count": delta_checkpoint_result["completed_items_count"],
            "total_items": len(delta_items),
            "repo_names": sorted_discovered,
            "period_chunks_count": len(period_chunks),
            "processed_indices": delta_checkpoint_result["processed_indices"],
            "resumed_from_index": delta_checkpoint_result.get("resumed_from_index"),
            "activities_count": ingested_count,
        }

    # Normal backfill (first run or resuming an in-progress parent task)
    active_repo_names = [
        r for r in sorted_discovered if gh_client.has_author_activity(r, start_dt, end_dt)
    ]
    skipped_repo_names = [r for r in sorted_discovered if r not in active_repo_names]

    if skipped_repo_names:
        logger.info(
            "Skipped %d repos with no author activity in range %s to %s: %s",
            len(skipped_repo_names),
            start_str,
            end_str,
            skipped_repo_names,
        )
        print(
            f"Skipped {len(skipped_repo_names)} repos with no author activity in range: {skipped_repo_names}"
        )

    items = build_backfill_work_items(active_repo_names, period_chunks)
    ingested_count = 0

    def process_fn(item: Dict[str, Any], idx: int) -> None:
        nonlocal ingested_count
        count = _ingest_single_item_activity(
            gh_client,
            repo_name=item["repo_name"],
            start_date=item["start_date"],
            end_date=item["end_date"],
            client=client,
        )
        ingested_count += count

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
            "repo_names": sorted_discovered,
            "active_repo_names": sorted(active_repo_names),
            "repos_skipped_no_activity": sorted(skipped_repo_names),
            "total_repos": len(sorted_discovered),
            "total_periods": len(period_chunks),
            "username": gh_client.username,
        },
    )

    return {
        "status": checkpoint_result["status"],
        "task_id": task_id,
        "is_delta": False,
        "completed_items_count": checkpoint_result["completed_items_count"],
        "total_items": len(items),
        "repo_names": sorted_discovered,
        "active_repo_names": active_repo_names,
        "repos_skipped_no_activity": skipped_repo_names,
        "period_chunks_count": len(period_chunks),
        "processed_indices": checkpoint_result["processed_indices"],
        "resumed_from_index": checkpoint_result.get("resumed_from_index"),
        "activities_count": ingested_count,
    }
