# Flow State: Project Context & Architecture

This document contains the distilled knowledge, decisions, and architectural pivots from the creation of the Flow State app. Read this before iterating on the codebase.

## The Product
A web app for musicians to record long jam sessions. Instead of clicking a button to save an idea, they play an "audio marker" (e.g., a specific chord). A background DSP worker finds that marker and extracts a 30-second clip, tags it with Key and BPM, and pushes it to Fulcra as a `MusicalIdea` (a `MomentAnnotation`).

## The Stack
- **Frontend:** HTML/JS, TailwindCSS, `wavesurfer.js` (playback), D3.js (color coding).
- **Backend:** Python FastAPI.
- **Data Layer:** Fulcra (Handles storage and semantic querying via `fulcra-api`).

## Key Architectural Pivots (The "Why")
1. **WebSockets over Browser Buffering:** Browsers drop standard `MediaRecorder` buffers if they crash. We chunk audio every 2 seconds via WebSockets to FastAPI so the jam is safely streamed to disk in real-time.
2. **FastAPI over 3rd-Party Bots:** We abandoned Discord/Telegram bots because they introduce heavy C++ dependencies or end-to-end encryption blockers for raw audio streaming. The browser `getUserMedia` gives us pristine audio (with echo cancellation disabled).
3. **Semantic Querying over File Scanning:** The frontend Review Feed does *not* scan directories for WAV files. It hits `/api/ideas`, which queries Fulcra for `MomentAnnotation` metadata. Fulcra acts as the database, making the UI instantly queryable without a traditional SQL backend.
4. **Proxy Audio Streaming:** To bypass strict WebAudio CORS restrictions on the frontend, FastAPI serves a proxy route (`/api/audio`) that downloads the file from Fulcra and streams it to `wavesurfer.js`.

## Current State & Next Steps
We followed the `fulcra-rapid-prototype` 7-step pipeline. We are currently at **Phase 6 (Build)**, having completed a V2 UX polish. 
- **Deferred Spike:** "Realtime Marker Detection". Currently, DSP extraction happens asynchronously after the session. We want to try detecting the marker in real-time on the incoming WebSocket chunks to flash the UI, but this requires physical testing with a real guitar.
