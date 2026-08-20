# Feature: Recording Frontend

## Status
in_progress

## Description
Browser-based UI for musicians to start/stop a recording session, capture
real microphone audio, stream it to the backend (see
`websocket_audio_streaming.md`), and later review/play back extracted
musical ideas.

Built with **SvelteKit**, as a separate app/process from the FastAPI
backend — not server-rendered from within FastAPI, not a single combined
process. This is a standard decoupled frontend/backend split: the browser
talks to FastAPI over plain HTTP and WebSocket connections, the same way
any client would, regardless of what language or framework runs behind
that boundary. SvelteKit imposes no constraint on the Python backend's
architecture (background tasks, workers, etc.) — that boundary is already
just "the browser calls a URL."

## Acceptance Criteria
- [x] A page lets the user start a recording session using the browser's
      microphone (`getUserMedia`), with echo cancellation disabled and
      auto-gain enabled (for cleaner audio capture).
- [x] Captured audio is chunked and sent to the backend's WebSocket
      endpoint in real time as the session progresses.
- [x] The user can stop the session cleanly, and the recording lands as a
      complete file in `raw/` (verified manually and via a scripted
      WebSocket client standing in for the browser -- see Notes; no
      explicit "upload confirmed" handshake message from the backend yet,
      that's still open).
- [ ] A separate review view lists previously extracted musical ideas and
      allows playback of each clip.
- [x] FastAPI has CORS configured to accept requests from the SvelteKit
      dev server's origin (Vite default, typically `http://localhost:5173`)
      for both HTTP and WebSocket connections, and from whatever the
      production origin ends up being once that's decided.
- [ ] Has automated tests (pytest for the backend side -- already covered
      by `websocket_audio_streaming`'s suite -- plus browser-level
      tests if a framework like Playwright is introduced for the SvelteKit
      side) covering the above criteria, and the full test suite passes.
      **Not yet done**: no Playwright/browser-level tests exist for the
      frontend itself yet, only manual + scripted-client verification.
      Left as visible debt rather than silently checked off.

## Dependencies
websocket_audio_streaming.md, musical_idea_publishing.md (for the review
view to have anything to list)

## Notes
**Sequencing pivot:** originally planned as the last feature, built only
after the full backend pipeline (streaming -> detection -> extraction ->
publishing). Revisited that plan: rather than building the entire backend
chain before touching any UI, a deliberately minimal slice of this feature
was pulled forward and built alongside `websocket_audio_streaming`, so
there's something clickable to test end-to-end well before marker
detection/DSP/publishing exist.

**What this minimal slice is:** a single bare-bones SvelteKit page
(`frontend/src/routes/+page.svelte`) with just Record/Stop buttons and a
status line -- no styling, no review view. Clicking Record calls
`getUserMedia` (echo cancellation off, auto-gain on), opens a WebSocket to
`/ws/record/{session_id}`, and streams `MediaRecorder` chunks (~every 2s,
`audio/webm`) to the backend. Clicking Stop stops capture and closes the
socket. This proves the full chain: browser mic -> WebSocket -> file in
`raw/` -- verified live with the FastAPI dev server + Vite dev server both
running, plus a scripted Python WebSocket client (standing in for a real
browser, since this sandbox has no real microphone/browser) streaming the
`marker.webm` test fixture and confirming a byte-identical, ffprobe-valid
file landed in `raw/`.

**Still open / deliberately deferred:** the review view (depends on
`musical_idea_publishing.md`, not built yet), any styling/polish, an
explicit "upload confirmed" message from backend to frontend, and
browser-level (Playwright) automated tests. The production frontend
deployment shape (static export vs. separate Node process) is still an
open decision, unaffected by this slice, which only concerns local dev.
In local dev, expect two separate processes running side by side: FastAPI
(port 8000) and the SvelteKit/Vite dev server (port 5173).
