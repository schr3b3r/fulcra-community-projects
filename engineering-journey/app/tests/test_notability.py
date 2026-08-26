"""Tests for NotabilitySignal model, calculation logic, persistence, and resumability."""

import json
import uuid
import pytest

from checkpoint import SimulatedInterruptError, clear_checkpoint
from fulcra_client import get_fulcra_client
from rollup import (
    ActivityRollup,
    clear_rollups,
    read_rollups,
    write_rollups,
)
from notability import (
    NotabilitySignal,
    clear_notability_signals,
    compute_baseline_stats,
    generate_notability_signal,
    generate_notability_signals,
    read_notability_signals,
    write_notability_signal,
    write_notability_signals,
)


def test_notability_signal_dataclass_serialization():
    signal = NotabilitySignal(
        period_type="week",
        start_date="2026-06-01",
        end_date="2026-06-07",
        username="devuser",
        notability_score=0.85,
        flags=["high_volume", "new_repo"],
        explanation="High volume (35 total activities, 2.5x baseline average of 14.0); First activity in new repository: org/new-service.",
        source_rollup_id="rollup_rec_001",
        baseline_stats={
            "mean_total_activities": 14.0,
            "std_total_activities": 3.2,
            "activity_ratio": 2.5,
        },
    )

    data = signal.to_dict()
    assert data["record_type"] == "NotabilitySignal"
    assert data["period_type"] == "week"
    assert data["username"] == "devuser"
    assert data["notability_score"] == 0.85
    assert "high_volume" in data["flags"]
    assert "new_repo" in data["flags"]
    assert data["source_rollup_id"] == "rollup_rec_001"

    reconstructed = NotabilitySignal.from_dict(data, record_id="ann_sig_100")
    assert reconstructed.period_type == signal.period_type
    assert reconstructed.username == signal.username
    assert reconstructed.notability_score == 0.85
    assert reconstructed.flags == signal.flags
    assert reconstructed.id == "ann_sig_100"

    fulcra_record = signal.to_fulcra_record()
    assert "recorded_at" in fulcra_record
    assert fulcra_record["recorded_at"] == "2026-06-01T00:00:00Z"
    assert "note" in fulcra_record


def test_notability_signal_recorded_at_reflects_historical_start_date():
    """Verify NotabilitySignal recorded_at reflects start_date formatted as ISO UTC timestamp."""
    signal = NotabilitySignal(
        period_type="month",
        start_date="2024-03-01",
        end_date="2024-03-31",
        username="histuser",
        notability_score=0.9,
        flags=["high_volume"],
        explanation="March 2024 high volume.",
    )

    rec = signal.to_fulcra_record()
    assert rec["recorded_at"] == "2024-03-01T00:00:00Z"
    assert rec["recorded_at"] != signal.updated_at

    note = json.loads(rec["note"])
    assert note["updated_at"] == signal.updated_at
    assert note["start_date"] == "2024-03-01"


def test_notability_signal_to_fulcra_record_flag_tags():
    """Verify to_fulcra_record attaches a tags array when tag_ids is passed --
    this is the primary mechanism for making notability flags (e.g.
    'focus_switch') genuinely queryable as real Fulcra tags rather than
    only readable by parsing the JSON note payload."""
    signal = NotabilitySignal(
        period_type="week",
        start_date="2026-06-01",
        end_date="2026-06-07",
        username="testuser",
        notability_score=0.8,
        flags=["focus_switch", "new_repo"],
        explanation="Real focus switch detected.",
    )

    tag_ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]
    rec = signal.to_fulcra_record(tag_ids=tag_ids)

    assert rec["tags"] == tag_ids


def test_notability_signal_to_fulcra_record_source_chain_marks_derived_data():
    """Verify to_fulcra_record's default sources chain marks this as
    DERIVED/computed data (distinct from raw ingested GitHub content),
    with the custom-type identity tag as the last element."""
    signal = NotabilitySignal(
        period_type="week",
        start_date="2026-06-01",
        end_date="2026-06-07",
        username="testuser",
        notability_score=0.5,
        flags=[],
    )

    identity_tag = "com.fulcradynamics.annotation.some-uuid"
    rec = signal.to_fulcra_record(source_tag=identity_tag)

    assert rec["sources"][-1] == identity_tag
    assert "agent.engineering-journey.notability" in rec["sources"]


def test_read_notability_signals_date_range_overlap_and_outer_bounds():
    """Verify read_notability_signals performs genuine range-overlap filtering
    instead of exact string matching.

    Regression test for a real bug found via a live full-scale backfill: a
    real account with 310 real ActivityRollup records ended up with ZERO
    NotabilitySignal records after a real backfill run, because
    read_rollups/read_notability_signals treated start_date/end_date as
    exact-string-equality filters instead of range filters, so any real
    multi-period query (e.g. a 3-year backfill window) silently returned 0
    results -- even though the caller (generate_notability_signals) already
    assumed and correctly implemented range semantics downstream, it never
    got real data to operate on. This is exactly that failure shape: query
    with OUTER bounds that don't exactly match any single record's own
    start_date/end_date, and assert all overlapping records are still
    returned.
    """
    client = get_fulcra_client()
    test_user = f"rangesignaluser_{uuid.uuid4().hex[:6]}"

    s1 = NotabilitySignal(
        period_type="month",
        start_date="2024-01-01",
        end_date="2024-01-31",
        username=test_user,
        notability_score=0.3,
    )
    s2 = NotabilitySignal(
        period_type="month",
        start_date="2024-02-01",
        end_date="2024-02-29",
        username=test_user,
        notability_score=0.4,
    )
    s3 = NotabilitySignal(
        period_type="month",
        start_date="2024-03-01",
        end_date="2024-03-31",
        username=test_user,
        notability_score=0.5,
    )

    try:
        write_notability_signals([s1, s2, s3], client=client)

        # Query with OUTER bounds matching the full Q1 range -- none of
        # these exactly equal any single record's start_date/end_date.
        q1_results = read_notability_signals(
            username=test_user,
            start_date="2024-01-01",
            end_date="2024-03-31",
            client=client,
            expected_min_count=3,
            timeout_seconds=20.0,
        )
        assert len(q1_results) == 3

        # Query with a narrower range covering only Feb
        feb_results = read_notability_signals(
            username=test_user,
            start_date="2024-02-01",
            end_date="2024-02-28",
            client=client,
            expected_min_count=1,
            timeout_seconds=10.0,
        )
        assert len(feb_results) == 1
        assert feb_results[0].notability_score == 0.4

        # Query completely outside the range
        out_results = read_notability_signals(
            username=test_user,
            start_date="2025-01-01",
            end_date="2025-12-31",
            client=client,
        )
        assert len(out_results) == 0

    finally:
        clear_notability_signals(username=test_user, client=client)


def test_write_and_read_notability_signals():
    client = get_fulcra_client()
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"

    s1 = NotabilitySignal(
        period_type="week",
        start_date="2026-06-01",
        end_date="2026-06-07",
        username=test_user,
        notability_score=0.75,
        flags=["high_volume"],
        explanation="High activity volume.",
        source_rollup_id="r1",
    )

    s2 = NotabilitySignal(
        period_type="month",
        start_date="2026-05-01",
        end_date="2026-05-31",
        username=test_user,
        notability_score=0.40,
        flags=["new_repo"],
        explanation="First activity in new repo.",
        source_rollup_id="r2",
    )

    try:
        written = write_notability_signals([s1, s2], client=client)
        assert len(written) == 2

        # Read back with eventual consistency polling
        read_records = read_notability_signals(
            username=test_user,
            client=client,
            expected_min_count=2,
            timeout_seconds=20.0,
        )
        assert len(read_records) == 2

        period_types = {r.period_type for r in read_records}
        assert "week" in period_types
        assert "month" in period_types

        # Filter by period_type
        week_signals = read_notability_signals(
            username=test_user,
            period_type="week",
            client=client,
            expected_min_count=1,
            timeout_seconds=10.0,
        )
        assert len(week_signals) == 1
        assert week_signals[0].notability_score == 0.75

    finally:
        clear_notability_signals(username=test_user, client=client)


def test_compute_baseline_stats():
    r1 = ActivityRollup(
        period_type="week",
        start_date="2026-01-01",
        end_date="2026-01-07",
        username="user1",
        summary="",
        stats={"total_activities": 10, "commit_count": 8, "pr_count": 2},
    )
    r2 = ActivityRollup(
        period_type="week",
        start_date="2026-01-08",
        end_date="2026-01-14",
        username="user1",
        summary="",
        stats={"total_activities": 20, "commit_count": 16, "pr_count": 4},
    )

    baseline = compute_baseline_stats([r1, r2])
    assert baseline["rollup_count"] == 2
    assert baseline["mean_total_activities"] == 15.0
    assert baseline["mean_commit_count"] == 12.0
    assert baseline["mean_pr_count"] == 3.0
    assert baseline["std_total_activities"] > 0.0

    empty_baseline = compute_baseline_stats([])
    assert empty_baseline["rollup_count"] == 0
    assert empty_baseline["mean_total_activities"] == 0.0


def test_generate_notability_signal_high_volume_and_firsts():
    test_user = "test_dev"

    r_hist_1 = ActivityRollup(
        period_type="week",
        start_date="2026-05-01",
        end_date="2026-05-07",
        username=test_user,
        summary="Routine week",
        stats={"total_activities": 10, "commit_count": 8, "repos_touched": ["org/repo-a"]},
        id="roll_1",
    )
    r_hist_2 = ActivityRollup(
        period_type="week",
        start_date="2026-05-08",
        end_date="2026-05-14",
        username=test_user,
        summary="Routine week",
        stats={"total_activities": 12, "commit_count": 10, "repos_touched": ["org/repo-a"]},
        id="roll_2",
    )

    # Target rollup: 35 total activities (>3x baseline) and a new repo "org/repo-new"
    r_target = ActivityRollup(
        period_type="week",
        start_date="2026-05-15",
        end_date="2026-05-21",
        username=test_user,
        summary="Big release week",
        stats={"total_activities": 35, "commit_count": 30, "repos_touched": ["org/repo-new", "org/repo-a"]},
        id="roll_3",
    )

    history = [r_hist_1, r_hist_2, r_target]

    signal = generate_notability_signal(target_rollup=r_target, history_rollups=history)

    assert signal.period_type == "week"
    assert signal.username == test_user
    assert "high_volume" in signal.flags
    assert "new_repo" in signal.flags
    assert signal.notability_score >= 0.60
    assert "High activity volume" in signal.explanation
    assert "org/repo-new" in signal.explanation
    assert signal.source_rollup_id == "roll_3"


def test_generate_notability_signal_focus_switch_and_streak():
    test_user = "test_dev"

    r1 = ActivityRollup(
        period_type="week",
        start_date="2026-04-01",
        end_date="2026-04-07",
        username=test_user,
        summary="",
        stats={"total_activities": 15, "repos_touched": ["org/repo-alpha"]},
        id="r1",
    )
    r2 = ActivityRollup(
        period_type="week",
        start_date="2026-04-08",
        end_date="2026-04-14",
        username=test_user,
        summary="",
        stats={"total_activities": 16, "repos_touched": ["org/repo-alpha"]},
        id="r2",
    )
    # Focus switches to repo-beta and continues high activity streak
    r3 = ActivityRollup(
        period_type="week",
        start_date="2026-04-15",
        end_date="2026-04-21",
        username=test_user,
        summary="",
        stats={"total_activities": 18, "repos_touched": ["org/repo-beta"]},
        id="r3",
    )

    history = [r1, r2, r3]

    signal = generate_notability_signal(target_rollup=r3, history_rollups=history)

    assert "focus_switch" in signal.flags
    assert "streak" in signal.flags
    assert "switched from 'org/repo-alpha' to 'org/repo-beta'" in signal.explanation
    assert "Sustained activity streak" in signal.explanation


def test_generate_notability_signal_low_volume_gap():
    test_user = "test_dev"

    r1 = ActivityRollup(
        period_type="month",
        start_date="2026-01-01",
        end_date="2026-01-31",
        username=test_user,
        summary="",
        stats={"total_activities": 25, "repos_touched": ["org/repo"]},
        id="m1",
    )
    r2 = ActivityRollup(
        period_type="month",
        start_date="2026-02-01",
        end_date="2026-02-28",
        username=test_user,
        summary="",
        stats={"total_activities": 20, "repos_touched": ["org/repo"]},
        id="m2",
    )
    # Month 3 has 0 activity following an active stretch
    r3 = ActivityRollup(
        period_type="month",
        start_date="2026-03-01",
        end_date="2026-03-31",
        username=test_user,
        summary="",
        stats={"total_activities": 0, "repos_touched": []},
        id="m3",
    )

    history = [r1, r2, r3]

    signal = generate_notability_signal(target_rollup=r3, history_rollups=history)

    assert "low_volume_gap" in signal.flags
    assert "Activity gap" in signal.explanation


def test_resumable_notability_signal_generation():
    client = get_fulcra_client()
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"
    task_id = f"test_notability_task_{uuid.uuid4().hex[:8]}"

    # Create 4 rollups
    rollups = [
        ActivityRollup(
            period_type="week",
            start_date=f"2026-01-{i*7+1:02d}",
            end_date=f"2026-01-{i*7+7:02d}",
            username=test_user,
            summary=f"Week {i+1}",
            stats={"total_activities": (i + 1) * 10, "repos_touched": ["org/repo"]},
            id=f"r_{i}",
        )
        for i in range(4)
    ]

    try:
        # First run: simulate interrupt at index 2
        with pytest.raises(SimulatedInterruptError):
            generate_notability_signals(
                username=test_user,
                period_type="week",
                client=client,
                task_id=task_id,
                interrupt_at_index=2,
                rollups=rollups,
            )

        # Second run: resume from checkpoint
        result = generate_notability_signals(
            username=test_user,
            period_type="week",
            client=client,
            task_id=task_id,
            interrupt_at_index=None,
            rollups=rollups,
        )

        assert result["status"] == "completed"
        assert result["resumed_from_index"] == 2
        assert result["completed_items_count"] == 4
        assert result["total_items"] == 4

        # Verify saved signals in Fulcra
        saved = read_notability_signals(
            username=test_user,
            period_type="week",
            client=client,
            expected_min_count=4,
            timeout_seconds=20.0,
        )
        assert len(saved) == 4

    finally:
        clear_checkpoint(task_id, client=client)
        clear_notability_signals(username=test_user, client=client)


def test_real_data_notability_signal_end_to_end():
    """Verify computing NotabilitySignals on real or generated ActivityRollup records in Fulcra."""
    client = get_fulcra_client()
    test_user = f"real_demo_{uuid.uuid4().hex[:6]}"
    task_id = f"real_notability_demo_{uuid.uuid4().hex[:8]}"

    # Write a set of rollups with varied activity levels to test real persistence & scoring
    r1 = ActivityRollup(
        period_type="week",
        start_date="2026-05-04",
        end_date="2026-05-10",
        username=test_user,
        summary="Baseline week 1",
        stats={"total_activities": 5, "commit_count": 4, "repos_touched": ["org/core-api"]},
        id="rec_w1",
    )
    r2 = ActivityRollup(
        period_type="week",
        start_date="2026-05-11",
        end_date="2026-05-17",
        username=test_user,
        summary="Baseline week 2",
        stats={"total_activities": 6, "commit_count": 5, "repos_touched": ["org/core-api"]},
        id="rec_w2",
    )
    # Peak activity week with new repository
    r3 = ActivityRollup(
        period_type="week",
        start_date="2026-05-18",
        end_date="2026-05-24",
        username=test_user,
        summary="Peak activity week launching new UI module",
        stats={"total_activities": 28, "commit_count": 22, "pr_count": 4, "repos_touched": ["org/ui-frontend", "org/core-api"]},
        id="rec_w3",
    )

    try:
        write_rollups([r1, r2, r3], client=client)

        result = generate_notability_signals(
            username=test_user,
            period_type="week",
            client=client,
            task_id=task_id,
            rollups=[r1, r2, r3],
        )

        assert result["status"] == "completed"
        assert result["completed_items_count"] == 3

        # Read back saved NotabilitySignals from Fulcra
        signals = read_notability_signals(
            username=test_user,
            period_type="week",
            client=client,
            expected_min_count=3,
            timeout_seconds=15.0,
        )
        assert len(signals) == 3

        # Find the signal for the peak week (2026-05-18)
        peak_signal = next(s for s in signals if s.start_date == "2026-05-18")
        assert peak_signal.notability_score >= 0.60
        assert "high_volume" in peak_signal.flags
        assert "new_repo" in peak_signal.flags
        assert "High activity volume" in peak_signal.explanation
        assert "org/ui-frontend" in peak_signal.explanation

    finally:
        clear_checkpoint(task_id, client=client)
        clear_rollups(username=test_user, client=client)
        clear_notability_signals(username=test_user, client=client)


def test_real_account_notability_signal_uses_real_rollups():
    """Compute notability signals against schr3b3r's ACTUAL stored week
    rollups from Milestones 4-5 (not synthetic data under a throwaway
    username) -- the same "verify against real, already-ingested data"
    bar Milestones 4 and 5 held themselves to. Confirms the baseline is
    computed from real history and at least one real signal's explanation
    is grounded in real stats, not just that some records got written."""
    client = get_fulcra_client()
    username = "schr3b3r"

    existing_week_rollups = read_rollups(
        username=username, period_type="week", client=client
    )
    if len(existing_week_rollups) < 3:
        pytest.skip(
            "Fewer than 3 real week rollups available for schr3b3r -- "
            "not enough history to establish a meaningful baseline. "
            "Run Milestone 4's generate_day_week_rollups against a wider "
            "real window first."
        )

    task_id = f"real_notability_account_demo_{uuid.uuid4().hex[:8]}"

    try:
        result = generate_notability_signals(
            username=username,
            period_type="week",
            client=client,
            task_id=task_id,
            rollups=existing_week_rollups,
        )

        assert result["status"] == "completed"
        assert result["completed_items_count"] == len(existing_week_rollups)

        signals = read_notability_signals(
            username=username,
            period_type="week",
            client=client,
            expected_min_count=len(existing_week_rollups),
            timeout_seconds=20.0,
        )
        assert len(signals) == len(existing_week_rollups)

        assert any(s.baseline_stats.get("mean_total_activities", 0) > 0 for s in signals)

        rollup_by_period = {
            (r.start_date, r.end_date): r for r in existing_week_rollups
        }
        busiest_period = max(
            rollup_by_period,
            key=lambda k: rollup_by_period[k].stats.get("total_activities", 0),
        )
        busiest_signal = next(
            s for s in signals if (s.start_date, s.end_date) == busiest_period
        )
        max_score = max(s.notability_score for s in signals)
        assert busiest_signal.notability_score == max_score
        assert len(busiest_signal.explanation) > 0

    finally:
        clear_checkpoint(task_id, client=client)
        clear_notability_signals(username=username, period_type="week", client=client)
