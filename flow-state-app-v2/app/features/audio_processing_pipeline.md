# Feature: Audio Processing Pipeline (webm → wav)

## Status
not_started

## Description
Once a session's raw audio has been fully received (see
`websocket_audio_streaming.md`), convert the raw uploaded `.webm` file into
a `.wav` file and write it to a `processed/` directory. This is a discrete
step between "raw audio received" and "ready for marker detection /
DSP extraction" — marker detection and clip extraction should operate on
the processed `.wav`, not the raw `.webm`.

## Acceptance Criteria
- [ ] Given a raw session recording as a `.webm` file, produces a valid
      `.wav` file with equivalent audio content (no audible corruption,
      correct duration). Target format: PCM 16-bit, 44.1kHz, stereo.
- [ ] The same conversion is applied to the reference marker sample file
      (also `.webm` -> `.wav`), since downstream marker detection compares
      processed audio to a processed marker, not raw-to-raw.
- [ ] The converted session file is written to a `processed/` directory
      (mirroring the raw file's session ID/name, e.g.
      `raw/<session_id>.webm` -> `processed/<session_id>.wav`).
- [ ] Conversion failure (e.g. corrupt/incomplete `.webm` input) is handled
      gracefully — logged with a clear error, does not crash the service,
      and does not leave a partial/corrupt file in `processed/`.
- [ ] Standalone and testable given any `.webm` input file — does not
      require a live WebSocket session to exercise.
- [ ] Has automated tests (pytest) covering the above criteria, and the
      full test suite passes.

## Dependencies
websocket_audio_streaming.md (raw `.webm` files are what that feature
produces; this feature consumes them)

## Notes
This step was missing from the original feature breakdown — raw audio
doesn't go directly into marker detection/DSP extraction, it's converted
first. Downstream features (`audio_marker_detection.md`,
`dsp_idea_extraction.md`) should be understood as operating on files in
`processed/`, not `raw/`.

Real sample files (a marker recording and a raw session recording) are
available to use as concrete test fixtures for this feature and the ones
downstream of it, rather than relying on synthetic test audio.

Implementation approach (ffmpeg with `-c:a pcm_s16le -ar 44100 -ac 2`,
applied to both session and marker) is informed by a prior implementation
of this same concept, consulted for reference only — this project's code
is independent and does not import or depend on that other codebase.
