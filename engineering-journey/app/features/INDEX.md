# Feature Index

Structured, per-feature specs for this app. Each feature lives in its own
file in this directory, following a consistent template (see any existing
feature file, or `_TEMPLATE.md`). Update this table whenever a feature's
status changes.

| Feature | Status | Description |
|---|---|---|
| [01_resumable_backfill_progress.md](01_resumable_backfill_progress.md) | done | Resumable backfill progress checkpointing stored durably in Fulcra |
| [02_github_raw_activity_ingestion.md](02_github_raw_activity_ingestion.md) | done | GitHub API client + durable, checkpointed raw activity ingestion |
| [03_full_3year_backfill_chunking_resumability.md](03_full_3year_backfill_chunking_resumability.md) | done | Full ~3-year multi-repo/multi-period chunked backfill with real at-scale resumability |
| [04_rollup_layer_day_week.md](04_rollup_layer_day_week.md) | done | ActivityRollup record type + resumable day/week rollup generation with real LLM narrative summaries |
| [05_rollup_layer_month_quarter_year.md](05_rollup_layer_month_quarter_year.md) | done | Month (older history) + quarter/year (both) rollup generation with hierarchical provenance chains |
| [06_notability_signal.md](06_notability_signal.md) | done | First-pass personal baseline, volume variance, firsts, focus switches, streaks, and gaps notability scoring |
| [07_narrative_generation.md](07_narrative_generation.md) | done | Reads the full rollup + notability layer and synthesizes one paced Markdown journey document with a provenance appendix |
| [08_packaging_hermes_skill.md](08_packaging_hermes_skill.md) | done | Unified CLI entrypoint, SKILL.md, README.md, requirements.txt, and packaging for execution by fresh agents or humans |

## Status values
- `not_started` — described but no work done yet.
- `in_progress` — actively being built; may be partially working.
- `done` — acceptance criteria met and verified (not just claimed).
