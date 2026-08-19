# V2 Product Prototype Retro

## What Worked Well
1. **Semantic Tagging:** Relying on Fulcra's tagging system (`key:Am`, `bpm:120`) made building the review feed incredibly easy. We didn't need a complex database; Fulcra acts as both the file store and the metadata index.
2. **Wavesurfer Integration:** Falling back to standard `<script>` tags and bypassing WebAudio CORS issues by proxying the audio through our own FastAPI backend proved to be a robust, elegant solution for premium UI playback.

## Open Risks / Future Work
1. **Realtime DSP:** We still need to prove we can detect the audio marker in real-time during the jam session (to flash the UI) without blocking the WebSocket audio stream.
