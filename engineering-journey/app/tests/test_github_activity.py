"""Tests for raw GitHub activity model, persistence, and checkpointed ingestion."""

import json
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
    compute_deterministic_activity_id,
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
    assert fulcra_record["recorded_at"] == "2026-06-15T12:00:00Z"
    assert "id" in fulcra_record
    assert fulcra_record["id"] == compute_deterministic_activity_id(
        act.activity_type, act.activity_id, act.repo_name
    )
    assert "note" in fulcra_record


def test_github_activity_recorded_at_reflects_historical_timestamp():
    """Verify recorded_at reflects real GitHub event timestamp, not ingestion updated_at time."""
    historical_ts = "2024-03-15T10:20:30Z"
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_hist_123",
        repo_name="org/historical-repo",
        username="histuser",
        timestamp=historical_ts,
        title_or_summary="feat: historical commit in 2024",
    )

    fulcra_rec = act.to_fulcra_record()
    # recorded_at must be the historical event timestamp
    assert fulcra_rec["recorded_at"] == historical_ts
    assert fulcra_rec["recorded_at"] != act.updated_at

    # updated_at must remain in the JSON note payload
    note_payload = json.loads(fulcra_rec["note"])
    assert note_payload["updated_at"] == act.updated_at
    assert note_payload["timestamp"] == historical_ts

    # id field must be deterministic activity ID
    expected_id = compute_deterministic_activity_id(
        "commit", "sha_hist_123", "org/historical-repo"
    )
    assert fulcra_rec["id"] == expected_id


def test_deterministic_activity_id_helper():
    """Verify compute_deterministic_activity_id produces deterministic, distinct UUIDs."""
    id1 = compute_deterministic_activity_id("commit", "sha123", "owner/repo")
    id2 = compute_deterministic_activity_id("commit", "sha123", "owner/repo")
    assert id1 == id2
    assert len(id1) == 36  # Standard UUID string length

    id3 = compute_deterministic_activity_id("pull_request", "123", "owner/repo")
    assert id1 != id3

    id4 = compute_deterministic_activity_id("commit", "sha123", "owner/other-repo")
    assert id1 != id4


def test_github_activity_to_fulcra_record_includes_tag_ids():
    """Verify to_fulcra_record attaches a tags array when tag_ids is passed."""
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_tag_test",
        repo_name="owner/repo",
        username="testuser",
        timestamp="2026-01-01T00:00:00Z",
        title_or_summary="test commit",
    )

    tag_ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]
    rec = act.to_fulcra_record(tag_ids=tag_ids)

    assert rec["tags"] == tag_ids


def test_github_activity_to_fulcra_record_no_tags_when_omitted():
    """Verify to_fulcra_record does not add a tags key when tag_ids is not passed."""
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_no_tag_test",
        repo_name="owner/repo",
        username="testuser",
        timestamp="2026-01-01T00:00:00Z",
        title_or_summary="test commit",
    )

    rec = act.to_fulcra_record()

    assert "tags" not in rec


def test_github_activity_to_fulcra_record_source_chain_includes_repo_lineage():
    """Verify to_fulcra_record's sources chain includes real repo-level lineage
    (com.github -> com.github.repo.<repo> -> the custom-type identity tag last),
    not just the bare custom-type identity tag."""
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_source_test",
        repo_name="owner/my-repo",
        username="testuser",
        timestamp="2026-01-01T00:00:00Z",
        title_or_summary="test commit",
    )

    identity_tag = "com.fulcradynamics.annotation.some-uuid"
    rec = act.to_fulcra_record(source_tag=identity_tag)

    assert rec["sources"] == [
        "com.github",
        "com.github.repo.owner.my-repo",
        identity_tag,
    ]
    # The custom-type identity tag must remain the LAST element -- this is
    # what _fetch_annotations_merged's source= filtering depends on.
    assert rec["sources"][-1] == identity_tag


def test_github_activity_to_fulcra_record_explicit_sources_override():
    """Verify an explicitly-passed sources list takes precedence over the
    auto-derived repo-lineage chain."""
    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id="sha_override_test",
        repo_name="owner/repo",
        username="testuser",
        timestamp="2026-01-01T00:00:00Z",
        title_or_summary="test commit",
    )

    custom_sources = ["custom.source.a", "custom.source.b"]
    rec = act.to_fulcra_record(source_tag="ignored-tag", sources=custom_sources)

    assert rec["sources"] == custom_sources


def test_historical_recorded_at_time_range_query_real():
    """Real live API test: write a record with historical timestamp and prove it is discoverable
    via a time-range query for that historical period, but excluded from non-overlapping periods."""
    client = get_fulcra_client()
    test_username = f"hist_test_{uuid.uuid4().hex[:6]}"
    test_repo = f"hist_repo_{uuid.uuid4().hex[:6]}"
    historical_ts = "2024-03-15T10:00:00Z"

    act = GitHubActivityRaw(
        activity_type="commit",
        activity_id=f"sha_{uuid.uuid4().hex[:8]}",
        repo_name=test_repo,
        username=test_username,
        timestamp=historical_ts,
        title_or_summary="feat: historical work from March 2024",
    )

    try:
        written = write_raw_activities([act], client=client)
        assert len(written) == 1

        # Query matching the historical March 2024 window
        matching = read_raw_activities(
            username=test_username,
            repo_name=test_repo,
            start_time="2024-03-01T00:00:00Z",
            end_time="2024-03-31T23:59:59Z",
            client=client,
            expected_min_count=1,
            timeout_seconds=20.0,
        )
        assert len(matching) == 1
        assert matching[0].timestamp == historical_ts

        # Query for non-overlapping window (2025)
        non_matching = read_raw_activities(
            username=test_username,
            repo_name=test_repo,
            start_time="2025-01-01T00:00:00Z",
            end_time="2025-01-31T23:59:59Z",
            client=client,
        )
        assert len(non_matching) == 0

    finally:
        clear_raw_activities(
            username=test_username,
            repo_name=test_repo,
            start_time="2024-01-01T00:00:00Z",
            end_time="2026-12-31T23:59:59Z",
            client=client,
        )


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

        # Read back records with eventual consistency polling
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

        records = read_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )

        assert len(records) > 0

        activity_types = {r.activity_type for r in records}
        assert "commit" in activity_types or "pull_request" in activity_types

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
    end = "2026-07-01"
    start = "2023-07-02"

    chunks = generate_period_chunks(start, end, recent_days=90)

    assert len(chunks) > 0
    for i in range(1, len(chunks)):
        prev_end = chunks[i - 1]["end_date"]
        curr_start = chunks[i]["start_date"]
        assert curr_start > prev_end

    monthly = [c for c in chunks if c["granularity"] == "monthly"]
    weekly = [c for c in chunks if c["granularity"] == "weekly"]
    assert len(monthly) > 0
    assert len(weekly) > 0

    assert monthly[-1]["end_date"] < weekly[0]["start_date"]

    from datetime import datetime, timedelta, timezone

    end_dt = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cutoff = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")
    assert weekly[0]["start_date"] >= cutoff

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
    assert [i["start_date"] for i in items] == [
        "2026-01-01",
        "2026-01-01",
        "2026-02-01",
        "2026-02-01",
    ]
    assert items[0]["repo_name"] == "alpha/repo"
    assert items[1]["repo_name"] == "zeta/repo"
    assert items[0]["granularity"] == "monthly"
    assert items[2]["granularity"] == "weekly"


def test_build_backfill_work_items_empty_inputs():
    assert build_backfill_work_items([], []) == []
    assert build_backfill_work_items(["a/b"], []) == []
    assert build_backfill_work_items([], [{"start_date": "x", "end_date": "y"}]) == []


def test_full_backfill_multi_repo_multi_period_resumability_real(monkeypatch):
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)
    repos = ["fulcradynamics/agent-skills", "schr3b3r/agent-testing"]

    test_task_id = f"test_full_backfill_{uuid.uuid4().hex[:8]}"

    try:
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
        assert result["period_chunks_count"] > 1
        assert set(result["repo_names"]) == set(repos)
        assert result["completed_items_count"] == result["total_items"]

    finally:
        clear_checkpoint(test_task_id, client=client)
        for repo in repos:
            clear_raw_activities(username=username, repo_name=repo, client=client)


def test_backfill_delta_awareness_real():
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)

    test_task_id = f"test_delta_{uuid.uuid4().hex[:8]}"
    narrow_repos = ["fulcradynamics/agent-skills"]
    expanded_repos = ["fulcradynamics/agent-skills", "schr3b3r/shimmer"]
    start_date = "2026-06-01"
    end_date = "2026-06-15"
    query_start = "2026-05-31"
    query_end = "2026-06-16"

    delta_task_id = None
    try:
        res1 = backfill_full_github_activity(
            gh_client=gh_client,
            start_date=start_date,
            end_date=end_date,
            repo_names=narrow_repos,
            client=client,
            task_id=test_task_id,
        )
        assert res1["status"] == "completed"
        assert res1["is_delta"] is False

        records_before = read_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            start_time=query_start,
            end_time=query_end,
            client=client,
        )
        count_before = len(records_before)

        res2 = backfill_full_github_activity(
            gh_client=gh_client,
            start_date=start_date,
            end_date=end_date,
            repo_names=expanded_repos,
            client=client,
            task_id=test_task_id,
        )
        assert res2["status"] == "completed"
        assert res2["is_delta"] is True
        assert res2["new_repos"] == ["schr3b3r/shimmer"]
        delta_task_id = res2.get("delta_task_id")

        records_after = read_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            start_time=query_start,
            end_time=query_end,
            client=client,
        )
        count_after = len(records_after)

        assert count_after == count_before

    finally:
        clear_checkpoint(test_task_id, client=client)
        if delta_task_id:
            clear_checkpoint(delta_task_id, client=client)
        clear_raw_activities(
            username=username,
            repo_name="schr3b3r/shimmer",
            start_time=query_start,
            end_time=query_end,
            client=client,
        )


def test_backfill_full_github_activity_skips_zero_activity_repos(monkeypatch):
    client = get_fulcra_client()
    gh_client = GitHubClient(token="dummy_token", username="dummy_user")

    monkeypatch.setattr(
        gh_client,
        "enumerate_repositories",
        lambda start, end: ["dummy/active1", "dummy/inactive", "dummy/active2"],
    )

    def mock_has_author_activity(repo, start, end):
        return repo != "dummy/inactive"

    monkeypatch.setattr(gh_client, "has_author_activity", mock_has_author_activity)
    monkeypatch.setattr(gh_client, "fetch_commits", lambda repo, start, end: [])
    monkeypatch.setattr(gh_client, "fetch_pull_requests", lambda repo, start, end: [])
    monkeypatch.setattr(gh_client, "fetch_issues", lambda repo, start, end: [])

    test_task_id = f"test_skip_inactive_{uuid.uuid4().hex[:8]}"

    try:
        summary = backfill_full_github_activity(
            gh_client=gh_client,
            start_date="2026-06-01",
            end_date="2026-07-01",
            client=client,
            task_id=test_task_id,
        )

        assert summary["status"] == "completed"
        assert summary["repos_skipped_no_activity"] == ["dummy/inactive"]
        assert summary["active_repo_names"] == ["dummy/active1", "dummy/active2"]
        assert summary["total_items"] == 2 * summary["period_chunks_count"]

    finally:
        clear_checkpoint(test_task_id, client=client)


def test_backfill_full_github_activity_skips_no_activity_repo_real():
    token, username = get_test_credentials()
    if not token:
        pytest.skip("No GitHub token available for live API test.")

    client = get_fulcra_client()
    gh_client = GitHubClient(token=token, username=username)

    test_task_id = f"test_skip_real_{uuid.uuid4().hex[:8]}"

    repos = ["fulcradynamics/agent-skills", "octocat/Hello-World"]
    start_date = "2026-06-01"
    end_date = "2026-07-01"

    try:
        summary = backfill_full_github_activity(
            gh_client=gh_client,
            start_date=start_date,
            end_date=end_date,
            repo_names=repos,
            client=client,
            task_id=test_task_id,
        )

        assert summary["status"] == "completed"
        assert "octocat/Hello-World" in summary["repos_skipped_no_activity"]
        assert "fulcradynamics/agent-skills" in summary["active_repo_names"]
        assert "octocat/Hello-World" not in summary["active_repo_names"]

    finally:
        clear_checkpoint(test_task_id, client=client)
        clear_raw_activities(
            username=username,
            repo_name="fulcradynamics/agent-skills",
            client=client,
        )
