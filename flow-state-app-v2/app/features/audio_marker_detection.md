# Feature: Audio Marker Detection

## Status
not_started

## Description
Detect a specific "audio marker" (e.g. a particular chord or sound) within
a recorded jam session, so the system knows where in the recording the
musician indicated "save this idea." This replaces manually clicking a save
button, which interrupts the flow of playing.

This is the heart of the application and expected to keep improving over
time (better algorithms, different features, maybe a trained model down
the line). The *implementation* of detection should be treated as
replaceable — everything else in the app should depend on a stable
interface ("given session audio + a marker sample, return timestamps"),
never on the internals of any one detection approach.

## Acceptance Criteria
- [ ] Detection logic is exposed behind a stable, swappable interface (e.g.
      a single function or small class with a clear signature: audio in,
      list of timestamps out) — not spread across the pipeline as
      inline logic. Anything that calls it (the processing pipeline,
      status tracking, etc.) should depend only on that interface, never
      on which algorithm is behind it.
- [ ] Swapping the detection implementation for a different one later
      should require changing/adding one module, not touching callers.
      Prove this isn't just aspirational: e.g. write two trivial
      interchangeable implementations behind the same interface in tests
      (even a dummy "always returns no matches" one) to confirm callers
      genuinely don't care which is plugged in.
- [ ] Given a processed `.wav` session file and a processed `.wav` marker
      sample, the system can identify the timestamp(s) where the marker
      occurs.
- [ ] Detection compares audio using MFCC (Mel-frequency cepstral
      coefficient) features rather than raw waveform correlation, since
      raw correlation is far more sensitive to noise/gain differences
      between the marker sample and the live session recording. (This is
      the first implementation behind the interface above — not the only
      one that will ever exist.)
- [ ] The marker sample is normalized and has leading/trailing silence
      trimmed before comparison, so silence in the reference clip doesn't
      distort the correlation.
- [ ] Detected matches are filtered by a correlation-strength threshold
      (tunable) and a minimum time distance between separate detections
      (so one sustained marker isn't reported as many separate hits).
- [ ] Validated against the real fixture files in `app/tests/fixtures/`
      (`marker.webm` + `raw_session.webm`) — confirmed ground truth is
      exactly 1 marker detection at ~t=38.6s in that session (see
      `app/tests/fixtures/README.md`).
- [ ] False-positive rate is reasonable on a quiet/silent test clip with no
      marker present (i.e. it doesn't hallucinate marker hits).
- [ ] Detection logic is a standalone, testable function/module — not
      wired into the WebSocket streaming path yet (that's a later
      integration step).
- [ ] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes.

## Dependencies
audio_processing_pipeline.md (operates on the processed `.wav` for both
the session and the marker sample, not the raw `.webm`)

## Notes
The original concept notes flagged this as a "deferred spike requiring
physical guitar testing" — that's less of a blocker now: we have a real
sample marker file and a real raw session recording available as test
fixtures, so this can be built and validated against real audio from the
start rather than only synthetic test cases.

A prior implementation of this same concept used MFCC cross-correlation
with per-coefficient normalization, a strict threshold (roughly 0.94x the
max correlation score observed), and a ~5 second minimum distance between
peaks to avoid double-counting a single sustained marker. This is a
reasonable starting point to evaluate against our real sample files, not a
requirement to replicate exactly — tune thresholds against our actual
fixtures rather than assuming these exact numbers transfer.

Explicitly requested: this feature should be built assuming it will change.
The current approach works and is a fine starting point, but detection
quality is expected to keep improving over time, so the interface boundary
matters more here than in most other features — get the seam right now,
even though only one implementation exists behind it today.
