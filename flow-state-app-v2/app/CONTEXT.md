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
  endpoint `/ws/record/{session_id}` that appends binary chunks to
  `raw/<session_id>.webm` as they arrive, with CORS enabled for the
  SvelteKit dev server origin (`http://localhost:5173`).
- `requirements.txt`: fastapi, uvicorn.
- `frontend/`: a minimal SvelteKit app (Svelte 5, TypeScript) with one
  page (`src/routes/+page.svelte`): Record/Stop buttons that capture mic
  audio via `getUserMedia` + `MediaRecorder` and stream it to the backend
  WebSocket. No styling, no review view yet.
- DSP, marker detection, `.webm`->`.wav` conversion, and Fulcra/data
  platform integration are still ahead.

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(this entry)** Pivoted sequencing: instead of building the full
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
