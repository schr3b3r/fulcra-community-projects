# Feature: Packaging as an Installable Hermes Skill

## Status
done

## Description
Unified CLI entrypoint (`app/engineering_journey.py`), Hermes skill spec (`SKILL.md`), developer documentation (`README.md`), and packaging for execution by fresh agents or humans. Unifies ingestion, rollup generation, and notability signal calculation behind `backfill`, and narrative Markdown document generation behind `generate`. Fully supports configurable multi-year history date ranges, environment-variable fallback, explicit credential options, and complete Context-Compute Separation.

## Acceptance Criteria
- [x] Implements unified CLI entrypoint (`app/engineering_journey.py`) supporting two subcommands:
  - `backfill`: orchestrates raw GitHub ingestion (`backfill_full_github_activity`), layered rollups (`generate_day_week_rollups`, `generate_month_rollups`, `generate_layer_rollups`), and personal baseline notability signals (`generate_notability_signals`).
  - `generate`: orchestrates narrative document synthesis (`generate_journey_narrative`) from stored Fulcra rollups and signals.
- [x] Configurable date range supporting multi-year history (`--years`, `--start-date`, `--end-date`) with sensible defaults (~3 years).
- [x] Authentication credentials and account identity passed via CLI arguments or environment variables (`GITHUB_TOKEN`, `GITHUB_USERNAME`, `FULCRA_CREDENTIALS_PATH`), with no hardcoded accounts or `gh` session identity dependencies.
- [x] Created root `SKILL.md` in standard Hermes skill format with step-by-step instructions for fresh agents covering auth verification, dependencies, `backfill` expectations, and `generate` usage.
- [x] Created root `README.md` for human developers covering features, prerequisites, installation, CLI usage, and output structure.
- [x] Verified end-to-end execution of `generate` subcommand against real ingested account data (`schr3b3r`), producing complete, grounded Markdown output.
- [x] Automated unit and orchestration tests (pytest) covering CLI argument parsing, date range calculation, `run_backfill`, and `run_generate` flows in `tests/test_engineering_journey.py`, and the FULL test suite passes — see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `02_github_raw_activity_ingestion.md`
- `03_full_3year_backfill_chunking_resumability.md`
- `04_rollup_layer_day_week.md`
- `05_rollup_layer_month_quarter_year.md`
- `06_notability_signal.md`
- `07_narrative_generation.md`

## Notes
- `SKILL.md` is agent-instruction-shaped; `README.md` is human-shaped.
- Context-Compute Separation is strictly preserved: `backfill` writes durable records to Fulcra; `generate` reads stored records without re-querying GitHub APIs.
