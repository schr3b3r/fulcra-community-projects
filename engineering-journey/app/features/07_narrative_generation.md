# Feature: Narrative Generation

## Status
done

## Description
Generates a single, paced, engaging Markdown document telling the story of a developer's engineering journey over time. Reads `ActivityRollup` and `NotabilitySignal` records from Fulcra, structures the journey chronologically into top-level periods (quarter/month backbone), expands notable periods (high volume, focus switches, new repos, streaks) with rich detailed prose while compressing routine or quiet periods (gaps, baseline volume) into brief clauses, and outputs a well-formatted Markdown file complete with a provenance appendix linking back to underlying rollup and notability records.

## Acceptance Criteria
- [x] Implements narrative generation module (`narrative.py`) with `generate_journey_narrative` reading `ActivityRollup` and `NotabilitySignal` records from Fulcra using `read_rollups` and `read_notability_signals`.
- [x] Structures the narrative chronologically into top-level sections (quarters or months), pacing narrative depth according to `NotabilitySignal` scores and flags (notable periods get rich multi-paragraph prose; quiet periods are compressed into single sentences/clauses).
- [x] Calls `harness.providers.gemini.call_model` to synthesize engaging, grounded prose for journey sections based strictly on rollup summaries, stats, and notability explanations.
- [x] Includes a clear Provenance Appendix (or sidecar metadata) tracing narrative claims and sections back to specific `ActivityRollup` and `NotabilitySignal` record IDs.
- [x] Provides a documented, runnable CLI/main entrypoint (`python narrative.py`) that writes the generated markdown document directly to disk.
- [x] Verified on real data: generated complete markdown output for real developer history (`schr3b3r`), confirmed that notable periods get specific detailed prose while quiet periods are compressed, and verified markdown structural validity.
- [x] Has automated tests (pytest) covering all criteria above, and the FULL test suite passes — see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `04_rollup_layer_day_week.md`
- `05_rollup_layer_month_quarter_year.md`
- `06_notability_signal.md`

## Notes
- Does NOT create a new durable Fulcra record type — narrative generation is a read, synthesize, and write-to-disk pass.
- Backbone sectioning uses top-level period rollups (quarters or months), walking child week/day/month rollups chronologically.
- Quiet periods are compressed into transition clauses rather than skipped entirely (respecting Interview decision #3 that gaps/quiet periods are real narratively significant data).
