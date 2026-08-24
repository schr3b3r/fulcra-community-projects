"""Tests for ActivityRollup model, persistence, generation, and resumability."""

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
    generate_period_rollup,
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
            timeout_seconds=15.0,
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
            timeout_seconds=15.0,
        )
        assert len(saved) == 4

    finally:
        clear_checkpoint(task_id, client=client)
        clear_rollups(username=test_user, client=client)


def test_real_data_rollup_generation_end_to_end():
    """Generate day and week rollups for real GitHubActivityRaw records stored in Fulcra,
    verifying LLM narrative summary and provenance on real data."""
    client = get_fulcra_client()
    username = "schr3b3r"
    task_id = f"real_rollup_demo_{uuid.uuid4().hex[:8]}"

    # Query existing raw records for schr3b3r in Fulcra
    raw_records = read_raw_activities(username=username, client=client)
    if not raw_records:
        pytest.skip("No existing GitHubActivityRaw records in Fulcra for real data demo.")

    # Pick whichever real day in the raw data has the most activity, rather
    # than a hardcoded date -- real ingestion windows shift across milestone
    # runs (raw records get cleaned up between tasks), so a fixed date would
    # silently start skipping this assertion once that day's data is gone.
    from collections import Counter

    day_counts = Counter(r.timestamp[:10] for r in raw_records if r.timestamp)
    if not day_counts:
        pytest.skip("No dated GitHubActivityRaw records available for real data demo.")
    start_date = end_date = day_counts.most_common(1)[0][0]

    try:
        summary_result = generate_day_week_rollups(
            username=username,
            start_date=start_date,
            end_date=end_date,
            granularities=["day", "week"],
            client=client,
            task_id=task_id,
            raw_records=raw_records,
        )

        assert summary_result["status"] == "completed"
        assert summary_result["completed_items_count"] == 2  # 1 day chunk + 1 week chunk

        # Read back saved rollups from Fulcra
        rollups = read_rollups(
            username=username,
            start_date=start_date,
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )
        assert len(rollups) >= 1

        day_rollup = next((r for r in rollups if r.period_type == "day"), rollups[0])
        assert day_rollup.username == username
        assert day_rollup.stats["total_activities"] > 0
        assert len(day_rollup.stats["repos_touched"]) > 0

        # Confirm provenance chain has non-empty record IDs
        assert len(day_rollup.source_record_ids) > 0

        # Confirm summary text is real, non-empty, and reflects real activity
        assert len(day_rollup.summary) > 50
        # Check that at least one real repo name touched that day appears
        # in the generated narrative (case-insensitive) -- a real signal
        # that the summary is grounded in actual content, not boilerplate.
        repo_short_names = [
            repo.split("/")[-1].lower() for repo in day_rollup.stats["repos_touched"]
        ]
        assert any(name in day_rollup.summary.lower() for name in repo_short_names)

    finally:
        clear_checkpoint(task_id, client=client)
        clear_rollups(username=username, client=client)
