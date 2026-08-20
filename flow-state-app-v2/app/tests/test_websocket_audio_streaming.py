"""Tests for the WebSocket audio streaming feature.

See app/features/websocket_audio_streaming.md for acceptance criteria.
Uses FastAPI's TestClient (Starlette under the hood), which drives the
WebSocket endpoint against real ASGI machinery without needing a live
network socket or a running uvicorn process.
"""
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from main import RAW_SESSIONS_DIR, app

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
MARKER_WEBM = FIXTURES_DIR / "marker.webm"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_raw_dir():
    """Ensure each test starts and ends with a clean raw/ directory, since
    the endpoint writes real files to disk keyed by session_id."""
    if RAW_SESSIONS_DIR.exists():
        shutil.rmtree(RAW_SESSIONS_DIR)
    yield
    if RAW_SESSIONS_DIR.exists():
        shutil.rmtree(RAW_SESSIONS_DIR)


def _new_session_id() -> str:
    return f"test-session-{uuid.uuid4().hex}"


def _chunk_file(data: bytes, chunk_size: int = 4096) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def test_websocket_endpoint_accepts_binary_chunks_and_writes_file(client: TestClient):
    """Backend exposes /ws/record/{session_id} and accepts binary chunks."""
    session_id = _new_session_id()
    raw_bytes = MARKER_WEBM.read_bytes()
    chunks = _chunk_file(raw_bytes)

    with client.websocket_connect(f"/ws/record/{session_id}") as ws:
        for chunk in chunks:
            ws.send_bytes(chunk)

    written_path = RAW_SESSIONS_DIR / f"{session_id}.webm"
    assert written_path.exists()


def test_chunks_are_appended_incrementally_not_only_on_close(client: TestClient):
    """Each chunk is appended to disk as it's received, not buffered until
    the connection closes -- verified by checking the file grows mid-stream
    (before the websocket context manager exits)."""
    session_id = _new_session_id()
    raw_bytes = MARKER_WEBM.read_bytes()
    chunks = _chunk_file(raw_bytes)
    assert len(chunks) >= 2, "fixture too small to test incremental writes"

    written_path = RAW_SESSIONS_DIR / f"{session_id}.webm"

    with client.websocket_connect(f"/ws/record/{session_id}") as ws:
        ws.send_bytes(chunks[0])
        # Give the ASGI app a beat to process; TestClient runs the app in a
        # background thread so sends are processed concurrently.
        import time

        for _ in range(50):
            if written_path.exists() and written_path.stat().st_size > 0:
                break
            time.sleep(0.05)

        assert written_path.exists()
        size_after_first_chunk = written_path.stat().st_size
        assert size_after_first_chunk > 0
        assert size_after_first_chunk <= len(raw_bytes)

        for chunk in chunks[1:]:
            ws.send_bytes(chunk)

    final_size = written_path.stat().st_size
    assert final_size == len(raw_bytes)
    # The file genuinely grew between the first chunk and the full upload --
    # proof this isn't just a single write-on-close.
    assert final_size > size_after_first_chunk


def test_partial_recording_survives_abrupt_disconnect(client: TestClient):
    """A session's audio file is playable/valid after the connection closes,
    even if closed abruptly mid-stream (simulated dropped connection)."""
    session_id = _new_session_id()
    raw_bytes = MARKER_WEBM.read_bytes()
    chunks = _chunk_file(raw_bytes, chunk_size=8192)
    assert len(chunks) >= 2

    written_path = RAW_SESSIONS_DIR / f"{session_id}.webm"

    # Simulate a dropped connection: send only the first chunk, then close
    # the websocket abruptly (context manager exit closes without a clean
    # "recording finished" handshake).
    with client.websocket_connect(f"/ws/record/{session_id}") as ws:
        ws.send_bytes(chunks[0])

    assert written_path.exists()
    partial_size = written_path.stat().st_size
    assert partial_size > 0
    assert partial_size < len(raw_bytes)

    # The partial file must still be a structurally valid (parseable) media
    # container -- checked with ffprobe, the same tool the processing
    # pipeline will rely on downstream.
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name",
            "-of",
            "default=noprint_wrappers=1",
            str(written_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"ffprobe could not parse the partial file as valid media: "
        f"{result.stderr}"
    )
    assert "matroska" in result.stdout.lower() or "webm" in result.stdout.lower()


def test_malformed_or_out_of_order_input_does_not_crash_or_corrupt(client: TestClient):
    """Basic error handling: a malformed/unexpected message (e.g. a text
    frame interleaved with binary chunks) doesn't crash the connection or
    corrupt previously-written data."""
    session_id = _new_session_id()
    raw_bytes = MARKER_WEBM.read_bytes()
    chunks = _chunk_file(raw_bytes)

    written_path = RAW_SESSIONS_DIR / f"{session_id}.webm"

    with client.websocket_connect(f"/ws/record/{session_id}") as ws:
        ws.send_bytes(chunks[0])
        # Send an unexpected text message in the middle of the stream.
        ws.send_text("not-a-binary-chunk")
        for chunk in chunks[1:]:
            ws.send_bytes(chunk)

    # The connection should have survived the whole exchange (no exception
    # raised inside the `with` block above), and the resulting file should
    # be exactly the concatenation of the real binary chunks, with the text
    # message ignored rather than written into the audio stream.
    assert written_path.exists()
    assert written_path.read_bytes() == raw_bytes


def test_invalid_session_id_is_rejected_without_crashing(client: TestClient):
    """A session_id containing path-traversal characters is rejected (the
    connection is closed) rather than allowed to write outside raw/."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/record/../../etc/passwd") as ws:
            ws.send_bytes(b"whatever")

    # Nothing should have been written outside the sandboxed raw/ dir.
    assert not (RAW_SESSIONS_DIR.parent / "etc").exists()


def test_multiple_sessions_do_not_interfere(client: TestClient):
    """Two concurrent-ish sessions write to independent files."""
    session_a = _new_session_id()
    session_b = _new_session_id()
    data_a = b"AAAA" * 100
    data_b = b"BBBB" * 100

    with client.websocket_connect(f"/ws/record/{session_a}") as ws_a:
        ws_a.send_bytes(data_a)
    with client.websocket_connect(f"/ws/record/{session_b}") as ws_b:
        ws_b.send_bytes(data_b)

    path_a = RAW_SESSIONS_DIR / f"{session_a}.webm"
    path_b = RAW_SESSIONS_DIR / f"{session_b}.webm"
    assert path_a.read_bytes() == data_a
    assert path_b.read_bytes() == data_b
