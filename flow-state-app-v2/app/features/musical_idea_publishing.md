# Feature: Musical Idea Publishing

## Status
done

## Description
Push an extracted musical idea (audio clip + Key + BPM metadata) to Fulcra
for durable storage, so it can be queried and reviewed later without the
frontend needing to scan local files directly. This uses the same
"annotation as database" pattern already proven for status tracking (see
`processing_status_tracking.md`): the clip is uploaded as a file, and its
metadata is recorded as a queryable annotation record referencing that
file.

## Acceptance Criteria
- [x] Given an extracted clip (audio file) and its metadata (Key, BPM,
      timestamp, session ID), the clip is uploaded to Fulcra via the
      Python SDK's `upload_file`.
- [x] A corresponding record (e.g. a `MusicalIdea` annotation/data type) is
      created via the SDK's `record_data_type`, referencing the uploaded
      file and carrying its Key/BPM/timestamp metadata as tags or fields.
- [x] The published record can be retrieved/queried afterward via the SDK
      (round-trip test: publish, then query it back, confirm the data
      matches) — not just trusting that the upload call returned success.
- [x] Failure to publish (e.g. network/auth error) is handled gracefully:
      logged clearly, does not crash the pipeline, does not lose or
      corrupt the locally extracted clip, and is reflected in this file's
      status via `processing_status_tracking.md` (a "failed" status, not a
      silently stuck one).

## Notes (continued)
Implemented in `app/idea_publishing.py`, reusing the `MusicalIdea` custom
annotation type already provisioned in this Fulcra account by the prior
v1 app's `setup_fulcra.sh` (confirmed present via the catalog rather than
assumed). Custom/user-configured annotation subtypes are recorded against
their *base* type (MomentAnnotation) tagged with a
`com.fulcradynamics.annotation.<uuid>` source -- confirmed by reading the
`fulcra-api` CLI's own `record` command implementation, not guessed at.
Tested against the REAL Fulcra account: a real extracted clip (derived
from the committed audio fixtures) is uploaded and published, then
queried back and confirmed to match. Later wired into `pipeline.py` and
verified through the actual running WebSocket server end-to-end.

## Dependencies
dsp_idea_extraction.md, processing_status_tracking.md

## Notes
Uses the Fulcra Python SDK (`fulcra-api` package) directly — not the CLI,
not subprocess/shell calls. This is a deliberate departure from a prior
implementation of this same concept, which shelled out to a CLI
(`uvx fulcra-api ...`) for uploads and record creation; the SDK gives real
Python objects, proper error handling, and testability that CLI-shelling
does not.

If the SDK requires a specific data type to exist in the user's Fulcra
account before records can be created against it (as a prior
implementation needed to look up a `MusicalIdea` type ID dynamically),
handle that lookup/creation explicitly and fail with a clear error message
if it's missing — don't fail silently or crash with an unhandled
exception.
