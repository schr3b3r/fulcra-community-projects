import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from fulcra_client import FulcraAuthError, get_fulcra_client
from idea_publishing import PublishingError
from pipeline import process_completed_session, process_marker_recording
from review_api import (
    AudioNotFoundError,
    download_idea_audio_from_fulcra,
    download_session_audio_from_fulcra,
    get_current_marker_info,
    list_review_ideas,
    local_idea_clip_path,
    local_processed_audio_path,
)

logger = logging.getLogger(__name__)

# Directory raw session recordings are appended to as chunks arrive over
# the WebSocket. Relative to this file (app/), so it works the same way
# whether uvicorn is launched from app/ or the repo root.
RAW_SESSIONS_DIR = Path(__file__).resolve().parent / "raw"

# Origins allowed to talk to this API from a browser. Covers the SvelteKit
# (Vite) dev server's default origin -- see recording_frontend.md. The
# production origin is still an open decision (see that feature's Notes)
# and will be added here once it's chosen.

app = FastAPI(
    title="Flow State Backend",
    description="Backend service for Flow State - capturing jam sessions and extracting musical ideas.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "name": "Flow State Backend API",
        "description": "Flow State backend service for recording jam sessions and extracting musical ideas.",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/marker")
def api_get_current_marker():
    """Info about the currently active marker sample (the one new
    session recordings get detected against), or a clear "none yet"
    response if no marker has been recorded."""
    marker_info = get_current_marker_info()
    if marker_info is None:
        return {"marker": None}
    return {"marker": marker_info}


@app.get("/api/ideas")
def api_list_ideas():
    """List published musical ideas for the review feed."""
    try:
        client = get_fulcra_client()
    except FulcraAuthError as exc:
        raise HTTPException(status_code=503, detail=f"Fulcra not available: {exc}")

    try:
        ideas = list_review_ideas(client)
    except PublishingError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list ideas: {exc}")

    return {"ideas": ideas}


@app.get("/api/audio/session/{session_id}")
def api_get_session_audio(session_id: str):
    """Stream a processed session (or marker) recording's audio for
    playback in the browser, e.g. via wavesurfer.js. Prefers the local
    copy (fast path); falls back to Fulcra if the local file no longer
    exists (e.g. after a server restart -- local disk is a cache, not the
    durable copy)."""
    try:
        path = local_processed_audio_path(session_id)
        return Response(content=path.read_bytes(), media_type="audio/wav")
    except AudioNotFoundError:
        pass

    try:
        client = get_fulcra_client()
    except FulcraAuthError as exc:
        raise HTTPException(status_code=503, detail=f"Fulcra not available: {exc}")

    try:
        audio_bytes = download_session_audio_from_fulcra(client, session_id)
    except AudioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(content=audio_bytes, media_type="audio/wav")


@app.get("/api/audio/idea/{idea_id}")
def api_get_idea_audio(idea_id: str):
    """Stream an extracted idea clip's audio for playback. Prefers the
    local copy (fast path, immediately after extraction); falls back to
    downloading it from Fulcra if the local file no longer exists (e.g.
    after a server restart, since local disk isn't the durable copy --
    Fulcra is)."""
    try:
        path = local_idea_clip_path(idea_id)
        return Response(content=path.read_bytes(), media_type="audio/wav")
    except AudioNotFoundError:
        pass

    try:
        client = get_fulcra_client()
    except FulcraAuthError as exc:
        raise HTTPException(status_code=503, detail=f"Fulcra not available: {exc}")

    try:
        ideas = list_review_ideas(client)
    except PublishingError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to look up idea: {exc}")

    matching = next(
        (idea for idea in ideas if idea.get("idea_id") == idea_id),
        None,
    )
    if matching is None:
        raise HTTPException(status_code=404, detail=f"Idea not found: {idea_id!r}")

    try:
        audio_bytes = download_idea_audio_from_fulcra(client, matching["file_path"])
    except AudioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(content=audio_bytes, media_type="audio/wav")


def _raw_session_path(session_id: str) -> Path:
    """Resolve the on-disk path for a session's raw recording.

    Session IDs are constrained to a safe character set so this can never
    be used to write outside RAW_SESSIONS_DIR (e.g. via `../` traversal).
    """
    safe_id = "".join(
        ch for ch in session_id if ch.isalnum() or ch in ("-", "_")
    )
    if not safe_id or safe_id != session_id:
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return RAW_SESSIONS_DIR / f"{safe_id}.webm"


@app.websocket("/ws/record/{session_id}")
async def record_session(websocket: WebSocket, session_id: str) -> None:
    """Accept a WebSocket connection and append each binary chunk received
    to that session's raw recording file on disk, in real time.

    Each chunk is appended and flushed to disk as it arrives (not buffered
    in memory until the connection closes), so the file on disk is always
    a valid prefix of the final recording -- if the connection drops
    mid-stream, everything received so far is still safely persisted.

    Once the raw recording is complete -- signaled by the client sending
    a text message "STOP" (matching a prior implementation of this same
    concept), NOT by closing the socket, since closing would prevent any
    further progress messages from ever reaching the client -- the
    connection stays open and the completed recording is handed off to
    the processing pipeline (audio_processing_pipeline ->
    audio_marker_detection -> dsp_idea_extraction ->
    musical_idea_publishing, with processing_status_tracking recording
    each stage). Progress messages are sent back over the still-open
    socket as the pipeline runs; the server closes the connection itself
    once the pipeline finishes. If the client disconnects abruptly
    instead of sending "STOP" (e.g. a crashed tab), the pipeline still
    runs against whatever was received, but progress messages have
    nowhere to go since the socket is already gone.

    `mode` (query param, default "session") selects which pipeline runs:
    "marker" processes a fresh reference marker sample instead of a full
    jam session.
    """
    try:
        file_path = _raw_session_path(session_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid session_id")
        return

    mode = websocket.query_params.get("mode", "session")

    await websocket.accept()
    RAW_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    disconnected = False
    try:
        with open(file_path, "ab") as raw_file:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    disconnected = True
                    break

                text = message.get("text")
                if text == "STOP":
                    # Client signals "recording finished" without closing
                    # the socket, so progress messages can still be sent
                    # back over it while the pipeline runs.
                    break

                chunk = message.get("bytes")
                if chunk is None:
                    # Any other non-binary message is ignored rather than
                    # treated as fatal -- a malformed/unexpected message
                    # must not crash the connection or corrupt
                    # already-written data.
                    continue

                raw_file.write(chunk)
                raw_file.flush()
    except WebSocketDisconnect:
        # Client dropped the connection (e.g. simulating a crash). The
        # file on disk already reflects everything written up to this
        # point because each chunk was flushed immediately above.
        disconnected = True

    async def _send_progress(message: str) -> None:
        if disconnected:
            return
        try:
            await websocket.send_text(message)
        except Exception:
            pass

    # The pipeline (ffmpeg, librosa DSP, network calls to Fulcra) is
    # synchronous and can take real time -- run it in a worker thread via
    # run_in_executor rather than blocking the event loop. Progress
    # messages originate from that worker thread, so they must be
    # scheduled onto the event loop with call_soon_threadsafe -- calling
    # asyncio.create_task directly from another thread is invalid (it
    # requires a running loop *in the calling thread*), which silently
    # swallowed every progress message here previously.
    loop = asyncio.get_event_loop()

    def _sync_progress(message: str) -> None:
        def _schedule_send() -> None:
            loop.create_task(_send_progress(message))

        loop.call_soon_threadsafe(_schedule_send)

    try:
        if mode == "marker":
            await loop.run_in_executor(
                None, process_marker_recording, session_id, _sync_progress
            )
        else:
            await loop.run_in_executor(
                None, process_completed_session, session_id, _sync_progress
            )
    except Exception:
        logger.exception(
            "Processing pipeline (mode=%s) raised for session %s", mode, session_id
        )

    if not disconnected:
        try:
            await websocket.close()
        except Exception:
            pass
