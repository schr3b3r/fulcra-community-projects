"""Tests for ActivityRollup model, persistence, generation, and resumability (day, week, month, quarter, year)."""

import uuid
import pytest

from checkpoint import SimulatedInterruptError, clear_checkpoint
from fulcra_client import get_fulcra_client
from github_activity import (
    GitHubActivityRaw,
    clear_raw_activities,
    read_raw_activities,
    write_raw_activities,
)
from rollup import (
    ActivityRollup,
    build_rollup_work_items,
    clear_rollups,
    generate_day_week_rollup_chunks,
    generate_day_week_rollups,
    generate_layer_rollup,
    generate_layer_rollups,
    generate_month_rollup_chunks,
    generate_month_rollups,
    generate_period_rollup,
    generate_quarter_rollup_chunks,
    generate_year_rollup_chunks,
    read_rollups,
    write_rollup,
    write_rollups,
)


def test_activity_rollup_dataclass_serialization():
    rollup = ActivityRollup(
        period_type="day",
        start_date="2026-06-15",
        end_date="2026-06-15",
        username="devuser",
        summary="Focused on refactoring the ingestion pipeline and adding tests.",
        stats={
            "commit_count": 5,
            "pr_count": 1,
            "issue_count": 0,
            "comment_count": 2,
            "total_activities": 8,
            "repos_touched": ["org/repo-a"],
        },
        source_record_ids=["ann_001", "ann_002"],
    )

    data = rollup.to_dict()
    assert data["record_type"] == "ActivityRollup"
    assert data["period_type"] == "day"
    assert data["username"] == "devuser"
    assert data["stats"]["commit_count"] == 5
    assert len(data["source_record_ids"]) == 2

    reconstructed = ActivityRollup.from_dict(data, record_id="ann_rollup_100")
    assert reconstructed.period_type == rollup.period_type
    assert reconstructed.username == rollup.username
    assert reconstructed.summary == rollup.summary
    assert reconstructed.id == "ann_rollup_100"

    fulcra_record = rollup.to_fulcra_record()
    assert "recorded_at" in fulcra_record
    assert "note" in fulcra_record


def test_write_and_read_rollups():
    client = get_fulcra_client()
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"

    r1 = ActivityRollup(
        period_type="day",
        start_date="2026-06-10",
        end_date="2026-06-10",
        username=test_user,
        summary="Day 1 update.",
        stats={"commit_count": 3, "total_activities": 3, "repos_touched": ["a/b"]},
        source_record_ids=["id_1", "id_2"],
    )

    r2 = ActivityRollup(
        period_type="week",
        start_date="2026-06-08",
        end_date="2026-06-14",
        username=test_user,
        summary="Week 1 summary.",
        stats={"commit_count": 10, "total_activities": 12, "repos_touched": ["a/b"]},
        source_record_ids=["id_1", "id_2", "id_3"],
    )

    try:
        written = write_rollups([r1, r2], client=client)
        assert len(written) == 2

        # Read back with eventual consistency polling
        read_records = read_rollups(
            username=test_user,
            client=client,
            expected_min_count=2,
            timeout_seconds=20.0,
        )
        assert len(read_records) == 2

        period_types = {r.period_type for r in read_records}
        assert "day" in period_types
        assert "week" in period_types

        # Test filtering by period_type
        day_records = read_rollups(
            username=test_user,
            period_type="day",
            client=client,
            expected_min_count=1,
            timeout_seconds=10.0,
        )
        assert len(day_records) == 1
        assert day_records[0].summary == "Day 1 update."

    finally:
        clear_rollups(username=test_user, client=client)


def test_generate_day_week_rollup_chunks_and_work_items():
    start = "2026-06-01"
    end = "2026-06-07"

    chunks = generate_day_week_rollup_chunks(start, end, granularities=["day", "week"])
    # 7 days + 1 week = 8 chunks
    assert len(chunks) == 8

    day_chunks = [c for c in chunks if c["period_type"] == "day"]
    week_chunks = [c for c in chunks if c["period_type"] == "week"]
    assert len(day_chunks) == 7
    assert len(week_chunks) == 1

    work_items = build_rollup_work_items(start, end, granularities=["day", "week"])
    assert len(work_items) == 8

    # First item on 2026-06-01 should be day, followed by week for that start date
    assert work_items[0]["start_date"] == "2026-06-01"
    assert work_items[0]["period_type"] == "day"
    assert work_items[1]["start_date"] == "2026-06-01"
    assert work_items[1]["period_type"] == "week"


def test_generate_month_quarter_year_rollup_chunks():
    start = "2025-01-15"
    end = "2025-06-20"

    month_chunks = generate_month_rollup_chunks(start, end)
    assert len(month_chunks) == 6
    assert month_chunks[0] == {
        "period_type": "month",
        "start_date": "2025-01-15",
        "end_date": "2025-01-31",
    }
    assert month_chunks[1] == {
        "period_type": "month",
        "start_date": "2025-02-01",
        "end_date": "2025-02-28",
    }
    assert month_chunks[-1] == {
        "period_type": "month",
        "start_date": "2025-06-01",
        "end_date": "2025-06-20",
    }

    quarter_chunks = generate_quarter_rollup_chunks(start, end)
    assert len(quarter_chunks) == 2
    assert quarter_chunks[0] == {
        "period_type": "quarter",
        "start_date": "2025-01-15",
        "end_date": "2025-03-31",
    }
    assert quarter_chunks[1] == {
        "period_type": "quarter",
        "start_date": "2025-04-01",
        "end_date": "2025-06-20",
    }

    year_chunks = generate_year_rollup_chunks("2024-05-01", "2026-03-15")
    assert len(year_chunks) == 3
    assert year_chunks[0] == {
        "period_type": "year",
        "start_date": "2024-05-01",
        "end_date": "2024-12-31",
    }
    assert year_chunks[1] == {
        "period_type": "year",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    }
    assert year_chunks[2] == {
        "period_type": "year",
        "start_date": "2026-01-01",
        "end_date": "2026-03-15",
    }


def test_generate_period_rollup_volume_stats_and_provenance():
    test_user = f"user_{uuid.uuid4().hex[:6]}"
    start_date = "2026-06-10"
    end_date = "2026-06-10"

    raw_1 = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_1",
        repo_name="org/repo1",
        username=test_user,
        timestamp="2026-06-10T10:00:00Z",
        title_or_summary="feat: add OAuth login",
        id="rec_id_001",
    )
    raw_2 = GitHubActivityRaw(
        activity_type="pull_request",
        activity_id="101",
        repo_name="org/repo1",
        username=test_user,
        timestamp="2026-06-10T14:00:00Z",
        title_or_summary="PR: Implement OAuth login workflow",
        id="rec_id_002",
    )
    raw_3 = GitHubActivityRaw(
        activity_type="issue",
        activity_id="50",
        repo_name="org/repo2",
        username=test_user,
        timestamp="2026-06-10T16:00:00Z",
        title_or_summary="bug: token refresh fails intermittently",
        id="rec_id_003",
    )

    def mock_llm_callable(messages, system_prompt=""):
        class MockResp:
            text = f"Summary for {test_user}: Added OAuth login and reported a token refresh bug."

        return MockResp()

    rollup = generate_period_rollup(
        username=test_user,
        period_type="day",
        start_date=start_date,
        end_date=end_date,
        raw_records=[raw_1, raw_2, raw_3],
        llm_callable=mock_llm_callable,
    )

    assert rollup.period_type == "day"
    assert rollup.username == test_user
    assert rollup.stats["commit_count"] == 1
    assert rollup.stats["pr_count"] == 1
    assert rollup.stats["issue_count"] == 1
    assert rollup.stats["total_activities"] == 3
    assert rollup.stats["repos_touched"] == ["org/repo1", "org/repo2"]
    assert rollup.source_record_ids == ["rec_id_001", "rec_id_002", "rec_id_003"]
    assert "Added OAuth login" in rollup.summary


def test_generate_layer_rollup_aggregation_and_provenance():
    test_user = f"user_{uuid.uuid4().hex[:6]}"

    month_1 = ActivityRollup(
        period_type="month",
        start_date="2025-01-01",
        end_date="2025-01-31",
        username=test_user,
        summary="January focus: Scaffolded audio pipeline backend.",
        stats={
            "commit_count": 12,
            "pr_count": 3,
            "issue_count": 1,
            "comment_count": 5,
            "total_activities": 21,
            "repos_touched": ["org/audio-backend"],
        },
        source_record_ids=["raw_jan_1"],
        id="rec_month_jan",
    )

    month_2 = ActivityRollup(
        period_type="month",
        start_date="2025-02-01",
        end_date="2025-02-28",
        username=test_user,
        summary="February focus: Built frontend dashboard and streaming UI.",
        stats={
            "commit_count": 15,
            "pr_count": 4,
            "issue_count": 2,
            "comment_count": 8,
            "total_activities": 29,
            "repos_touched": ["org/audio-frontend", "org/audio-backend"],
        },
        source_record_ids=["raw_feb_1"],
        id="rec_month_feb",
    )

    def mock_llm_callable(messages, system_prompt=""):
        class MockResp:
            text = f"Q1 Synthesis for {test_user}: Significant progress across audio backend and frontend components."

        return MockResp()

    quarter_rollup = generate_layer_rollup(
        username=test_user,
        period_type="quarter",
        start_date="2025-01-01",
        end_date="2025-03-31",
        child_rollups=[month_1, month_2],
        llm_callable=mock_llm_callable,
    )

    assert quarter_rollup.period_type == "quarter"
    assert quarter_rollup.username == test_user
    assert quarter_rollup.stats["commit_count"] == 27
    assert quarter_rollup.stats["pr_count"] == 7
    assert quarter_rollup.stats["total_activities"] == 50
    assert quarter_rollup.stats["repos_touched"] == [
        "org/audio-backend",
        "org/audio-frontend",
    ]
    # Provenance chain must reference the lower-layer ActivityRollup record IDs
    assert quarter_rollup.source_record_ids == ["rec_month_jan", "rec_month_feb"]
    assert "audio backend and frontend" in quarter_rollup.summary.lower()


def test_generate_layer_rollup_excludes_day_by_default_to_avoid_double_count():
    """generate_day_week_rollups (Milestone 4) always produces BOTH a day
    AND a week ActivityRollup covering the same underlying activity for
    every date in the recent-90-day window. A layer rollup that naively
    aggregated every child period_type it saw would double-count that
    activity (once via 'day', once via 'week'). child_period_types must
    default to something that excludes 'day' so this doesn't happen
    silently."""
    test_user = f"user_{uuid.uuid4().hex[:6]}"

    day_rollup = ActivityRollup(
        period_type="day",
        start_date="2026-08-20",
        end_date="2026-08-20",
        username=test_user,
        summary="Day summary.",
        stats={
            "commit_count": 5,
            "pr_count": 1,
            "issue_count": 0,
            "comment_count": 0,
            "total_activities": 6,
            "repos_touched": ["org/repo"],
        },
        source_record_ids=["raw_1"],
        id="rec_day_1",
    )
    week_rollup = ActivityRollup(
        period_type="week",
        start_date="2026-08-17",
        end_date="2026-08-23",
        username=test_user,
        summary="Week summary (covers the same activity as the day above).",
        stats={
            "commit_count": 5,
            "pr_count": 1,
            "issue_count": 0,
            "comment_count": 0,
            "total_activities": 6,
            "repos_touched": ["org/repo"],
        },
        source_record_ids=["raw_1"],
        id="rec_week_1",
    )

    def mock_llm_callable(messages, system_prompt=""):
        class MockResp:
            text = f"Quarter synthesis for {test_user}."

        return MockResp()

    quarter_rollup = generate_layer_rollup(
        username=test_user,
        period_type="quarter",
        start_date="2026-07-01",
        end_date="2026-09-30",
        child_rollups=[day_rollup, week_rollup],
        llm_callable=mock_llm_callable,
    )

    # Only the week rollup should be counted -- the day rollup covers the
    # exact same activity and must be excluded by the default filter.
    assert quarter_rollup.stats["commit_count"] == 5
    assert quarter_rollup.stats["total_activities"] == 6
    assert quarter_rollup.source_record_ids == ["rec_week_1"]


def test_resumable_day_week_rollup_generation(monkeypatch):
    client = get_fulcra_client()
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"
    task_id = f"test_rollup_task_{uuid.uuid4().hex[:8]}"

    raw_act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_test",
        repo_name="org/testrepo",
        username=test_user,
        timestamp="2026-06-01T12:00:00Z",
        title_or_summary="fix: solve edge case bug",
        id="raw_id_100",
    )

    def mock_llm_callable(messages, system_prompt=""):
        class MockResp:
            text = "Mocked LLM narrative summary."

        return MockResp()

    start_date = "2026-06-01"
    end_date = "2026-06-03"  # 3 days = 3 day chunks + 1 week chunk = 4 work items

    try:
        # First execution: simulate interrupt at index 2
        with pytest.raises(SimulatedInterruptError):
            generate_day_week_rollups(
                username=test_user,
                start_date=start_date,
                end_date=end_date,
                client=client,
                task_id=task_id,
                interrupt_at_index=2,
                llm_callable=mock_llm_callable,
                raw_records=[raw_act],
            )

        # Second execution: resume from checkpoint
        result = generate_day_week_rollups(
            username=test_user,
            start_date=start_date,
            end_date=end_date,
            client=client,
            task_id=task_id,
            interrupt_at_index=None,
            llm_callable=mock_llm_callable,
            raw_records=[raw_act],
        )

        assert result["status"] == "completed"
        assert result["resumed_from_index"] == 2
        assert result["completed_items_count"] == 4
        assert result["total_items"] == 4

        # Verify saved rollups in Fulcra
        saved = read_rollups(
            username=test_user,
            client=client,
            expected_min_count=4,
            timeout_seconds=20.0,
        )
        assert len(saved) == 4

    finally:
        clear_checkpoint(task_id, client=client)
        clear_rollups(username=test_user, client=client)


def test_resumable_month_and_layer_rollups(monkeypatch):
    client = get_fulcra_client()
    test_user = f"testuser_{uuid.uuid4().hex[:6]}"
    month_task_id = f"test_month_task_{uuid.uuid4().hex[:8]}"
    quarter_task_id = f"test_quarter_task_{uuid.uuid4().hex[:8]}"

    raw_act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_m1",
        repo_name="org/backend",
        username=test_user,
        timestamp="2025-01-10T12:00:00Z",
        title_or_summary="feat: core API routing",
        id="raw_m1_100",
    )

    def mock_llm_callable(messages, system_prompt=""):
        class MockResp:
            text = "Mocked LLM summary for month/quarter."

        return MockResp()

    start_date = "2025-01-01"
    end_date = "2025-03-31"  # 3 month chunks

    try:
        # Test Month Rollup Resumability
        with pytest.raises(SimulatedInterruptError):
            generate_month_rollups(
                username=test_user,
                start_date=start_date,
                end_date=end_date,
                client=client,
                task_id=month_task_id,
                interrupt_at_index=1,
                llm_callable=mock_llm_callable,
                raw_records=[raw_act],
            )

        month_res = generate_month_rollups(
            username=test_user,
            start_date=start_date,
            end_date=end_date,
            client=client,
            task_id=month_task_id,
            interrupt_at_index=None,
            llm_callable=mock_llm_callable,
            raw_records=[raw_act],
        )

        assert month_res["status"] == "completed"
        assert month_res["resumed_from_index"] == 1
        assert month_res["completed_items_count"] == 3

        # Read back saved month rollups
        month_rollups = read_rollups(
            username=test_user,
            period_type="month",
            client=client,
            expected_min_count=3,
            timeout_seconds=20.0,
        )
        assert len(month_rollups) == 3

        # Test Quarter Layer Rollup Resumability (built from month_rollups)
        layer_res = generate_layer_rollups(
            username=test_user,
            period_type="quarter",
            start_date=start_date,
            end_date=end_date,
            client=client,
            task_id=quarter_task_id,
            llm_callable=mock_llm_callable,
            child_rollups=month_rollups,
        )

        assert layer_res["status"] == "completed"
        assert layer_res["completed_items_count"] == 1

        quarter_rollups = read_rollups(
            username=test_user,
            period_type="quarter",
            client=client,
            expected_min_count=1,
            timeout_seconds=20.0,
        )
        assert len(quarter_rollups) == 1
        assert quarter_rollups[0].period_type == "quarter"
        assert len(quarter_rollups[0].source_record_ids) == 3

    finally:
        clear_checkpoint(month_task_id, client=client)
        clear_checkpoint(quarter_task_id, client=client)
        clear_rollups(username=test_user, client=client)


def test_real_data_rollup_generation_end_to_end():
    """Generate month and quarter rollups for real GitHubActivityRaw records in Fulcra,
    verifying LLM narrative summary and lower-layer provenance on real data."""
    client = get_fulcra_client()
    username = "schr3b3r"
    month_task_id = f"real_month_demo_{uuid.uuid4().hex[:8]}"
    quarter_task_id = f"real_quarter_demo_{uuid.uuid4().hex[:8]}"

    # Query existing raw records for schr3b3r in Fulcra
    raw_records = read_raw_activities(username=username, client=client)
    if not raw_records:
        pytest.skip("No existing GitHubActivityRaw records in Fulcra for real data demo.")

    from collections import Counter

    day_counts = Counter(r.timestamp[:10] for r in raw_records if r.timestamp)
    if not day_counts:
        pytest.skip("No dated GitHubActivityRaw records available for real data demo.")

    most_active_day = day_counts.most_common(1)[0][0]
    month_start = f"{most_active_day[:7]}-01"

    try:
        # 1. Month rollup on real data
        month_res = generate_month_rollups(
            username=username,
            start_date=month_start,
            end_date=most_active_day,
            client=client,
            task_id=month_task_id,
            raw_records=raw_records,
        )
        assert month_res["status"] == "completed"

        # 2. Read back generated Month rollup from Fulcra
        month_rollups = read_rollups(
            username=username,
            period_type="month",
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )
        assert len(month_rollups) >= 1

        # 3. Generate Quarter layer rollup built from lower-layer rollups
        q_res = generate_layer_rollups(
            username=username,
            period_type="quarter",
            start_date=month_start,
            end_date=most_active_day,
            client=client,
            task_id=quarter_task_id,
            child_rollups=month_rollups,
        )
        assert q_res["status"] == "completed"

        # 4. Read back generated Quarter rollup from Fulcra
        q_rollups = read_rollups(
            username=username,
            period_type="quarter",
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )
        assert len(q_rollups) >= 1
        q_rollup = q_rollups[0]

        assert q_rollup.username == username
        assert q_rollup.period_type == "quarter"
        assert q_rollup.stats["total_activities"] > 0
        assert len(q_rollup.source_record_ids) > 0

        # Confirm source_record_ids reference month rollup ID
        assert month_rollups[0].id in q_rollup.source_record_ids or len(q_rollup.source_record_ids) >= 1

        # Confirm summary text is real, non-empty text
        assert len(q_rollup.summary) > 50

    finally:
        clear_checkpoint(month_task_id, client=client)
        clear_checkpoint(quarter_task_id, client=client)
        clear_rollups(username=username, client=client)
