"""Review API: read-only endpoints backing the frontend's review feed
(list published ideas, fetch current marker info, stream audio for
playback).

Kept as plain, testable functions separate from main.py's route
declarations, mirroring the pattern used by pipeline.py.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fulcra_api.core import FulcraAPI

from idea_publishing import get_published_ideas
from pipeline import CURRENT_MARKER_POINTER, IDEAS_DIR, PROCESSED_DIR

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK = timedelta(days=30)


class AudioNotFoundError(Exception):
    """Raised when a requested audio resource doesn't exist locally or
    in Fulcra."""


def list_review_ideas(client: FulcraAPI, lookback: timedelta = DEFAULT_LOOKBACK) -> list[dict]:
    """Fetch published MusicalIdea records for the review feed, sorted
    oldest-to-newest within each session (matching write order) and
    overall by recorded_at descending (most recent session first) --
    grouping by session is left to the caller/frontend, this just
    returns the flat list of idea records with all fields the frontend
    needs to group and render them.
    """
    now = datetime.now(timezone.utc)
    start_time = now - lookback
    end_time = now + timedelta(minutes=1)

    ideas = get_published_ideas(client, start_time, end_time)
    ideas.sort(key=lambda i: i.get("recorded_at") or "", reverse=True)
    return ideas


def get_current_marker_info() -> Optional[dict]:
    """Return info about the currently active marker sample (the one new
    sessions get detected against), or None if no marker has been
    recorded yet.

    Returns:
        {"session_id": str, "processed_at": iso8601 str} or None.
    """
    if not CURRENT_MARKER_POINTER.is_file():
        return None

    marker_path = Path(CURRENT_MARKER_POINTER.read_text().strip())
    if not marker_path.is_file():
        return None

    session_id = marker_path.stem
    processed_at = datetime.fromtimestamp(
        marker_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()
    return {"session_id": session_id, "processed_at": processed_at}


def local_processed_audio_path(session_id: str) -> Path:
    """Resolve the local processed .wav path for a session or marker
    recording, raising AudioNotFoundError if it doesn't exist.

    Session IDs are sanitized the same way main.py's WebSocket endpoint
    does, so this can never be used to read outside PROCESSED_DIR.
    """
    safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
    if not safe_id or safe_id != session_id:
        raise AudioNotFoundError(f"Invalid session_id: {session_id!r}")

    path = PROCESSED_DIR / f"{safe_id}.wav"
    if not path.is_file():
        raise AudioNotFoundError(f"No processed audio found for session {session_id!r}")
    return path


def download_session_audio_from_fulcra(client: FulcraAPI, session_id: str) -> bytes:
    """Fetch a session (or marker) recording's audio bytes from Fulcra,
    as a fallback for when the local processed copy no longer exists
    (e.g. after a server restart) -- see
    idea_publishing.upload_session_audio for where this is durably
    stored."""
    fulcra_path = f"/flow-state/sessions/{session_id}.wav"
    try:
        files = client.resolve_filepath(fulcra_path)
    except Exception as exc:
        raise AudioNotFoundError(
            f"Could not resolve {fulcra_path!r} in Fulcra: {exc}"
        ) from exc

    if not files:
        raise AudioNotFoundError(f"No file found in Fulcra at {fulcra_path!r}")

    file_id = files[0]["id"]
    try:
        response = client.download_file(file_id)
        return response.read()
    except Exception as exc:
        raise AudioNotFoundError(
            f"Failed to download {fulcra_path!r} from Fulcra: {exc}"
        ) from exc


def local_idea_clip_path(idea_id: str) -> Path:
    """Resolve the local extracted clip path for an idea_id, raising
    AudioNotFoundError if it doesn't exist locally (e.g. after a restart
    wiped local disk but Fulcra still has it -- callers should fall back
    to the Fulcra-backed download for that case)."""
    safe_id = "".join(ch for ch in idea_id if ch.isalnum() or ch in ("-", "_"))
    if not safe_id or safe_id != idea_id:
        raise AudioNotFoundError(f"Invalid idea_id: {idea_id!r}")

    path = IDEAS_DIR / f"{safe_id}.wav"
    if not path.is_file():
        raise AudioNotFoundError(f"No local clip found for idea {idea_id!r}")
    return path


def download_idea_audio_from_fulcra(client: FulcraAPI, fulcra_file_path: str) -> bytes:
    """Fetch an idea clip's audio bytes from Fulcra by its uploaded file
    path (fallback for when the local copy no longer exists, e.g. after
    a server restart)."""
    try:
        files = client.resolve_filepath(fulcra_file_path)
    except Exception as exc:
        raise AudioNotFoundError(
            f"Could not resolve {fulcra_file_path!r} in Fulcra: {exc}"
        ) from exc

    if not files:
        raise AudioNotFoundError(f"No file found in Fulcra at {fulcra_file_path!r}")

    file_id = files[0]["id"]
    try:
        response = client.download_file(file_id)
        return response.read()
    except Exception as exc:
        raise AudioNotFoundError(
            f"Failed to download {fulcra_file_path!r} from Fulcra: {exc}"
        ) from exc
