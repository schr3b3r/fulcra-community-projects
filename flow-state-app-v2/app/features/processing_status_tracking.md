# Feature: Processing Status Tracking

## Status
done

## Description
Track the lifecycle of every file that enters the pipeline (raw upload ->
processed -> marker-detected -> idea-extracted -> published) as Fulcra
annotation data, so the state of any given session/file is always
queryable — not inferred from "does this file happen to exist in this
folder." This is the backbone of observability for the whole pipeline: at
any point, it should be possible to answer "was this file processed? is it
currently being processed? did something go wrong, and what?"

## Acceptance Criteria
- [x] A status record is created (via the Fulcra Python SDK, not the CLI)
      when a raw session file is received, in a "received"/"queued" state.
- [x] The status record is updated as the file moves through each pipeline
      stage (e.g. "processing", "processed", "marker_detection",
      "extracting", "published", "failed"), with enough detail to know
      which stage it's in at any time.
- [x] Failures at any stage are recorded as a distinct "failed" status
      with an error message/reason attached — not silently dropped or left
      stuck in an ambiguous "processing" state forever.
- [x] Status for a given session/file can be queried back out (round-trip:
      write a status, read it back, confirm it matches) using the SDK's
      annotation query methods.
- [x] Standalone and testable: creating/updating/querying status records
      should be exercisable without needing a live WebSocket session or
      real audio files.

## Notes (continued)
Implemented in `app/status_tracking.py` using MomentAnnotation records
with a JSON-encoded note payload (session_id/stage/detail/error) plus a
`stage:<stage>` tag (tag names are capped at 30 chars server-side, which
ruled out a session-id tag; session filtering is done by decoding the
note instead). Tests run against the REAL, authenticated Fulcra account
(skipped if no local credentials), not mocks -- round-tripping actual
writes and reads. Discovered and worked around Fulcra's ~1s ingest lag
(annotations aren't immediately queryable after being recorded) by
polling briefly in tests rather than asserting instantaneously.

## Dependencies
none directly, but this is a cross-cutting concern that
`websocket_audio_streaming.md`, `audio_processing_pipeline.md`,
`audio_marker_detection.md`, `dsp_idea_extraction.md`, and
`musical_idea_publishing.md` should all integrate with once built, so that
every stage of the real pipeline reports its status.

## Notes
Uses the Fulcra Python SDK (`fulcra-api` package) directly — specifically
its annotation methods (e.g. `create_annotation` to define the status
annotation type once, `record_data_type`/`validate_records` to write status
updates, and the time-range query methods like `moment_annotations` to
read them back). Do not shell out to the `fulcra-api` CLI or use
subprocess calls for this — use the SDK's Python classes/methods so error
handling, typing, and testability are all first-class.

This was explicitly identified as a strength worth building on: a prior
version of this concept used a `MomentAnnotation`-based pattern to look up
files, and it worked well for making the system's state queryable rather
than requiring directory scanning. This feature extends that same idea
specifically to pipeline *status*, not just to locating files.
