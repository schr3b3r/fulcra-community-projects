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

**Sequencing note (this build pass):** built alongside a deliberately
minimal slice of `recording_frontend.md` (record/stop buttons only, no
review view) rather than after the full backend pipeline
(processing/detection/DSP/publishing), so there's something clickable to
test end-to-end sooner. See `recording_frontend.md`'s Notes for the
reasoning. This feature's own acceptance criteria above are fully met on
their own terms — the sequencing choice only affects *when* this was
built relative to other backend features, not what was required of it.

"Playable/valid" is verified by ffprobe-style structural validity of the
received bytes (parseable WebM/Opus container), not by human listening —
consistent with how `audio_processing_pipeline.md`'s conversion step will
later validate its own output.
