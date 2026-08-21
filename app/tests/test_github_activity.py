"""Tests for raw GitHub activity model, persistence, and checkpointed ingestion."""

import os
import subprocess
import uuid
import pytest

from checkpoint import SimulatedInterruptError, clear_checkpoint
from fulcra_client import get_fulcra_client
from github_activity import (
    GitHubActivityRaw,
    clear_raw_activities,
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
            timeout_seconds=15.0,
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
