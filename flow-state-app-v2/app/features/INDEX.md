# Feature Index

Structured, per-feature specs for this app. Each feature lives in its own
file in this directory, following a consistent template (see any existing
feature file, or `_TEMPLATE.md`). Update this table whenever a feature's
status changes.

| Feature | Status | Description |
|---|---|---|
| [backend_skeleton](./backend_skeleton.md) | done | Minimal FastAPI app with health-check and root endpoints. |
| [websocket_audio_streaming](./websocket_audio_streaming.md) | not_started | Stream audio from the browser to the backend over WebSockets in small chunks, saved to disk in real time. |
| [audio_marker_detection](./audio_marker_detection.md) | not_started | Detect a specific audio marker (e.g. a chord) within a recorded session. |
| [dsp_idea_extraction](./dsp_idea_extraction.md) | not_started | Extract a 30-second clip around a detected marker and tag it with Key and BPM. |
| [musical_idea_publishing](./musical_idea_publishing.md) | not_started | Push an extracted musical idea to a data platform for storage and later retrieval. |
| [recording_frontend](./recording_frontend.md) | not_started | Browser UI to capture audio, stream it to the backend, and review extracted ideas afterward. |

## Status values
- `not_started` — described but no work done yet.
- `in_progress` — actively being built; may be partially working.
- `done` — acceptance criteria met and verified (not just claimed).
