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
| [09_custom_fulcra_data_types.md](09_custom_fulcra_data_types.md) | done | Migrated all record kinds from generic MomentAnnotation blobs to real, visible custom Fulcra data types, with backward-compatible reads |
| [10_private_repo_discovery.md](10_private_repo_discovery.md) | done | Fixed private repo discovery in `enumerate_repositories()` by unioning `GET /user/repos` listing with GraphQL contributions Collection |
| [11_stale_checkpoint_masking_fix.md](11_stale_checkpoint_masking_fix.md) | done | Delta-aware backfill: detects repos not covered by a prior completed checkpoint and ingests only those, without reprocessing/duplicating already-covered repos |
| [12_skip_repos_no_activity.md](12_skip_repos_no_activity.md) | done | Skips repos with zero author-scoped activity across the full requested range before per-chunk ingestion, via a one-time-per-repo `has_author_activity` pre-check |
| [13_recorded_at_real_event_time.md](13_recorded_at_real_event_time.md) | done | `recorded_at` reflects real historical event/period time across all writers, not ingestion time; deterministic IDs fix a raw-activity dedup gap |
| [14_tags_and_source_chains.md](14_tags_and_source_chains.md) | done | Real Fulcra tags for repo_name/activity_type/period_type/notability flags, and deeper source-chain lineage marking derived vs. raw data |
| [15_date_range_filter_fix.md](15_date_range_filter_fix.md) | done | Fixed `read_rollups`/`read_notability_signals` treating start_date/end_date as exact-string matches instead of range filters, which silently produced zero NotabilitySignal records on a real full-scale 3-year backfill |
| [16_checkpoint_duration_annotation_migration.md](16_checkpoint_duration_annotation_migration.md) | done | Migrated GitHubBackfillProgress checkpoints from MomentAnnotation to DurationAnnotation, using the platform's native start/end time instead of a single ingestion-time instant |

## Status values
- `not_started` — described but no work done yet.
- `in_progress` — actively being built; may be partially working.
- `done` — acceptance criteria met and verified (not just claimed).
