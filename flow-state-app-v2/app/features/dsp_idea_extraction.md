# Feature: DSP Idea Extraction

## Status
not_started

## Description
Once a marker's timestamp is known (see `audio_marker_detection.md`),
extract a fixed-length clip (e.g. 30 seconds) around that timestamp from
the full session recording, and tag it with its musical Key and BPM
(tempo). This produces the actual "musical idea" artifact to be saved.

## Acceptance Criteria
- [ ] Given a full session audio file and a marker timestamp, produces a
      new audio file containing a ~30-second clip centered on (or
      following) that timestamp.
- [ ] Estimates BPM for the extracted clip and returns it as a number.
- [ ] Estimates musical Key for the extracted clip and returns it as a
      standard key label (e.g. "C major", "A minor").
- [ ] Handles edge cases: marker near the very start or end of the session
      (clip should be truncated/shifted sensibly, not crash).
- [ ] Testable standalone (given any audio file + timestamp), independent
      of the marker-detection and streaming features.

## Dependencies
audio_marker_detection.md (for real timestamps in practice, though this
feature can be developed/tested with a manually-specified timestamp)

## Notes
BPM/Key estimation accuracy will vary — acceptance criteria should require
that it *produces* an estimate, not that the estimate is always perfect.
Revisit accuracy expectations once we have a real DSP library in place.
