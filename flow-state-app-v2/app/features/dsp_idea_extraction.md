# Feature: DSP Idea Extraction

## Status
not_started

## Description
Once a marker's timestamp is known (see `audio_marker_detection.md`),
extract a fixed-length clip (15 seconds) around that timestamp from the
processed `.wav` session recording (see `audio_processing_pipeline.md`),
and tag it with its musical Key and BPM (tempo). This produces the actual
"musical idea" artifact to be saved.

## Acceptance Criteria
- [ ] Given a processed `.wav` session file and a marker timestamp,
      produces a new audio file containing a 15-second clip: 15 seconds
      *before* the marker timestamp, ending at the marker (a "lookback"
      window, not a centered one) — since the marker is played at the
      moment the musician decides an idea is worth keeping, so the idea
      itself already happened just before that moment.
- [ ] Estimates BPM for the extracted clip and returns it as a number.
- [ ] Estimates musical Key for the extracted clip and returns it as a
      standard key label (e.g. "C major", "A minor").
- [ ] Handles the edge case where the marker occurs less than 15 seconds
      into the session: shift/truncate the window sensibly (e.g. start at
      0 and use whatever duration is available) rather than crashing or
      producing a negative-length clip.
- [ ] Testable standalone (given any audio file + timestamp), independent
      of the marker-detection and streaming features.
- [ ] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes.

## Dependencies
audio_marker_detection.md (for real timestamps in practice, though this
feature can be developed/tested with a manually-specified timestamp)

## Notes
BPM/Key estimation accuracy will vary — acceptance criteria should require
that it *produces* an estimate, not that the estimate is always perfect.
Revisit accuracy expectations once we have a real DSP library in place.

Clip length is deliberately 15 seconds, not 30. In the original concept
project, the actual extraction logic used 15s but a user-facing docs page
described it as 30s — an undetected drift between code and documentation.
Keep this file (and any docs generated from it) in sync with whatever the
actual implementation does; don't let this number drift again.

Extraction is a lookback window ending at the marker, not a centered
window — confirmed by checking a prior implementation of this same concept
directly rather than assuming. If the marker is too close to the start of
the session for a full 15s lookback, fall back to whatever shorter duration
is actually available rather than erroring out.
