# Test Fixtures

Real audio files used to validate the audio pipeline features
(`audio_processing_pipeline`, `audio_marker_detection`,
`dsp_idea_extraction`) against actual data rather than synthetic
approximations.

## Files
- `marker.webm` — a short reference recording of the "audio marker" sound
  (~5.1s raw, ~2.0s after silence-trimming). Raw `.webm`, matching what the
  pipeline actually receives before conversion.
- `raw_session.webm` — a real jam session recording (~41.8s), raw `.webm`,
  containing one instance of the marker being played.

## Validated ground truth
Confirmed by running the marker-detection approach described in
`../../features/audio_marker_detection.md` (ffmpeg conversion to WAV, MFCC
cross-correlation, 94%-of-max threshold, 5s minimum peak distance) directly
against these files:

- `raw_session.webm` contains **exactly 1** marker instance, at
  approximately **t=38.6s**, with a strong, unambiguous correlation score
  (the next-highest peak in the signal is well below the detection
  threshold).

Tests for `audio_marker_detection` should assert against this known result
(1 detection, ~38.6s) rather than a synthetic/assumed value.

## Notes
- Both files are raw `.webm` — NOT pre-converted to `.wav` — deliberately,
  so tests can exercise the full pipeline including the conversion step
  (`audio_processing_pipeline`), rather than skipping it.
- ffmpeg may log "Error parsing Opus packet header" warnings when reading
  these files — this is expected/benign for streamed WebM chunks with
  imperfect headers (the same issue v1's processor worked around with
  `-err_detect ignore_err` during conversion), not file corruption.
- Sourced from the user's own Fulcra account
  (`/agent/flow-state/templates/` and `/agent/flow-state/sessions/raw/`),
  downloaded via the `fulcra-api` CLI for use as committed test fixtures.
