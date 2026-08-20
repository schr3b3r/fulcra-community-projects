from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
    """
    try:
        file_path = _raw_session_path(session_id)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid session_id")
        return

    await websocket.accept()
    RAW_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(file_path, "ab") as raw_file:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break

                chunk = message.get("bytes")
                if chunk is None:
                    # Non-binary (e.g. text) messages are ignored rather
                    # than treated as fatal -- a malformed/unexpected
                    # message must not crash the connection or corrupt
                    # already-written data.
                    continue

                raw_file.write(chunk)
                raw_file.flush()
    except WebSocketDisconnect:
        # Client dropped the connection (e.g. simulating a crash). The
        # file on disk already reflects everything written up to this
        # point because each chunk was flushed immediately above.
        pass
