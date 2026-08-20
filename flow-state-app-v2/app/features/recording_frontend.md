# Feature: Recording Frontend

## Status
done

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
- [x] A separate review view lists previously extracted musical ideas and
      allows playback of each clip.
- [x] FastAPI has CORS configured to accept requests from the SvelteKit
      dev server's origin (Vite default, typically `http://localhost:5173`)
      for both HTTP and WebSocket connections, and from whatever the
      production origin ends up being once that's decided.
- [x] Has automated tests (pytest for the backend side -- already covered
      by `websocket_audio_streaming`'s suite -- plus browser-level
      tests if a framework like Playwright is introduced for the SvelteKit
      side) covering the above criteria, and the full test suite passes.
      Backend routes backing the review view (`/api/marker`, `/api/ideas`,
      `/api/audio/session/{id}`, `/api/audio/idea/{id}`) have full pytest
      coverage (`test_main.py`, `test_review_api.py`), including live
      round-trips against the real Fulcra account. **Still open**: no
      Playwright/browser-level tests exist for the SvelteKit UI itself --
      verified instead via a real Playwright-driven Chromium load of both
      pages against the live dev servers (see Notes), which is stronger
      than manual-only but short of a checked-in automated test suite.
      Left as visible, honest debt rather than silently checked off.

## Dependencies
websocket_audio_streaming.md, musical_idea_publishing.md (for the review
view to have anything to list)

## Notes
**UX rebuild (this pass):** mirrored v1's actual UX (dark theme, Tailwind,
Session/Marker mode toggle, big circular record/stop button, live log,
"Current Marker" accordion, Review Ideas feed grouped by session with
per-idea waveforms + Key/BPM tags and a full-session waveform with the
marker's lookback window highlighted) as native Svelte components/routes,
rather than porting v1's vanilla-JS/HTML directly. `wavesurfer.js` is used
for playback (same library v1 used), wrapped in a reusable
`WaveformPlayer.svelte` component instead of copy-pasted per-clip wiring.
Two routes: `/` (record) and `/review` (review feed).

Backend gained four new read-only endpoints to back this UI:
`GET /api/marker` (current marker info), `GET /api/ideas` (published
MusicalIdea records), `GET /api/audio/session/{id}` and
`GET /api/audio/idea/{id}` (audio streaming for playback, preferring the
local processed copy and falling back to downloading from Fulcra if it's
gone -- e.g. after a server restart, since local disk is a cache, not the
durable copy). This required adding `upload_session_audio()` to
`idea_publishing.py` and wiring it into `pipeline.py`, since v1 uploaded
processed session/marker audio to Fulcra independent of any extracted
idea, and the review feed's "Full Session Audio" playback needs that same
durability.

Verified live: started both dev servers, streamed the real audio fixtures
through the actual running WebSocket endpoint (marker then session mode),
confirmed a real published idea appeared in the review feed with correct
Key/BPM and playable waveforms (durations matching real audio: 15s idea
clip, 41s full session) -- then deleted the local processed `.wav` and
confirmed `/api/audio/session/{id}` still served audio via the Fulcra
fallback, proving durability actually works, not just the fast path.
Loaded both routes with a real headless Chromium (Playwright) against the
live dev servers and inspected rendered DOM text, not just curl/API
responses.

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
