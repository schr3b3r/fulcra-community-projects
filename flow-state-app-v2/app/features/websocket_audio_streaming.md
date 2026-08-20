# Feature: WebSocket Audio Streaming

## Status
not_started

## Description
Stream audio from the browser to the backend over a WebSocket connection,
in small chunks (e.g. every ~2 seconds), so a jam session is saved to disk
incrementally as it happens rather than buffered entirely client-side.
This protects against losing a recording if the browser tab crashes or the
connection drops mid-session.

## Acceptance Criteria
- [ ] Backend exposes a WebSocket endpoint (e.g. `/ws/record/{session_id}`)
      that accepts binary audio chunks.
- [ ] Each received chunk is appended to a file on disk associated with
      that session, without needing the full recording to be received
      first.
- [ ] A session's audio file is playable/valid after the connection closes,
      even if closed abruptly (e.g. simulate a dropped connection
      mid-stream and confirm the partial file is still valid).
- [ ] Basic error handling: a malformed or out-of-order chunk does not
      crash the connection or corrupt previously-written data.

## Dependencies
backend_skeleton.md

## Notes
Real audio capture from a browser (`getUserMedia`) is part of
`recording_frontend.md`, not this feature — this feature only needs to
prove the backend can receive and durably persist chunks over a WebSocket,
which can be tested with any chunked binary input, not necessarily real
recorded audio.
