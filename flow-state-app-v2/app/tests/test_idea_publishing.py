"""Tests for musical_idea_publishing.

Exercises the REAL Fulcra SDK (upload_file, record_data_type,
moment_annotations) against the authenticated local account, using a real
extracted clip (derived from the committed test fixtures) -- not mocks.
Skipped entirely if no local Fulcra credentials are available.
"""
import time
import uuid
from pathlib import Path

import pytest

from audio import convert_webm_to_wav, extract_musical_idea
from fulcra_client import FulcraAuthError, get_fulcra_client
from idea_publishing import (
    MusicalIdeaTypeNotFoundError,
    PublishingError,
    get_published_ideas,
    publish_musical_idea,
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


@pytest.fixture(scope="module")
def real_idea_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real extracted clip derived from the committed audio fixtures,
    using the real marker timestamp validated in fixtures/README.md."""
    processed_dir = tmp_path_factory.mktemp("processed")
    session_wav = convert_webm_to_wav(
        RAW_SESSION_WEBM, processed_dir / "raw_session.wav"
    )
    result = extract_musical_idea(
        session_wav, 38.6, processed_dir / "idea.wav", lookback_seconds=15.0
    )
    return result["clip_path"]


@pytest.fixture()
def session_id() -> str:
    return f"pytest-publish-{uuid.uuid4().hex}"


def test_publish_and_query_back_round_trip(
    client, real_idea_clip: Path, session_id: str
) -> None:
    """Publish a real idea, then confirm it can be queried back and the
    metadata matches -- not just trusting the upload call returned success."""
    from datetime import datetime, timedelta, timezone

    result = publish_musical_idea(
        client,
        real_idea_clip,
        key="C Major",
        bpm=120,
        session_id=session_id,
        marker_timestamp_seconds=38.6,
    )

    assert result["upload_id"]
    assert result["file_path"].endswith(real_idea_clip.name)

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=5)
    end = now + timedelta(minutes=5)

    def _find_published():
        ideas = get_published_ideas(client, start, end)
        return next((i for i in ideas if i.get("session_id") == session_id), None)

    published = _poll_until(_find_published)
    assert published is not None
    assert published["key"] == "C Major"
    assert published["bpm"] == 120
    assert published["session_id"] == session_id
    assert published["marker_timestamp_seconds"] == 38.6


def test_publish_missing_clip_raises_clear_error(client, tmp_path: Path) -> None:
    with pytest.raises(PublishingError, match="Clip file not found"):
        publish_musical_idea(
            client,
            tmp_path / "does_not_exist.wav",
            key="C Major",
            bpm=120,
            session_id="whatever",
            marker_timestamp_seconds=10.0,
        )


def test_musical_idea_type_not_found_is_a_distinct_error(
    monkeypatch: pytest.MonkeyPatch, client, real_idea_clip: Path
) -> None:
    """If the MusicalIdea type isn't provisioned, fail with a specific,
    clear error rather than crashing unhandled or silently no-op'ing."""
    monkeypatch.setattr(client, "v1_catalog", lambda: [])

    with pytest.raises(MusicalIdeaTypeNotFoundError):
        publish_musical_idea(
            client,
            real_idea_clip,
            key="C Major",
            bpm=120,
            session_id="whatever",
            marker_timestamp_seconds=10.0,
        )
