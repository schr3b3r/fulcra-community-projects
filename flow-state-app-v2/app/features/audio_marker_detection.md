# Feature: Audio Marker Detection

## Status
done

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
- [x] Detection logic is exposed behind a stable, swappable interface (e.g.
      a single function or small class with a clear signature: audio in,
      list of timestamps out) — not spread across the pipeline as
      inline logic. Anything that calls it (the processing pipeline,
      status tracking, etc.) should depend only on that interface, never
      on which algorithm is behind it.
- [x] Swapping the detection implementation for a different one later
      should require changing/adding one module, not touching callers.
      Prove this isn't just aspirational: e.g. write two trivial
      interchangeable implementations behind the same interface in tests
      (even a dummy "always returns no matches" one) to confirm callers
      genuinely don't care which is plugged in.
- [x] Given a processed `.wav` session file and a processed `.wav` marker
      sample, the system can identify the timestamp(s) where the marker
      occurs.
- [x] Detection compares audio using MFCC (Mel-frequency cepstral
      coefficient) features rather than raw waveform correlation, since
      raw correlation is far more sensitive to noise/gain differences
      between the marker sample and the live session recording. (This is
      the first implementation behind the interface above — not the only
      one that will ever exist.)
- [x] The marker sample is normalized and has leading/trailing silence
      trimmed before comparison, so silence in the reference clip doesn't
      distort the correlation.
- [x] Detected matches are filtered by a correlation-strength threshold
      (tunable) and a minimum time distance between separate detections
      (so one sustained marker isn't reported as many separate hits).
- [x] Validated against the real fixture files in `app/tests/fixtures/`
      (`marker.webm` + `raw_session.webm`) — confirmed ground truth is
      exactly 1 marker detection at ~t=38.6s in that session (see
      `app/tests/fixtures/README.md`).
- [x] False-positive rate is reasonable on a quiet/silent test clip with no
      marker present (i.e. it doesn't hallucinate marker hits).
- [x] Detection logic is a standalone, testable function/module — not
      wired into the WebSocket streaming path yet (that's a later
      integration step).
- [x] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes.

## Notes (continued)
Implemented in `app/audio/marker_detection.py` as `MFCCCorrelationDetector`
behind a `MarkerDetector` protocol, with `NullMarkerDetector` as a second,
trivially different implementation proving the interface boundary is
real (see `test_swappable_interface_null_detector_returns_no_matches`).
Validated live against the real fixtures: exactly 1 detection at
t≈38.59s, matching the documented ground truth. Later wired into
`pipeline.py` and verified through the actual running WebSocket server,
not just in isolation.

**Real bug found via live user testing, fixed:** the fixed-`top_db`
silence trim on the marker sample worked fine for the clean,
high-dynamic-range committed test fixtures, but a real marker recording
captured through a quieter/lower-dynamic-range mic could have almost its
entire duration fall within `top_db` of its own peak amplitude -- e.g.
one real recording trimmed down to ~0.58s. A reference clip that short
isn't distinctive enough to correlate against reliably, and produced 4
"detections" in a session where the marker was actually played only
once (confirmed directly with the user after listening back to their
recording). Fixed with an adaptive relaxation in `_trim_marker`: if the
initial trim leaves less than `min_marker_duration_seconds` (default
1.0s) of audio, progressively relax `top_db` until either a long-enough
clip results or a relaxation ceiling is hit (falling back to the
untrimmed, normalized recording as a last resort). Confirmed against
the user's real session: 4 detections -> 1, matching what they actually
played. Regression test added
(`test_quiet_marker_recording_does_not_trim_to_near_nothing`) using a
synthetic low-dynamic-range signal, since the existing high-quality
fixtures don't exercise this path at all (confirmed: the fix is
additive and doesn't change fixture-based test results).

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
