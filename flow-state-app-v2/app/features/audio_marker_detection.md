# Feature: Audio Marker Detection

## Status
not_started

## Description
Detect a specific "audio marker" (e.g. a particular chord or sound) within
a recorded jam session, so the system knows where in the recording the
musician indicated "save this idea." This replaces manually clicking a save
button, which interrupts the flow of playing.

## Acceptance Criteria
- [ ] Given a recorded audio file and a reference marker sample, the system
      can identify the timestamp(s) where the marker occurs.
- [ ] Works on a synthetic test case first (e.g. a marker sound
      artificially inserted into a longer audio clip at a known timestamp)
      before requiring any real instrument/guitar testing.
- [ ] False-positive rate is reasonable on a quiet/silent test clip with no
      marker present (i.e. it doesn't hallucinate marker hits).
- [ ] Detection logic is a standalone, testable function/module — not
      wired into the WebSocket streaming path yet (that's a later
      integration step).

## Dependencies
none (can be developed and tested independently of the streaming/backend
work, using pre-recorded test audio files)

## Notes
The original concept notes flagged this as a "deferred spike requiring
physical guitar testing" — that's true for validating real-world accuracy,
but the core detection algorithm can and should be built and tested against
synthetic/recorded audio first, so we're not blocked on physical testing to
make initial progress.
