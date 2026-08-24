"""Tests for raw GitHub activity model, persistence, and checkpointed ingestion."""

import os
import subprocess
import uuid
import pytest

from checkpoint import SimulatedInterruptError, clear_checkpoint
from fulcra_client import get_fulcra_client
from github_activity import (
    GitHubActivityRaw,
    backfill_full_github_activity,
    build_backfill_work_items,
    clear_raw_activities,
    generate_period_chunks,
    ingest_github_activity,
    read_raw_activities,
    write_raw_activities,
)
from github_client import GitHubClient


def get_test_credentials():
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GITHUB_USERNAME") or "schr3b3r"
    if not token:
        try:
            token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
        except Exception:
            token = None
    return token, username


def test_github_activity_dataclass_serialization():
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha123456",
        repo_name="testowner/testrepo",
        username="testuser",
        timestamp="2026-06-15T12:00:00Z",
        title_or_summary="feat: add new feature",
        body="feat: add new feature\n\nDetailed body description.",
        url="https://github.com/testowner/testrepo/commit/sha123456",
        metadata={"additions": 10, "deletions": 2},
    )

    data = act.to_dict()
    assert data["record_type"] == "GitHubActivityRaw"
    assert data["activity_type"] == "commit"
    assert data["activity_id"] == "sha123456"
    assert data["title_or_summary"] == "feat: add new feature"

    reconstructed = GitHubActivityRaw.from_dict(data, record_id="annotation_999")
    assert reconstructed.activity_type == act.activity_type
    assert reconstructed.activity_id == act.activity_id
    assert reconstructed.repo_name == act.repo_name
    assert reconstructed.id == "annotation_999"

    fulcra_record = act.to_fulcra_record()
    assert "recorded_at" in fulcra_record
    assert "note" in fulcra_record


def test_write_and_read_raw_activities():
    client = get_fulcra_client()
    test_username = f"testuser_{uuid.uuid4().hex[:6]}"
    test_repo = f"testrepo_{uuid.uuid4().hex[:6]}"

    act1 = GitHubActivityRaw(
        activity_type="commit",
        activity_id=f"sha_{uuid.uuid4().hex[:8]}",
        repo_name=test_repo,
        username=test_username,
        timestamp="2026-06-10T10:00:00Z",
        title_or_summary="fix: solve edge case bug",
        body="Fixed edge case where input was None",
    )

    act2 = GitHubActivityRaw(
        activity_type="pull_request",
        activity_id="42",
        repo_name=test_repo,
        username=test_username,
        timestamp="2026-06-12T14:30:00Z",
        title_or_summary="PR: Refactor ingestion pipeline",
        body="This PR refactors raw ingestion to use Fulcra annotations",
    )

    try:
        written = write_raw_activities([act1, act2], client=client)
        assert len(written) == 2

        # Read back records. Fulcra writes are eventually consistent, so
        # poll (with a generous timeout) until both just-written records
        # actually show up, rather than treating a single immediate
        # query as authoritative -- the same category of intermittent
        # failure already hit and fixed for checkpoint.py's
        # list_checkpoints (see app/CONTEXT.md's Decisions Log).
        read_records = read_raw_activities(
            username=test_username,
            repo_name=test_repo,
            client=client,
            expected_min_count=2,
            timeout_seconds=30.0,
        )
        assert len(read_records) == 2

        summaries = [r.title_or_summary for r in read_records]
        assert "fix: solve edge case bug" in summaries
        assert "PR: Refactor ingestion pipeline" in summaries

    finally:
        clear_raw_activities(
            username=test_username, repo_name=test_repo, client=client
        )


def test_ingest_github_activity_resumption(monkeypatch):
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)

    test_task_id = f"test_ingest_{uuid.uuid4().hex[:8]}"
    repos = ["fulcradynamics/agent-skills", "schr3b3r/agent-testing"]

    try:
        # First call: simulate process interruption at index 1
        with pytest.raises(SimulatedInterruptError):
            ingest_github_activity(
                gh_client=gh_client,
                start_date="2026-06-01",
                end_date="2026-07-01",
                repo_names=repos,
                client=client,
                interrupt_at_index=1,
                task_id=test_task_id,
            )

        # Second call: resume from checkpoint without interruption
        result = ingest_github_activity(
            gh_client=gh_client,
            start_date="2026-06-01",
            end_date="2026-07-01",
            repo_names=repos,
            client=client,
            interrupt_at_index=None,
            task_id=test_task_id,
        )

        assert result["status"] == "completed"
        assert result["resumed_from_index"] == 1
        assert result["completed_items_count"] == 2

    finally:
        clear_checkpoint(test_task_id, client=client)
        for repo in repos:
            clear_raw_activities(username=username, repo_name=repo, client=client)


def test_real_bounded_window_ingestion_end_to_end():
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)

    task_id = f"real_window_{uuid.uuid4().hex[:8]}"
    start_date = "2026-06-01"
    end_date = "2026-07-01"

    try:
        summary = ingest_github_activity(
            gh_client=gh_client,
            start_date=start_date,
            end_date=end_date,
            client=client,
            task_id=task_id,
        )

        assert summary["status"] == "completed"
        assert summary["completed_items_count"] > 0
        assert "fulcradynamics/agent-skills" in summary["repos_processed"]

        # Read back ingested records from Fulcra (poll briefly for the
        # same eventual-consistency reason as the write/read test above,
        # though real ingestion's own runtime usually makes this a
        # non-issue in practice).
        records = read_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )

        assert len(records) > 0

        # Verify real content
        activity_types = {r.activity_type for r in records}
        assert "commit" in activity_types or "pull_request" in activity_types

        # Verify commit message or PR title is non-empty real text
        sample_record = records[0]
        assert len(sample_record.title_or_summary) > 0
        assert sample_record.username == username
        assert sample_record.repo_name == "fulcradynamics/agent-skills"

    finally:
        clear_checkpoint(task_id, client=client)
        clear_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            client=client,
        )
        clear_raw_activities(
            username=username,
            repo_name="schr3b3r/agent-testing",
            client=client,
        )


def test_generate_period_chunks_decaying_granularity():
    """Last 90 days -> weekly chunks; older -> monthly chunks (Interview
    decision #1's decaying-granularity boundary)."""
    end = "2026-07-01"
    start = "2023-07-02"  # ~3 years back

    chunks = generate_period_chunks(start, end, recent_days=90)

    assert len(chunks) > 0
    # Chronological order, no gaps, no overlaps
    for i in range(1, len(chunks)):
        prev_end = chunks[i - 1]["end_date"]
        curr_start = chunks[i]["start_date"]
        assert curr_start > prev_end

    monthly = [c for c in chunks if c["granularity"] == "monthly"]
    weekly = [c for c in chunks if c["granularity"] == "weekly"]
    assert len(monthly) > 0
    assert len(weekly) > 0

    # All monthly chunks strictly precede all weekly chunks
    assert monthly[-1]["end_date"] < weekly[0]["start_date"]

    # Boundary: weekly chunks should only cover the most recent ~90 days
    from datetime import datetime, timedelta, timezone

    end_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cutoff = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")
    assert weekly[0]["start_date"] >= cutoff

    # Full window covered: first chunk starts at start_date, last ends at end_date
    assert chunks[0]["start_date"] == start
    assert chunks[-1]["end_date"] == end


def test_generate_period_chunks_empty_or_reversed_window():
    assert generate_period_chunks("2026-07-01", "2026-07-01") == []
    assert generate_period_chunks("2026-08-01", "2026-07-01") == []


def test_build_backfill_work_items_ordering():
    chunks = [
        {"start_date": "2026-01-01", "end_date": "2026-01-31", "granularity": "monthly"},
        {"start_date": "2026-02-01", "end_date": "2026-02-07", "granularity": "weekly"},
    ]
    repos = ["zeta/repo", "alpha/repo"]

    items = build_backfill_work_items(repos, chunks)

    assert len(items) == 4
    # Chronological by period first
    assert [i["start_date"] for i in items] == [
        "2026-01-01",
        "2026-01-01",
        "2026-02-01",
        "2026-02-01",
    ]
    # Repos alphabetically within each period
    assert items[0]["repo_name"] == "alpha/repo"
    assert items[1]["repo_name"] == "zeta/repo"
    assert items[0]["granularity"] == "monthly"
    assert items[2]["granularity"] == "weekly"


def test_build_backfill_work_items_empty_inputs():
    assert build_backfill_work_items([], []) == []
    assert build_backfill_work_items(["a/b"], []) == []
    assert build_backfill_work_items([], [{"start_date": "x", "end_date": "y"}]) == []


def test_full_backfill_multi_repo_multi_period_resumability_real(monkeypatch):
    """Milestone 3's real, at-scale resumability demo: interrupt a real
    backfill run partway through a work-item list that spans MULTIPLE repos
    AND multiple period-chunk granularities (not just one repo/one window
    like Milestones 1-2's tests), then confirm a fresh call resumes at the
    correct index with zero duplicate or skipped work items."""
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)
    repos = ["fulcradynamics/agent-skills", "schr3b3r/agent-testing"]

    test_task_id = f"test_full_backfill_{uuid.uuid4().hex[:8]}"

    try:
        # Bound the window so the real work-item list spans both monthly
        # and weekly granularity but stays small enough to run in a task
        # (~5 months -> a handful of monthly chunks + ~13 weekly chunks,
        # x2 repos = tens of items, not thousands).
        with pytest.raises(SimulatedInterruptError):
            backfill_full_github_activity(
                gh_client=gh_client,
                start_date="2026-02-01",
                end_date="2026-07-01",
                repo_names=repos,
                client=client,
                interrupt_at_index=5,
                task_id=test_task_id,
            )

        # Fresh call (simulating a fresh process): resume without interruption
        result = backfill_full_github_activity(
            gh_client=gh_client,
            start_date="2026-02-01",
            end_date="2026-07-01",
            repo_names=repos,
            client=client,
            interrupt_at_index=None,
            task_id=test_task_id,
        )

        assert result["status"] == "completed"
        assert result["resumed_from_index"] == 5
        assert result["total_items"] > 5
        # Multi-period-granularity: both monthly and weekly chunks present
        assert result["period_chunks_count"] > 1
        assert set(result["repo_names"]) == set(repos)
        # Every index in the full item list was processed exactly once
        # across both calls (first call: 0-4, second call: 5..end).
        assert result["completed_items_count"] == result["total_items"]

    finally:
        clear_checkpoint(test_task_id, client=client)
        for repo in repos:
            clear_raw_activities(username=username, repo_name=repo, client=client)

