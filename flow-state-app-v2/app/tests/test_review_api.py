"""Tests for review_api.py -- the read-only endpoints backing the
frontend's review feed.
"""
import shutil
import time
import uuid
from pathlib import Path

import pytest

from audio import convert_webm_to_wav, extract_musical_idea
from fulcra_client import FulcraAuthError, get_fulcra_client
from idea_publishing import publish_musical_idea
from pipeline import CURRENT_MARKER_POINTER, IDEAS_DIR, PROCESSED_DIR
from review_api import (
    AudioNotFoundError,
    download_idea_audio_from_fulcra,
    get_current_marker_info,
    list_review_ideas,
    local_idea_clip_path,
    local_processed_audio_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RAW_SESSION_WEBM = FIXTURES_DIR / "raw_session.webm"

POLL_TIMEOUT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 0.5


def _fulcra_client_or_skip():
    try:
        return get_fulcra_client()
    except FulcraAuthError:
        pytest.skip("No local Fulcra credentials available; skipping live SDK test.")


def _poll_until(predicate, timeout: float = POLL_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        result = predicate()
    return result


@pytest.fixture()
def client():
    return _fulcra_client_or_skip()


@pytest.fixture()
def clean_marker_pointer():
    """Save/restore the real current-marker pointer so tests that
    manipulate it don't permanently disturb the actual pipeline state."""
    original = CURRENT_MARKER_POINTER.read_text() if CURRENT_MARKER_POINTER.is_file() else None
    yield
    if original is not None:
        CURRENT_MARKER_POINTER.write_text(original)
    elif CURRENT_MARKER_POINTER.is_file():
        CURRENT_MARKER_POINTER.unlink()


def test_get_current_marker_info_none_when_never_set(
    clean_marker_pointer, tmp_path: Path
):
    if CURRENT_MARKER_POINTER.is_file():
        CURRENT_MARKER_POINTER.unlink()
    assert get_current_marker_info() is None


def test_get_current_marker_info_reflects_pointer(clean_marker_pointer, tmp_path: Path):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fake_marker = PROCESSED_DIR / f"test-marker-{uuid.uuid4().hex}.wav"
    fake_marker.write_bytes(b"fake wav bytes")
    try:
        CURRENT_MARKER_POINTER.write_text(str(fake_marker))
        info = get_current_marker_info()
        assert info is not None
        assert info["session_id"] == fake_marker.stem
        assert "processed_at" in info
    finally:
        fake_marker.unlink(missing_ok=True)


def test_local_processed_audio_path_missing_raises(tmp_path: Path):
    with pytest.raises(AudioNotFoundError):
        local_processed_audio_path(f"nonexistent-{uuid.uuid4().hex}")


def test_local_processed_audio_path_rejects_traversal():
    with pytest.raises(AudioNotFoundError):
        local_processed_audio_path("../../etc/passwd")


def test_local_idea_clip_path_missing_raises():
    with pytest.raises(AudioNotFoundError):
        local_idea_clip_path(f"nonexistent-idea-{uuid.uuid4().hex}")


def test_list_review_ideas_and_download_from_fulcra_round_trip(client, tmp_path: Path):
    """Publish a real idea, then confirm list_review_ideas surfaces it
    and download_idea_audio_from_fulcra can fetch its actual audio bytes
    back -- exercising the exact path the /api/audio/idea endpoint falls
    back to when no local copy exists."""
    processed_dir = tmp_path / "processed"
    session_wav = convert_webm_to_wav(
        RAW_SESSION_WEBM, processed_dir / "raw_session.wav"
    )
    session_id = f"pytest-review-{uuid.uuid4().hex}"
    idea_id = f"{session_id}_idea0"
    extraction = extract_musical_idea(
        session_wav, 38.6, processed_dir / f"{idea_id}.wav", lookback_seconds=15.0
    )

    publish_musical_idea(
        client,
        extraction["clip_path"],
        key=extraction["key"],
        bpm=extraction["bpm"],
        session_id=session_id,
        marker_timestamp_seconds=38.6,
        idea_id=idea_id,
    )

    def _find_it():
        ideas = list_review_ideas(client)
        return next((i for i in ideas if i.get("idea_id") == idea_id), None)

    published = _poll_until(_find_it)
    assert published is not None
    assert published["session_id"] == session_id

    audio_bytes = download_idea_audio_from_fulcra(client, published["file_path"])
    assert audio_bytes == extraction["clip_path"].read_bytes()
