# Feature: WebSocket Audio Streaming

## Status
done

## Description
Stream audio from the browser to the backend over a WebSocket connection,
in small chunks (e.g. every ~2 seconds), so a jam session is saved to disk
incrementally as it happens rather than buffered entirely client-side.
This protects against losing a recording if the browser tab crashes or the
connection drops mid-session.

## Acceptance Criteria
- [x] Backend exposes a WebSocket endpoint (e.g. `/ws/record/{session_id}`)
      that accepts binary audio chunks.
- [x] Each received chunk is appended to a file on disk associated with
      that session, without needing the full recording to be received
      first.
- [x] A session's audio file is playable/valid after the connection closes,
      even if closed abruptly (e.g. simulate a dropped connection
      mid-stream and confirm the partial file is still valid).
- [x] Basic error handling: a malformed or out-of-order chunk does not
      crash the connection or corrupt previously-written data.
- [x] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes.

## Dependencies
backend_skeleton.md

## Notes
Real audio capture from a browser (`getUserMedia`) is part of
`recording_frontend.md`, not this feature — this feature only needs to
prove the backend can receive and durably persist chunks over a WebSocket,
which can be tested with any chunked binary input, not necessarily real
recorded audio.

**Protocol update (this build pass):** the endpoint now also treats a
text message `"STOP"` from the client as end-of-recording, in addition to
`websocket.disconnect`. This was necessary once the endpoint started
triggering the processing pipeline on completion (see `pipeline.py`):
closing the socket immediately (the original behavior) meant no progress
messages could ever be sent back, since the connection was already gone.
Sending `"STOP"` lets the client signal "done recording" while keeping
the socket open long enough to receive pipeline progress messages before
the server closes it. A real client that closes without sending `"STOP"`
(e.g. a crashed tab) still works via the disconnect path -- it just won't
receive progress messages, which matches the original acceptance
criterion about surviving abrupt disconnects.
