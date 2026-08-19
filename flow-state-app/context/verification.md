# Prototype Verification Log

## Spike 1: Realtime Marker Detection
- **Status:** SKIPPED / DEFERRED.
- **Reason:** Requires physical audio/instrument input to verify effectively without risking false positives in the DSP logic. We will tackle this when the user is in a better environment.

## Spike 2: Fulcra Query Route
- **Status:** VERIFIED.
- **Result:** Successfully queried `MomentAnnotation/c4480f1a-b80e-45b1-9eaa-190bf564485c` (MusicalIdea) via `fulcra-api get-records`. Successfully resolved the tag UUIDs (e.g. `432a60b1-...`) into semantic tags (`key:F#-minor`, `bpm:99`) using `fulcra-api tag list`.
- **Output:** We wrote `spike2_query.py` which transforms the raw Fulcra data into a clean JSON array perfectly suited for a frontend feed (includes `key`, `bpm`, `file_path`, and `recorded_at`).

## Spike 3: Premium Playback UI (Wavesurfer.js)
- **Status:** VERIFIED.
- **Result:** Wrote `prototype/waveform_spike.html`. Successfully integrated `wavesurfer.js` via CDN along with TailwindCSS to build a dark-mode, Samply-inspired asset card. Audio visualizes correctly using rounded bars and a vibrant progress color.
