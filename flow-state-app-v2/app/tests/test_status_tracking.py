"""Tests for processing_status_tracking.

These exercise the REAL Fulcra SDK against the authenticated local
account (per app/ENGINEERING_STANDARDS.md's preference for real, runnable
tests over structure-only checks) -- not a mock. If local Fulcra
credentials aren't available, these tests are skipped rather than failing
the whole suite, so the rest of the app remains testable without Fulcra
access.

Note on eventual consistency: Fulcra's ingest pipeline has a short delay
(observed ~1s) between writing an annotation and it becoming queryable.
Tests poll briefly for this rather than asserting instantaneously, since
that's a real characteristic of the system being tested, not test flake.
"""
import time
import uuid

import pytest

from fulcra_client import FulcraAuthError, get_fulcra_client
from status_tracking import (
    get_latest_status,
    get_session_status_history,
    record_status,
)

POLL_TIMEOUT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 0.5


def _fulcra_client_or_skip():
    try:
        return get_fulcra_client()
    except FulcraAuthError:
        pytest.skip("No local Fulcra credentials available; skipping live SDK test.")


def _poll_until(predicate, timeout: float = POLL_TIMEOUT_SECONDS):
    """Poll `predicate()` until it returns a truthy value or timeout
    elapses, to absorb Fulcra's ingest lag rather than racing it."""
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
def session_id() -> str:
    """A unique session ID per test so parallel/repeated runs never
    collide against previously-written status records."""
    return f"pytest-status-{uuid.uuid4().hex}"


def test_record_and_read_back_single_status(client, session_id: str) -> None:
    """Round-trip: write a status, read it back, confirm it matches."""
    record_status(client, session_id, stage="received", detail="raw file landed")

    latest = _poll_until(lambda: get_latest_status(client, session_id))
    assert latest is not None
    assert latest["session_id"] == session_id
    assert latest["stage"] == "received"
    assert latest["detail"] == "raw file landed"
    assert latest["error"] is None


def test_status_progresses_through_multiple_stages(client, session_id: str) -> None:
    """Status is updated as the file moves through pipeline stages, and
    the full history can be queried back in order."""
    record_status(client, session_id, stage="received")
    record_status(client, session_id, stage="processing")
    record_status(client, session_id, stage="processed")

    history = _poll_until(
        lambda: get_session_status_history(client, session_id)
        if len(get_session_status_history(client, session_id)) >= 3
        else None
    )
    stages = [h["stage"] for h in history]
    assert stages == ["received", "processing", "processed"]

    latest = get_latest_status(client, session_id)
    assert latest is not None
    assert latest["stage"] == "processed"


def test_failure_recorded_with_error_message(client, session_id: str) -> None:
    """A failure at any stage is recorded as a distinct 'failed' status
    with an error message attached, not silently dropped."""
    record_status(client, session_id, stage="processing")
    record_status(
        client,
        session_id,
        stage="failed",
        error="ffmpeg conversion failed: corrupt input",
    )

    latest = _poll_until(
        lambda: (get_latest_status(client, session_id) or {}).get("stage") == "failed"
        and get_latest_status(client, session_id)
    )
    assert latest is not None
    assert latest["stage"] == "failed"
    assert latest["error"] == "ffmpeg conversion failed: corrupt input"


def test_unknown_session_has_no_status_history(client) -> None:
    """A session_id that was never recorded returns an empty history /
    None latest status, rather than raising or returning stale data."""
    unknown_session_id = f"pytest-status-never-existed-{uuid.uuid4().hex}"
    assert get_session_status_history(client, unknown_session_id) == []
    assert get_latest_status(client, unknown_session_id) is None


def test_different_sessions_do_not_interfere(client) -> None:
    """Two sessions' status histories are tracked independently."""
    session_a = f"pytest-status-a-{uuid.uuid4().hex}"
    session_b = f"pytest-status-b-{uuid.uuid4().hex}"

    record_status(client, session_a, stage="received")
    record_status(client, session_b, stage="failed", error="boom")

    latest_a = _poll_until(lambda: get_latest_status(client, session_a))
    latest_b = _poll_until(lambda: get_latest_status(client, session_b))

    assert latest_a is not None
    assert latest_b is not None
    assert latest_a["stage"] == "received"
    assert latest_b["stage"] == "failed"
    assert latest_b["error"] == "boom"
