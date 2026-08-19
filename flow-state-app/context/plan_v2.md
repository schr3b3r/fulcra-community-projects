# Flow State V2 - Technical Plan & Spikes

## Spike 1: Realtime Marker Detection (WebSocket)
- **Goal:** Prove we can run a lightweight heuristic on the incoming 2-second audio chunks in FastAPI to detect the marker and send a real-time UI flash to the frontend.
- **Risk:** High. Real-time DSP in Python might cause blocking or latency issues on the WebSocket.

## Spike 2: Fulcra Query Route
- **Goal:** Prove we can query the `MusicalIdea` custom data type using the `fulcra-api` (or SDK), parse the semantic tags (`#key`, `#bpm`), and serve a clean JSON payload of available ideas.
- **Risk:** Low/Medium. Just need to ensure the Fulcra query syntax handles custom types and tags efficiently.

## Spike 3: Premium Playback UI (Wavesurfer.js)
- **Goal:** Prove we can render a sleek, interactive waveform for a fetched audio file using `wavesurfer.js` within our dark-mode aesthetic.
- **Risk:** Low. Standard frontend integration, but crucial for the UX.

## Production Build
Once spikes are verified, integrate them into the main `app/main.py` and `app/static/index.html` to complete the V2 product prototype.
