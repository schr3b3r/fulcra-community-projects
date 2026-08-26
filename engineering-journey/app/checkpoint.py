"""Fulcra-backed durable progress checkpointing for GitHub activity backfills.

This module implements the `GitHubBackfillProgress` record type and functions
to read/write backfill progress to Fulcra as `DurationAnnotation` records tagged with
custom Fulcra data type source IDs.
This ensures resumability across process restarts or failures without
re-processing previously completed work or skipping items.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, Callable, Dict, List, Optional, Union

from fulcra_api.core import FulcraAPI
from fulcra_client import get_fulcra_client
from fulcra_types import get_custom_source_tag

RECORD_TYPE = "GitHubBackfillProgress"
# Real, permanent constraint discovered while migrating this type to
# DurationAnnotation (Milestone 17): this project's real Fulcra account
# already has a custom data type literally named "GitHubBackfillProgress"
# created back in Milestone 9, permanently classified as a MomentAnnotation
# -- Fulcra does not support changing a custom type's base annotation type
# after creation. Reusing the same catalog name here would silently resolve
# to that old MomentAnnotation-based UUID (get_or_create_custom_data_type
# looks up by name first) regardless of the annotation_type this module
# requests, causing DurationAnnotation-shaped writes/reads to silently fail
# against a type whose real underlying schema is still MomentAnnotation.
# A new catalog name is required for a genuinely new DurationAnnotation-
# based type. Per this project's explicit design decision (see Milestone
# 17's Decisions Log entry), old MomentAnnotation-shaped
# "GitHubBackfillProgress" records under the old name are deliberately
# abandoned, not migrated -- checkpoints are ephemeral process state, not
# durable historical data worth preserving across this type change.
CATALOG_TYPE_NAME = "GitHubBackfillProgressV2"

# In-memory cache for fast same-process checkpoint lookups
_IN_MEMORY_CHECKPOINTS: Dict[str, "GitHubBackfillProgress"] = {}


def clear_memory_cache() -> None:
    """Clear the process-local in-memory checkpoint cache."""
    global _IN_MEMORY_CHECKPOINTS
    _IN_MEMORY_CHECKPOINTS.clear()


class CheckpointError(Exception):
    """Base exception for checkpoint errors."""


class SimulatedInterruptError(Exception):
    """Exception raised when a work loop is interrupted by simulated process termination."""


def _format_iso_timestamp(timestamp_str: str, end_of_day: bool = False) -> str:
    """Ensure a date or ISO timestamp string is formatted as ISO 8601 UTC timestamp.

    Args:
        timestamp_str: a plain "YYYY-MM-DD" date or a full ISO timestamp.
        end_of_day: when `timestamp_str` is a plain date (no time
            component), format it as 23:59:59 instead of 00:00:00. This
            matters specifically for DurationAnnotation's `end_time`:
            Fulcra's backend has been confirmed (empirically, not just in
            theory) to silently drop a DurationAnnotation record whose
            `start_time` and `end_time` are exactly equal (a genuine
            zero-length duration) -- a write call reports success, but
            the record is never returned by any later read, filtered or
            not. Any single-day period whose start_date == end_date
            would otherwise format both bounds to the same
            "YYYY-MM-DDT00:00:00Z" instant and silently vanish; using
            end-of-day for the end bound keeps the duration genuinely
            positive.
    """
    if len(timestamp_str) == 10 and timestamp_str[4] == "-" and timestamp_str[7] == "-":
        return f"{timestamp_str}T23:59:59Z" if end_of_day else f"{timestamp_str}T00:00:00Z"
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


@dataclass
class GitHubBackfillProgress:
    """Represents the progress of a backfill task or sub-task stored in Fulcra."""

    task_id: str
    stage: str = "raw_ingestion"
    repo_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_processed_item: Optional[str] = None
    last_processed_index: int = -1
    completed_items_count: int = 0
    total_items: Optional[int] = None
    status: str = "not_started"  # not_started | in_progress | completed | failed
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None  # Fulcra record ID if available

    def __post_init__(self) -> None:
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize progress data into a JSON-compatible dictionary."""
        return {
            "record_type": RECORD_TYPE,
            "task_id": self.task_id,
            "stage": self.stage,
            "repo_name": self.repo_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "last_processed_item": self.last_processed_item,
            "last_processed_index": self.last_processed_index,
            "completed_items_count": self.completed_items_count,
            "total_items": self.total_items,
            "status": self.status,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], record_id: Optional[str] = None
    ) -> "GitHubBackfillProgress":
        """Reconstruct a GitHubBackfillProgress instance from a dictionary."""
        return cls(
            task_id=data["task_id"],
            stage=data.get("stage", "raw_ingestion"),
            repo_name=data.get("repo_name"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            last_processed_item=data.get("last_processed_item"),
            last_processed_index=data.get("last_processed_index", -1),
            completed_items_count=data.get("completed_items_count", 0),
            total_items=data.get("total_items"),
            status=data.get("status", "not_started"),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata", {}),
            id=record_id,
        )

    def to_fulcra_record(self, source_tag: Optional[str] = None) -> Dict[str, Any]:
        """Format the progress data into a Fulcra DurationAnnotation record dict."""
        if self.start_date and self.end_date:
            recorded_at = {
                "start_time": _format_iso_timestamp(self.start_date),
                "end_time": _format_iso_timestamp(self.end_date, end_of_day=True),
            }
        else:
            # No item-level date range available for this checkpoint (e.g.
            # a top-level task marker rather than a per-item update) --
            # fall back to updated_at, but with a real, non-zero
            # end_time. A DurationAnnotation whose start_time == end_time
            # exactly is silently dropped by Fulcra's backend (confirmed
            # empirically: the write call reports success, but the record
            # is never returned by any later read) -- one second is an
            # arbitrary but real, always-positive offset, not a
            # meaningful duration in its own right.
            start_dt = (
                datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
                if self.updated_at
                else datetime.now(timezone.utc)
            )
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(seconds=1)
            recorded_at = {
                "start_time": start_dt.isoformat().replace("+00:00", "Z"),
                "end_time": end_dt.isoformat().replace("+00:00", "Z"),
            }
        rec: Dict[str, Any] = {
            "recorded_at": recorded_at,
            "note": json.dumps(self.to_dict()),
        }
        if source_tag:
            rec["sources"] = [source_tag]
        return rec


def write_checkpoint(
    progress: GitHubBackfillProgress, client: Optional[FulcraAPI] = None
) -> GitHubBackfillProgress:
    """Write or update a progress checkpoint record in Fulcra.

    Args:
        progress: The GitHubBackfillProgress instance to record.
        client: Optional authenticated FulcraAPI client. If omitted, uses get_fulcra_client().

    Returns:
        The updated GitHubBackfillProgress instance.
    """
    if client is None:
        client = get_fulcra_client()

    source_tag = get_custom_source_tag(
        CATALOG_TYPE_NAME, client=client, annotation_type="duration"
    )
    progress.updated_at = datetime.now(timezone.utc).isoformat()
    record = progress.to_fulcra_record(source_tag=source_tag)

    try:
        client.record_data_type(
            "DurationAnnotation",
            [record],
            api_version="v1alpha1",
        )
    except Exception as exc:
        raise CheckpointError(f"Failed to write checkpoint to Fulcra: {exc}") from exc

    # Update process-local memory cache
    _IN_MEMORY_CHECKPOINTS[progress.task_id] = progress

    return progress


def _fetch_annotations_merged(
    client: FulcraAPI,
    record_type_name: str,
    start_iso: str,
    end_iso: str,
    base_type: str = "MomentAnnotation",
    catalog_type_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Helper to query Fulcra using custom type source tag first, with untagged fallback if tagged query fails.

    Args:
        record_type_name: the value of the JSON `note.record_type` field
            written into each record -- used to filter the untagged
            fallback query down to just this record kind.
        catalog_type_name: the REAL custom data type's catalog name used
            to resolve/create the type and its source tag. Defaults to
            `record_type_name` when not given, which is correct for every
            record kind except GitHubBackfillProgress (see
            checkpoint.CATALOG_TYPE_NAME's own docstring/comment for why
            that one specific type needs a different catalog name than
            its content-level record_type tag).
    """
    if catalog_type_name is None:
        catalog_type_name = record_type_name

    annotation_type = "duration" if base_type == "DurationAnnotation" else "moment"
    source_tag = get_custom_source_tag(
        catalog_type_name, client=client, annotation_type=annotation_type
    )

    fetch_fn = (
        client.duration_annotations
        if base_type == "DurationAnnotation"
        else client.moment_annotations
    )

    annotations: List[Dict[str, Any]] = []
    tagged_failed = False

    try:
        annotations = fetch_fn(start_iso, end_iso, source=source_tag)
    except Exception:
        tagged_failed = True

    if tagged_failed:
        try:
            annotations_all = fetch_fn(start_iso, end_iso)
            for ann in annotations_all:
                if not isinstance(ann, dict):
                    continue
                note_str = ann.get("note")
                if not note_str:
                    continue
                try:
                    data = json.loads(note_str)
                    if isinstance(data, dict) and data.get("record_type") == record_type_name:
                        annotations.append(ann)
                except Exception:
                    continue
        except Exception as exc:
            raise exc

    by_id: Dict[str, Dict[str, Any]] = {}
    for ann in annotations:
        if isinstance(ann, dict) and "id" in ann:
            by_id[ann["id"]] = ann

    return list(by_id.values())


def read_checkpoint(
    task_id: str,
    client: Optional[FulcraAPI] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    use_cache: bool = True,
    timeout_seconds: float = 0.0,
    poll_interval: float = 0.5,
) -> Optional[GitHubBackfillProgress]:
    """Read the latest progress checkpoint for a given task_id from Fulcra.

    Args:
        task_id: Unique identifier for the checkpoint task.
        client: Optional authenticated FulcraAPI client.
        start_time: Start of query window (defaults to 3 years ago).
        end_time: End of query window (defaults to current time + 5 mins).
        use_cache: If True, check in-memory cache before querying Fulcra API.
        timeout_seconds: Max seconds to poll Fulcra API if not found immediately.
        poll_interval: Seconds between poll attempts when timeout_seconds > 0.

    Returns:
        The latest GitHubBackfillProgress instance if found, or None.
    """
    if use_cache and task_id in _IN_MEMORY_CHECKPOINTS:
        return _IN_MEMORY_CHECKPOINTS[task_id]

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
            annotations = _fetch_annotations_merged(
                client,
                RECORD_TYPE,
                start_iso,
                end_iso,
                base_type="DurationAnnotation",
                catalog_type_name=CATALOG_TYPE_NAME,
            )
        except Exception as exc:
            raise CheckpointError(
                f"Failed to query checkpoints from Fulcra: {exc}"
            ) from exc

        matching_checkpoints: List[GitHubBackfillProgress] = []

        for ann in annotations:
            note_str = ann.get("note")
            if not note_str:
                continue
            try:
                data = json.loads(note_str)
                if (
                    isinstance(data, dict)
                    and data.get("record_type") == RECORD_TYPE
                    and data.get("task_id") == task_id
                ):
                    checkpoint = GitHubBackfillProgress.from_dict(
                        data, record_id=ann.get("id")
                    )
                    matching_checkpoints.append(checkpoint)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if matching_checkpoints:
            # Sort by last_processed_index descending, then updated_at descending
            matching_checkpoints.sort(
                key=lambda c: (c.last_processed_index, c.updated_at or ""),
                reverse=True,
            )
            result = matching_checkpoints[0]
            _IN_MEMORY_CHECKPOINTS[task_id] = result
            return result

        elapsed = time.time() - start_poll_time
        if elapsed >= timeout_seconds:
            break

        time.sleep(poll_interval)

    return None


def list_checkpoints(
    client: Optional[FulcraAPI] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
    expected_task_ids: Optional[List[str]] = None,
    timeout_seconds: float = 0.0,
    poll_interval: float = 0.5,
    use_cache: bool = True,
) -> Dict[str, GitHubBackfillProgress]:
    """Retrieve the latest progress checkpoint for each task_id found in Fulcra.

    Args:
        client: Optional authenticated FulcraAPI client.
        start_time: Start of query window (defaults to 3 years ago).
        end_time: End of query window (defaults to current time + 5 mins).
        expected_task_ids: If given, poll (up to timeout_seconds) until all
            of these task_ids are present in the result, rather than
            returning after a single query.
        timeout_seconds: Max seconds to poll for expected_task_ids to appear.
        poll_interval: Seconds between poll attempts.
        use_cache: Include in-memory cached checkpoints in initial state.

    Returns:
        A dict of task_id -> latest GitHubBackfillProgress for that task.
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
        latest_by_task: Dict[str, GitHubBackfillProgress] = {}
        if use_cache:
            latest_by_task.update(_IN_MEMORY_CHECKPOINTS)

        annotations = _fetch_annotations_merged(
            client,
            RECORD_TYPE,
            start_iso,
            end_iso,
            base_type="DurationAnnotation",
            catalog_type_name=CATALOG_TYPE_NAME,
        )

        for ann in annotations:
            note_str = ann.get("note")
            if not note_str:
                continue
            try:
                data = json.loads(note_str)
                if isinstance(data, dict) and data.get("record_type") == RECORD_TYPE:
                    task_id = data.get("task_id")
                    if not task_id:
                        continue
                    cp = GitHubBackfillProgress.from_dict(data, record_id=ann.get("id"))
                    if task_id not in latest_by_task or (
                        cp.last_processed_index,
                        cp.updated_at or "",
                    ) > (
                        latest_by_task[task_id].last_processed_index,
                        latest_by_task[task_id].updated_at or "",
                    ):
                        latest_by_task[task_id] = cp
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if expected_task_ids is None or all(
            tid in latest_by_task for tid in expected_task_ids
        ):
            return latest_by_task

        elapsed = time.time() - start_poll_time
        if elapsed >= timeout_seconds:
            return latest_by_task

        time.sleep(poll_interval)


def clear_checkpoint(
    task_id: str,
    client: Optional[FulcraAPI] = None,
    start_time: Optional[Union[datetime, str]] = None,
    end_time: Optional[Union[datetime, str]] = None,
) -> int:
    """Tombstone all progress checkpoint annotations matching task_id in Fulcra."""

    # Remove from memory cache if present
    _IN_MEMORY_CHECKPOINTS.pop(task_id, None)

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

    annotations = _fetch_annotations_merged(
        client,
        RECORD_TYPE,
        start_iso,
        end_iso,
        base_type="DurationAnnotation",
        catalog_type_name=CATALOG_TYPE_NAME,
    )
    tombstones = []

    for ann in annotations:
        note_str = ann.get("note")
        if not note_str:
            continue
        try:
            data = json.loads(note_str)
            if (
                isinstance(data, dict)
                and data.get("record_type") == RECORD_TYPE
                and data.get("task_id") == task_id
            ):
                ann_id = ann.get("id")
                if ann_id:
                    tombstones.append(
                        {"record_id": ann_id, "data_type": "DurationAnnotation"}
                    )
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    if tombstones:
        client.record_data_type("DeletedRecord", tombstones, api_version="v1alpha1")

    return len(tombstones)


def process_with_checkpoint(
    task_id: str,
    items: List[Any],
    process_fn: Callable[[Any, int], None],
    client: Optional[FulcraAPI] = None,
    interrupt_at_index: Optional[int] = None,
    stage: str = "raw_ingestion",
    repo_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
    timeout_seconds: float = 5.0,
    checkpoint_interval: int = 1,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Process a list of work items with automatic checkpointing and resumption support.

    Args:
        task_id: Unique task identifier.
        items: List of work items to process.
        process_fn: Callable invoked for each item as process_fn(item, item_index).
        client: Optional authenticated FulcraAPI client.
        interrupt_at_index: Optional 0-based index at which to simulate a process failure/interrupt.
        stage: Backfill stage identifier.
        repo_name: Repository name if applicable.
        metadata: Extra metadata dictionary for the checkpoint.
        use_cache: Whether to use in-memory cache when reading checkpoints.
        timeout_seconds: Timeout for querying checkpoints from Fulcra.
        checkpoint_interval: Write checkpoint after processing every N items.
        progress_callback: Optional callable invoked with a structured event dict
            at meaningful points during processing (task start, resume, each
            completed item, and task completion) -- see the emitted event
            "kind" values ("task_started", "item_completed", "task_completed")
            for the full event shape. Never raises out of this function: a
            failing callback (e.g. a broken terminal renderer) is caught and
            ignored so it can never break the actual backfill/rollup work.

    Returns:
        Summary dict containing status, processed_indices, and completed count.

    Raises:
        SimulatedInterruptError: If interrupt_at_index is reached.
    """

    def _emit(event: Dict[str, Any]) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(event)
        except Exception:
            # Progress reporting must never be able to break real work.
            pass

    if client is None:
        client = get_fulcra_client()

    existing = read_checkpoint(
        task_id, client=client, use_cache=use_cache, timeout_seconds=timeout_seconds
    )

    if existing and existing.status == "completed":
        _emit(
            {
                "kind": "task_already_completed",
                "task_id": task_id,
                "stage": stage,
                "total": len(items),
            }
        )
        return {
            "status": "completed",
            "completed_items_count": len(items),
            "processed_indices": [],
            "resumed_from_index": None,
        }

    start_index = 0
    if existing and existing.last_processed_index >= 0:
        start_index = existing.last_processed_index + 1

    progress = existing or GitHubBackfillProgress(
        task_id=task_id,
        stage=stage,
        repo_name=repo_name,
        total_items=len(items),
        status="in_progress",
        metadata=metadata or {},
    )
    progress.status = "in_progress"
    progress.total_items = len(items)

    _emit(
        {
            "kind": "task_started",
            "task_id": task_id,
            "stage": stage,
            "total": len(items),
            "resumed_from_index": start_index if start_index > 0 else None,
        }
    )

    processed_indices: List[int] = []

    for idx in range(start_index, len(items)):
        item = items[idx]
        if isinstance(item, dict):
            progress.start_date = item.get("start_date")
            progress.end_date = item.get("end_date")
        else:
            progress.start_date = None
            progress.end_date = None

        if interrupt_at_index is not None and idx == interrupt_at_index:
            # Save checkpoint before raising interrupt
            if processed_indices:
                write_checkpoint(progress, client=client)
            raise SimulatedInterruptError(
                f"Simulated process interruption at index {idx} (item: {items[idx]})"
            )

        process_fn(item, idx)
        processed_indices.append(idx)

        progress.last_processed_index = idx
        progress.last_processed_item = str(item)
        progress.completed_items_count = idx + 1

        if (
            checkpoint_interval <= 1
            or idx % checkpoint_interval == 0
            or idx == len(items) - 1
        ):
            write_checkpoint(progress, client=client)

        _emit(
            {
                "kind": "item_completed",
                "task_id": task_id,
                "stage": stage,
                "index": idx + 1,  # 1-based, "item N of total"
                "total": len(items),
                "item": item,
            }
        )

    progress.status = "completed"
    write_checkpoint(progress, client=client)

    _emit(
        {
            "kind": "task_completed",
            "task_id": task_id,
            "stage": stage,
            "total": len(items),
            "completed_items_count": progress.completed_items_count,
        }
    )

    return {
        "status": "completed",
        "completed_items_count": len(items),
        "processed_indices": processed_indices,
        "resumed_from_index": start_index if start_index > 0 else None,
    }
