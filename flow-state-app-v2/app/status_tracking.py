"""Processing status tracking: records each pipeline file's lifecycle
(received -> processing -> processed -> marker_detection -> extracting ->
published / failed) as queryable Fulcra annotation data.

See app/features/processing_status_tracking.md for the full spec. Uses
the Fulcra Python SDK's MomentAnnotation type directly (create/query),
never the CLI or subprocess calls.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fulcra_api.core import FulcraAPI

logger = logging.getLogger(__name__)

STATUS_TAG_PREFIX = "flow-state-status"
STAGE_TAG_PREFIX = "stage"

VALID_STAGES = {
    "received",
    "queued",
    "processing",
    "processed",
    "marker_detection",
    "extracting",
    "published",
    "failed",
}


class StatusTrackingError(Exception):
    """Raised when a status record cannot be written or read."""


def record_status(
    client: FulcraAPI,
    session_id: str,
    stage: str,
    detail: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    """Record a pipeline status update for a session as a MomentAnnotation.

    Args:
        client: an authenticated FulcraAPI client (see fulcra_client.py).
        session_id: identifies which session/file this status is for.
        stage: one of VALID_STAGES (e.g. "received", "processing",
            "failed"). Not restrictive by exception -- any string is
            accepted and recorded, but callers should stick to the known
            set so downstream consumers can rely on consistent values.
        detail: optional human-readable detail about this stage.
        error: optional error message. When provided, this status should
            typically have stage="failed" (not enforced, but expected by
            convention) so failures are recorded as a distinct, visible
            state rather than left ambiguous.

    Returns:
        The raw record dict that was submitted (with its structured
        payload), for the caller's own logging/reference.

    Raises:
        StatusTrackingError: if the write fails (e.g. network/auth error).
    """
    payload = {
        "session_id": session_id,
        "stage": stage,
        "detail": detail,
        "error": error,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    tags = [
        STATUS_TAG_PREFIX,
        f"{STAGE_TAG_PREFIX}:{stage}",
    ]

    record = {
        "note": json.dumps(payload),
        "tags": [_get_or_create_tag_id(client, tag) for tag in tags],
    }

    try:
        client.record_data_type("MomentAnnotation", [record], api_version="v1alpha1")
    except Exception as exc:
        raise StatusTrackingError(
            f"Failed to record status for session {session_id!r} "
            f"(stage={stage!r}): {exc}"
        ) from exc

    return record


def get_session_status_history(
    client: FulcraAPI,
    session_id: str,
    lookback: timedelta = timedelta(days=7),
) -> list[dict]:
    """Query back all recorded status updates for a session, most recent
    stage last (in write order, which is chronological since each call to
    record_status happens as the pipeline progresses).

    Returns:
        A list of decoded status payload dicts (session_id, stage, detail,
        error, recorded_at), in the order Fulcra returns them.

    Raises:
        StatusTrackingError: if the query fails.
    """
    now = datetime.now(timezone.utc)
    start_time = (now - lookback).isoformat()
    end_time = (now + timedelta(minutes=1)).isoformat()

    try:
        raw_records = client.moment_annotations(start_time, end_time)
    except Exception as exc:
        raise StatusTrackingError(
            f"Failed to query status history for session {session_id!r}: {exc}"
        ) from exc

    matching = []
    for record in raw_records:
        note = record.get("note")
        if not note:
            continue
        try:
            payload = json.loads(note)
        except json.JSONDecodeError:
            continue
        if payload.get("session_id") == session_id:
            matching.append(payload)

    matching.sort(key=lambda p: p.get("recorded_at", ""))
    return matching


def get_latest_status(
    client: FulcraAPI,
    session_id: str,
    lookback: timedelta = timedelta(days=7),
) -> Optional[dict]:
    """Convenience: return just the most recent status payload for a
    session, or None if no status has ever been recorded for it."""
    history = get_session_status_history(client, session_id, lookback)
    return history[-1] if history else None


_tag_id_cache: dict[str, str] = {}


def _get_or_create_tag_id(client: FulcraAPI, tag_name: str) -> str:
    """Resolve a tag name to its Fulcra tag ID, creating it if necessary.

    Cached per-process (tag names are stable for the lifetime of the
    pipeline's status vocabulary) to avoid a create_tags round trip for
    every single status update.
    """
    if tag_name in _tag_id_cache:
        return _tag_id_cache[tag_name]

    created = client.create_tags([tag_name])
    tag_id = created[0]["id"]
    _tag_id_cache[tag_name] = tag_id
    return tag_id
