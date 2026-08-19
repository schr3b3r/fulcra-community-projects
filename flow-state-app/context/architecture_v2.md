# Flow State V2 - Architecture Map

## 1. Frontend (UI/UX Shell)
- **Tech:** HTML/CSS/JS (Lightweight React/Vue or Vanilla JS + TailwindCSS) for a sleek, dark-mode aesthetic (Samply-inspired).
- **Playback:** `wavesurfer.js` for premium visual waveform playback of `MusicalIdea` assets.
- **State:** Manages Recording states (Start/Stop), Realtime Marker Feedback (flashing UI), and Review Feed filtering (Key/BPM).

## 2. Backend (FastAPI)
- **Realtime DSP Route:** Inject lightweight detection into the existing WebSocket stream to send `{"type": "marker_detected"}` back to the client.
- **Fulcra Query Route:** New endpoint (`GET /api/ideas`) leveraging Fulcra SDK to query `MusicalIdea` records, parse semantic tags (`#key:Am`, `#bpm:120`), and return clean JSON for the frontend.

## 3. Data Layer (Fulcra)
- **Status:** Unchanged. Relying on the existing `MusicalIdea` custom type and background `worker/processor.py` for asynchronous heavy DSP and data persistence.
