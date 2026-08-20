# Flow State v2: Project Context & Architecture

This document is the durable memory for this app, maintained by the agent
itself across tasks. Read this before starting any new task. Update it
whenever you make an architectural decision, pivot, or complete a
significant milestone — so the next task (run by you or a future agent) has
accurate context without needing to re-derive it from the diff history.

This project is independent: it does not reference or depend on any other
app's code, files, or context. Record all decisions relevant to this app
here.

## The Product
A web app for musicians to record long jam sessions. Instead of clicking a
button to save an idea, they play an "audio marker" (e.g. a specific
chord). A background DSP worker finds that marker and extracts a 15-second
clip, tags it with Key and BPM, and pushes it to a data platform as a
"MusicalIdea".

## Current State
- `main.py`: FastAPI app with `GET /`, `GET /health`, and a WebSocket
  endpoint `/ws/record/{session_id}?mode=session|marker`. Appends binary
  chunks to `raw/<session_id>.webm` as they arrive; a client text message
  `"STOP"` (not closing the socket) signals end-of-recording, after which
  the endpoint runs `pipeline.py`'s full processing pipeline in a worker
  thread and streams progress messages back before closing the
  connection itself. CORS enabled for the SvelteKit dev server origin.
- `audio/` package: `processor.py` (webm->wav via ffmpeg),
  `marker_detection.py` (MFCC-correlation marker detection behind a
  swappable `MarkerDetector` interface), `dsp_extraction.py` (15s
  lookback clip extraction + Key/BPM estimation).
- `fulcra_client.py`: loads local Fulcra credentials into an authenticated
  SDK client (refreshing the token if expired).
- `status_tracking.py`: records/queries pipeline status as
  MomentAnnotation records (JSON note payload + `stage:<stage>` tag).
- `idea_publishing.py`: uploads extracted clips and publishes them as
  `MusicalIdea` records (reusing the type already provisioned by the
  prior v1 app in this Fulcra account).
- `pipeline.py`: orchestrates all of the above into
  `process_marker_recording()` and `process_completed_session()`, called
  by `main.py` once a recording finishes.
- `requirements.txt`: fastapi, uvicorn (librosa/numpy/scipy/soundfile
  come from the harness's own `.venv`, already present).
- `frontend/`: a minimal SvelteKit app (Svelte 5, TypeScript) with one
  page (`src/routes/+page.svelte`): Record/Stop buttons that capture mic
  audio via `getUserMedia` + `MediaRecorder`, stream it to the backend
  WebSocket, send `"STOP"` on Stop (instead of closing), and display
  progress messages received back. No styling, no review view yet.
- Full backend pipeline (record -> convert -> detect marker -> extract
  idea -> publish to Fulcra) is built, tested (40/40 pytest, several
  against the real authenticated Fulcra account), and verified live
  end-to-end through the actual running WebSocket server -- not just unit
  tests. What's NOT done yet: the frontend has no marker-recording mode
  or review/playback view (v1 parity for the UI, not just the backend).

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(this entry)** Built the remaining backend pipeline features
  (`audio_marker_detection`, `dsp_idea_extraction`,
  `processing_status_tracking`, `musical_idea_publishing`) and wired them
  together in `pipeline.py`, called automatically from the WebSocket
  endpoint once a recording finishes -- bringing the backend to v1
  feature parity. Two real integration bugs were found and fixed only by
  testing through the actual running server (not just isolated pytest):
  (1) `find_latest_processed_marker()` originally matched filenames
  against a `marker_*.wav` glob, but marker session_ids don't reliably
  contain that substring, so a successfully processed marker was
  silently never found by the session pipeline -- fixed by tracking the
  "current marker" via an explicit pointer file instead of a filename
  convention; (2) the WebSocket handler originally ran the pipeline only
  after the connection closed, meaning progress messages had nowhere to
  go -- fixed by adopting a prior implementation's protocol: the client
  sends a text `"STOP"` message instead of closing, keeping the socket
  open so the server can stream progress back before closing it itself.
  Also fixed a threading bug where progress callbacks from the
  worker-thread-run pipeline called `asyncio.create_task` directly
  (invalid across threads, silently swallowed) instead of going through
  `loop.call_soon_threadsafe`. All of this was verified against the real,
  authenticated Fulcra account and the real committed audio fixtures,
  through the actual running uvicorn server (WebSocket client scripts,
  not just FastAPI's TestClient) -- confirmed a real published
  `MusicalIdea` record (key "C# Major", 99 BPM, marker at t≈38.6s)
  queryable back from Fulcra afterward.
- **(previous)** Pivoted sequencing: instead of building the full
  backend pipeline (streaming -> processing -> detection -> DSP ->
  publishing) before touching any frontend, pulled forward a deliberately
  minimal slice of `recording_frontend.md` (Record/Stop buttons only) to
  pair with `websocket_audio_streaming.md`, so there's an actual
  clickable, testable path (browser mic -> WebSocket -> file in `raw/`)
  before the rest of the backend exists. Reasoning: catches
  integration issues (CORS, WebSocket compatibility with a real browser,
  files actually landing correctly) early and cheaply, and gives the user
  something to test well before the full spec is done, rather than reading
  pytest output for a long stretch. Full frontend polish (review view,
  styling, Playwright tests) remains deferred to when `recording_frontend`
  is picked up in full. `websocket_audio_streaming` was built to its full
  acceptance criteria (not a partial slice) — only its *sequencing*
  relative to other backend features changed, not its scope.
  Verified live: FastAPI (port 8000) + Vite dev server (port 5173) running
  side by side, CORS preflight succeeding, and a scripted WebSocket client
  (standing in for a real browser mic, since this sandbox has no real
  audio device) streaming the `marker.webm` fixture and landing a
  byte-identical, ffprobe-valid file in `raw/`.
- **(previous)** Introduced `features/` — a structured, per-feature spec
  (one file per feature + an INDEX.md), separate from this CONTEXT.md.
  CONTEXT.md stays retrospective (architecture decisions, history);
  features/ is prescriptive (what should exist, with acceptance criteria).
- **(initial)** Scaffolded a minimal FastAPI skeleton with health-check and
  root endpoints, deliberately deferring all audio/DSP/data-platform work.
