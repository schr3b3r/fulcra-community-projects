# Feature: Notability Signal

## Status
done

## Description
Computes a first-pass "notability" signal per rollup period, scoring and flagging periods that stand out based on volume variance vs personal baseline, detected firsts (new repos touched), focus switches (dominant repo changes), streaks of sustained activity, and activity gaps following active stretches. Stores `NotabilitySignal` records durably in Fulcra with explicit provenance chains referencing underlying `ActivityRollup` records, and integrates into `checkpoint.process_with_checkpoint` for resumable execution across multiple periods.

## Acceptance Criteria
- [x] Defines `NotabilitySignal` Fulcra record model and persistence functions (`write_notability_signal(s)`, `read_notability_signals`, `clear_notability_signals`) following the `MomentAnnotation` JSON-note pattern.
- [x] Computes notability score (0.0 - 1.0), categorical flags (`high_volume`, `low_volume_gap`, `new_repo`, `focus_switch`, `streak`), human-readable explanation, and baseline statistics for a rollup period relative to personal historical baseline (comparing like period_types).
- [x] Supports resumable multi-period computation wired into `checkpoint.process_with_checkpoint`.
- [x] Verified on real data: computed notability signals for real rollup periods in Fulcra, confirming notable periods (e.g. highest activity or focus shift) are flagged with explanations matching underlying stats.
- [x] Has automated tests (pytest) covering all criteria above, and the FULL test suite passes — see `app/ENGINEERING_STANDARDS.md`.

## Dependencies
- `01_resumable_backfill_progress.md`
- `04_rollup_layer_day_week.md`
- `05_rollup_layer_month_quarter_year.md`

## Notes
- Notability is relative to the developer's personal baseline (not global thresholds).
- Comparing rollups compares like-with-like (e.g. week vs weeks, month vs months).
- Gaps (low/no activity following active stretches) are treated as significant data points, not noise.
- Explicitly a "first pass" per Interview: each signal check (high volume, gap, new repo, focus switch, streak) is a separate, independently-readable check in `generate_notability_signal` rather than one opaque formula, so a future pass can revise/replace individual checks or scoring weights without touching rollup.py or ingestion/checkpoint code.
- Verified against schr3b3r's real, already-generated week rollups (not just synthetic data under a throwaway username, matching the bar Milestones 4-5 held): the account's single busiest real week (2026-08-20/21, 69 activities vs a 13.5 baseline average) was correctly flagged `high_volume` + `focus_switch` with the highest notability score among its real weeks; two real weeks with zero activity following an active stretch were correctly flagged `low_volume_gap`; a real first-time repo appearance was correctly flagged `new_repo`.
- The initial task run's `git_commit` attempt failed the test gate not because tests failed, but because the gate's `TEST_RUNNER_TIMEOUT_SECONDS` (300s, set during Milestone 3) was no longer enough once this feature's own real tests were added — raised to 480s. Not a code regression, a rising-real-runtime issue as the suite grows; worth revisiting again if it recurs.
