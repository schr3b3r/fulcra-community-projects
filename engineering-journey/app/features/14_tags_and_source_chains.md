# Feature: Real Fulcra Tags for Filterable Dimensions, Deeper Source Chains

## Status
done

## Description
Fixes a real gap flagged directly by a user reviewing this project's Fulcra usage: this project
had never used Fulcra's tag primitive at all, despite having several obvious filterable dimensions
(repo name, activity type, period type, notability flags like `focus_switch`) sitting only inside
each record's JSON `note` payload, invisible to anyone querying via the Fulcra API directly.
Separately, every record's `sources` array was always exactly one element (the custom-type identity
tag used purely for read filtering), never encoding real provenance.

The implementation:
1. `fulcra_types.get_or_create_tag_uuids(tag_names, client)`: resolves a list of tag names to real
   Fulcra tag UUIDs via `client.create_tags()` (idempotent batch call), caching results in a
   process-local `_TAG_UUID_CACHE` so repeated resolution of the same tag name across a run is free
   after the first lookup — mirrors the existing custom-data-type UUID caching pattern.
2. `GitHubActivityRaw.to_fulcra_record()`: accepts `tag_ids` (attached as the record's `tags` array)
   and an optional `sources` override; by default builds a source chain `["com.github",
   "com.github.repo.<repo_name with '/' -> '.'>", <custom-type identity tag>]`. `write_raw_activities`
   resolves `repo_name`/`activity_type` tag UUIDs once per batch write call, not per record.
3. `ActivityRollup`/`NotabilitySignal.to_fulcra_record()`: same `tag_ids`/`sources` parameters;
   default source chain is `["com.github", "agent.engineering-journey.<rollup|notability>",
   <custom-type identity tag>]`, explicitly marking these as DERIVED/computed data rather than raw
   ingested content. `write_rollups`/`write_notability_signals` resolve `period_type` (and, for
   signals, every flag in `flags`) as real tags, once per batch write call.
4. In all cases the custom-type identity tag remains the LAST element of `sources` — this is what
   `_fetch_annotations_merged`'s `source=` read filtering depends on, and was preserved deliberately.

## Acceptance Criteria
- [x] `GitHubActivityRaw` records carry real tags for `repo_name` and `activity_type`.
- [x] `NotabilitySignal` records carry a real tag for `period_type` and one real tag per flag in `flags`.
- [x] `ActivityRollup` records carry a real tag for `period_type`.
- [x] Tag UUIDs are resolved once per distinct value per batch write call, not once per record.
- [x] `sources` arrays carry real lineage (origin -> intermediate -> custom-type identity tag), with the identity tag preserved as the last element.
- [x] Automated unit tests (mocked) cover tag resolution determinism/dedup/caching and `to_fulcra_record()`'s tags/sources output for all three record kinds.
- [x] A real live test proves `get_or_create_tag_uuids` resolves real tag UUIDs against the real Fulcra account and is idempotent across repeated calls.
- [x] FULL test suite passes -- see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `02_github_raw_activity_ingestion.md`
- `04_rollup_layer_day_week.md`
- `06_notability_signal.md`
- `09_custom_fulcra_data_types.md`
- `13_recorded_at_real_event_time.md`

## Notes
- Real cost trade-off, not free: resolving N distinct tag values costs N-ish `create_tags`/`tags()`
  API calls per run (once, cached) -- cheap relative to per-item backfill work, but a genuinely new
  consideration no prior milestone incurred.
- Concrete example of the value this unlocks: finding every notable focus-switch moment across a
  3-year engineering journey goes from "read every `NotabilitySignal` record and parse its JSON
  note" to a single tag-filtered query.
- Deliberately did not change what data is computed or ingested -- only how existing data gets
  tagged/sourced when written to Fulcra.
