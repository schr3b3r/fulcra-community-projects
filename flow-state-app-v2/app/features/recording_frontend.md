# Feature: Recording Frontend

## Status
not_started

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
- [ ] A page lets the user start a recording session using the browser's
      microphone (`getUserMedia`), with echo cancellation disabled and
      auto-gain enabled (for cleaner audio capture).
- [ ] Captured audio is chunked and sent to the backend's WebSocket
      endpoint in real time as the session progresses.
- [ ] The user can stop the session cleanly, and the backend confirms the
      full recording was received.
- [ ] A separate review view lists previously extracted musical ideas and
      allows playback of each clip.
- [ ] FastAPI has CORS configured to accept requests from the SvelteKit
      dev server's origin (Vite default, typically `http://localhost:5173`)
      for both HTTP and WebSocket connections, and from whatever the
      production origin ends up being once that's decided.
- [ ] Has automated tests (pytest for the backend side, plus browser-level
      tests if a framework like Playwright is introduced for the SvelteKit
      side) covering the above criteria, and the full test suite passes.

## Dependencies
websocket_audio_streaming.md, musical_idea_publishing.md (for the review
view to have anything to list)

## Notes
This is the largest, most user-facing feature and depends on several
backend features being in place first. Likely the last feature to be
picked up, once the backend pipeline (streaming -> detection -> extraction
-> publishing) is proven end-to-end.

Deployment shape (whether SvelteKit is exported as static files served by
FastAPI, or run as its own Node process behind a reverse proxy) is an open
decision to make when this feature is actually picked up — not decided
here. In local dev, expect two separate processes running side by side:
FastAPI (typically port 8000) and the SvelteKit/Vite dev server (typically
port 5173).
