# Feature: Custom Fulcra Data Types Migration

## Status
done

## Description
Migrates all four record kinds (`GitHubBackfillProgress`, `GitHubActivityRaw`,
`ActivityRollup`, `NotabilitySignal`) from being hidden inside generic
`MomentAnnotation` JSON `note` blobs to being real, registered, visible custom
Fulcra data types in the account's catalog -- fulfilling this project's own
stated "why Fulcra, specifically" rationale (custom annotation types as a
deliberate, visible primitive) that Milestones 1-8 built against but never
actually used. New `fulcra_types.py` module provides idempotent
create-or-get-UUID + source-tag helpers; every `write_*`/`read_*`/`clear_*`
function in `checkpoint.py`, `github_activity.py`, `rollup.py`, `notability.py`
was updated to write with the correct `sources` tag and read back merged
(new source-tagged + legacy untagged) for backward compatibility.

## Acceptance Criteria
- [x] New `app/fulcra_types.py` module: `get_or_create_custom_data_type(name, ...)`
      idempotently creates (via `client.create_annotation`) or looks up (via
      `client.v1_catalog`) a real custom Fulcra data type and returns its
      assigned UUID; `get_custom_source_tag(name, ...)` returns the
      `com.fulcradynamics.annotation.<uuid>` source tag used for
      writing/filtering records of that type.
- [x] All four record kinds' `write_*` functions tag written records with
      `sources: [<source_tag>]` for their custom type.
- [x] All four record kinds' `read_*`/`clear_*` functions query Fulcra merging
      new source-tagged records with legacy untagged records (backward
      compatible with data written before this migration), via
      `checkpoint._fetch_annotations_merged`.
- [x] Verified end-to-end on REAL data: all four custom types (`GitHubBackfillProgress`,
      `GitHubActivityRaw`, `ActivityRollup`, `NotabilitySignal`) are genuinely
      visible in this account's real Fulcra catalog (`fulcra-api catalog -c
      user_configured`), not just that records round-tripped. Confirmed
      idempotent creation (second call returns the same UUID, no duplicate
      type created). Confirmed a write+read through the new mechanism for at
      least two record kinds, and confirmed a manually-written legacy
      (untagged) record is still readable alongside a new tagged one for the
      same task/entity.
- [x] Has automated tests (pytest) covering all criteria above
      (`tests/test_fulcra_types.py`), and the FULL test suite passes -- see
      `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `02_github_raw_activity_ingestion.md`
- `04_rollup_layer_day_week.md`
- `06_notability_signal.md`

## Notes
- The JSON `note` payload and its embedded `"record_type"` string key are
  UNCHANGED -- this migration is additive (a `sources` tag alongside the
  existing note format), not a payload format change, so nothing about how
  records are parsed once fetched needed to change.
- `get_or_create_custom_data_type` caches resolved UUIDs in an in-memory
  process-local dict to avoid a catalog round-trip on every write/read within
  a single run, but does NOT assume that cache is durable across process
  restarts -- a fresh process re-queries the catalog (and only creates if
  genuinely missing), so this works correctly for both this
  already-run-before account and a genuinely fresh Fulcra account running
  this skill for the first time.
- A stray `_ProbeTypeTest5` custom type was created during this feature's own
  exploration and cleaned up (archived) before finishing, per this project's
  recurring "clean up ad-hoc Fulcra writes" standard (see `app/CONTEXT.md`'s
  Decisions Log).
