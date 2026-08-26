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
- `main.py`: FastAPI app with `GET /`, `GET /health`, a WebSocket
  endpoint `/ws/record/{session_id}?mode=session|marker`, and four
  read-only review endpoints: `GET /api/marker`, `GET /api/ideas`,
  `GET /api/audio/session/{id}`, `GET /api/audio/idea/{id}` (each prefers
  local disk, falls back to Fulcra if the local copy is gone). The
  WebSocket endpoint appends binary chunks to `raw/<session_id>.webm` as
  they arrive; a client text message `"STOP"` (not closing the socket)
  signals end-of-recording, after which the endpoint runs `pipeline.py`'s
  full processing pipeline in a worker thread and streams progress
  messages back before closing the connection itself. CORS enabled for
  the SvelteKit dev server origin.
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
  prior v1 app in this Fulcra account); also uploads processed
  session/marker audio to Fulcra (`upload_session_audio`) for durable
  "Full Session Audio" playback independent of any extracted idea.
- `review_api.py`: read-only helpers backing the review endpoints --
  listing published ideas, current-marker info, resolving local vs.
  Fulcra-backed audio paths.
- `pipeline.py`: orchestrates all of the above into
  `process_marker_recording()` and `process_completed_session()`, called
  by `main.py` once a recording finishes.
- `requirements.txt`: fastapi, uvicorn (librosa/numpy/scipy/soundfile
  come from the harness's own `.venv`, already present).
- `frontend/`: a SvelteKit app (Svelte 5, TypeScript, Tailwind v4,
  wavesurfer.js) with two routes: `/` (record page -- Session/Marker mode
  toggle, big circular record/stop button, live progress log, "Current
  Marker" accordion with waveform playback) and `/review` (review feed --
  published ideas grouped by session, each with its own waveform +
  Key/BPM tags, plus the full session waveform with the marker's lookback
  window highlighted as a region). Mirrors v1's UX, rebuilt as native
  Svelte components rather than ported vanilla JS/HTML. `$lib/api.ts`
  centralizes backend API calls/types (relative URLs, proxied through
  Vite's dev server -- see `vite.config.ts` -- rather than an absolute
  `localhost:8000` origin, so only the frontend's port needs to be
  reachable from the browser); `$lib/WaveformPlayer.svelte` is a reusable
  wavesurfer wrapper used by both routes.
- Full backend pipeline (record -> convert -> detect marker -> extract
  idea -> publish to Fulcra, including durable session-audio storage) and
  the full frontend (recording UI + review feed) are built, tested
  (59/59 pytest, many against the real authenticated Fulcra account), and
  verified live end-to-end -- both through the actual running WebSocket
  server and via a real headless-Chromium (Playwright) load of both
  frontend routes against the live dev servers, AND against the user's
  own real recorded session (marker detection was found and fixed to
  have false positives on quiet recordings; see Decisions Log). v1 UX
  parity achieved. What's NOT done yet: no checked-in browser-level
  (Playwright) automated test suite for the frontend itself (verified
  manually/live instead); no realtime marker detection (v1 also deferred
  this); production frontend deployment shape (static export vs.
  separate Node process) still an open decision, irrelevant to local dev.

See `features/INDEX.md` for the full, structured feature spec — what the
app is supposed to do, broken into individually-scoped features with
acceptance criteria and status. This file (CONTEXT.md) records *why*
things are built the way they are and what's already happened; the
features/ directory records *what* the app should do, including work not
yet started. Consult both, but don't duplicate one into the other.

## Decisions Log
(Newest at the top. One entry per meaningful decision — not a full
chronological journal, just high-signal architectural notes.)

- **(this entry)** Added an optional metadata-only provenance and consent
  generator for the proposed Maha integration. It hashes the full session,
  marker sample and selected idea clip locally after explicit opt-in, binds the
  transformation metadata and resulting MusicalIdea reference, and can derive
  a narrower audience-bound share record that omits session/marker digests.
  Consent and audience references are retained only as hashes. It is deliberately
  not wired into the automatic pipeline yet: a real session must not be read
  for this additional purpose until the musician has chosen a sharing scope.
  This layer does not change or attest Fulcra's existing storage/access policy,
  and it does not claim creative ownership or DSP accuracy.
- **(this entry)** Fixed a real marker-detection bug found via live user
  testing: playing the marker once produced 4 "detections" in the review
  feed (one with an invisible highlighted region on the full-session
  waveform -- 0.18% of the timeline width, not a rendering bug, a real
  false-positive at t≈0.6s). Root cause: the marker sample's silence-trim
  used a fixed `top_db` that works for the clean, high-dynamic-range
  committed test fixtures, but the user's actual recording (quieter mic)
  had almost its entire duration within `top_db` of its own peak,
  trimming it down to ~0.58s -- too short/generic a reference clip to
  correlate against reliably. Fixed with adaptive relaxation in
  `MFCCCorrelationDetector._trim_marker` (`app/audio/marker_detection.py`):
  if the initial trim leaves less than `min_marker_duration_seconds`
  (default 1.0s), progressively relax `top_db` until either a long-enough
  clip results or a ceiling is hit (falling back to the untrimmed,
  normalized recording as a last resort). Verified against the user's
  real session: 4 false positives -> 1, matching what they confirmed
  (after listening back to their own recording) was their one actual
  marker play. Cleaned up the incorrect idea records/files from Fulcra
  and republished the corrected single idea. New regression test
  (`test_quiet_marker_recording_does_not_trim_to_near_nothing`) uses a
  synthetic low-dynamic-range signal, since the existing fixtures are too
  clean to exercise this failure mode at all -- confirmed the fix doesn't
  change fixture-based results (59/59 passing). Also clarified in
  `idea_publishing.get_published_ideas()` that it deliberately only
  understands this codebase's own JSON-note record format, not a prior
  implementation's different plain-text-note-plus-tags format -- a
  scope decision (not worth a permanent compatibility parser for a small,
  fixed number of legacy records), not an oversight.
- **(previous)** Fixed a real bug reported directly by the user:
  `/review` failed with "Failed to fetch". Root cause: the frontend
  called `http://localhost:8000` directly from the browser
  (`BACKEND_HTTP_ORIGIN`/`BACKEND_WS_ORIGIN` in `$lib/api.ts`), which only
  works if the browser can reach port 8000 directly -- fails when only
  the frontend's port is reachable (e.g. via port forwarding into this
  sandbox). Fixed by adding a Vite dev-server proxy (`vite.config.ts`,
  forwarding `/api/*` and `/ws/*` to the backend server-side) and
  switching the frontend to relative URLs plus a `recordingSocketUrl()`
  helper built from the page's own current origin. Now only the
  SvelteKit dev server's port needs to be reachable from the browser.
  Verified: curled `/api/ideas`, `/api/marker`, `/api/audio/session/{id}`
  through the frontend port alone; opened a real WebSocket through that
  port and confirmed it proxied through to the pipeline correctly; loaded
  `/review` with real headless Chromium and confirmed no fetch errors.
- **(previous)** Rebuilt the frontend to mirror v1's actual UX (dark
  theme, Session/Marker mode toggle, big record button, live log,
  "Current Marker" accordion, Review Ideas feed grouped by session with
  per-idea waveforms + Key/BPM tags and a full-session waveform with the
  marker's lookback window highlighted), as native Svelte
  components/routes rather than porting v1's vanilla JS/HTML wholesale.
  Added Tailwind v4 and wavesurfer.js to the frontend. Two routes: `/`
  (record) and `/review` (review feed), sharing `$lib/api.ts` (typed
  backend client) and `$lib/WaveformPlayer.svelte` (reusable wavesurfer
  wrapper). Backend gained four review-facing endpoints (`/api/marker`,
  `/api/ideas`, `/api/audio/session/{id}`, `/api/audio/idea/{id}`), each
  preferring local disk and falling back to Fulcra if the local copy is
  gone. Discovered mid-build that the pipeline never durably stored
  processed session/marker audio in Fulcra (only extracted idea clips
  were uploaded) -- v1 did upload full session audio too, and the review
  feed's "Full Session Audio" playback needs that durability. Fixed by
  adding `upload_session_audio()` and wiring it into both
  `process_marker_recording()` and `process_completed_session()`.
  Verified by deleting the local processed `.wav` after a real pipeline
  run and confirming `/api/audio/session/{id}` still served correct audio
  via the Fulcra fallback. Also verified the actual rendered frontend
  (not just API responses) using a real headless-Chromium session
  (Playwright, installed for this verification only, not added as a
  project dependency) against the live dev servers, confirming both
  routes render real data with correct waveform durations.
- **(previous)** Built the remaining backend pipeline features
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
