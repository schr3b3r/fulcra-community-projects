"""Tests for Fulcra progress checkpointing and resumable execution."""

import uuid
from typing import List
import pytest

from fulcra_client import get_fulcra_client
from checkpoint import (
    GitHubBackfillProgress,
    SimulatedInterruptError,
    clear_checkpoint,
    list_checkpoints,
    process_with_checkpoint,
    read_checkpoint,
    write_checkpoint,
)


def generate_test_task_id() -> str:
    """Generate a unique task ID for isolated test runs."""
    return f"test_task_{uuid.uuid4().hex[:8]}"


class TestGitHubBackfillProgressDataClass:
    def test_serialization_and_deserialization(self) -> None:
        progress = GitHubBackfillProgress(
            task_id="task-123",
            stage="raw_ingestion",
            repo_name="owner/repo",
            start_date="2023-01-01",
            end_date="2023-02-01",
            last_processed_item="item_47",
            last_processed_index=46,
            completed_items_count=47,
            total_items=100,
            status="in_progress",
            metadata={"batch_size": 10},
        )

        d = progress.to_dict()
        assert d["record_type"] == "GitHubBackfillProgress"
        assert d["task_id"] == "task-123"
        assert d["last_processed_index"] == 46
        assert d["completed_items_count"] == 47

        reconstructed = GitHubBackfillProgress.from_dict(d, record_id="rec-456")
        assert reconstructed.task_id == progress.task_id
        assert reconstructed.stage == progress.stage
        assert reconstructed.repo_name == progress.repo_name
        assert reconstructed.last_processed_index == 46
        assert reconstructed.completed_items_count == 47
        assert reconstructed.id == "rec-456"
        assert reconstructed.metadata == {"batch_size": 10}

    def test_fulcra_record_format(self) -> None:
        progress = GitHubBackfillProgress(task_id="task-999")
        rec = progress.to_fulcra_record()
        assert "recorded_at" in rec
        assert "note" in rec
        assert "GitHubBackfillProgress" in rec["note"]


class TestFulcraCheckpointIntegration:
    @pytest.fixture(autouse=True)
    def setup_client(self) -> None:
        self.client = get_fulcra_client()

    def test_write_and_read_checkpoint(self) -> None:
        task_id = generate_test_task_id()
        try:
            progress = GitHubBackfillProgress(
                task_id=task_id,
                stage="testing",
                repo_name="org/repo-a",
                last_processed_item="item_20",
                last_processed_index=19,
                completed_items_count=20,
                total_items=50,
                status="in_progress",
            )

            write_checkpoint(progress, client=self.client)

            read_back = read_checkpoint(task_id, client=self.client)
            assert read_back is not None
            assert read_back.task_id == task_id
            assert read_back.stage == "testing"
            assert read_back.repo_name == "org/repo-a"
            assert read_back.last_processed_index == 19
            assert read_back.completed_items_count == 20
            assert read_back.status == "in_progress"
        finally:
            clear_checkpoint(task_id, client=self.client)

    def test_resumability_isolated_kill_and_restart(self) -> None:
        """Core Milestone 1 requirement:
        - Process items 1 through 100.
        - Interrupt/kill process at item 47 (processed 47 items: indices 0..46).
        - Restart from fresh process session.
        - Confirm resumes at item 48 (index 47) and completes without duplicate or skipped items.
        """
        task_id = generate_test_task_id()
        items = [f"item_{i}" for i in range(1, 101)]  # items 1 to 100
        processed_log_run_1: List[str] = []

        def worker_fn_run_1(item: str, idx: int) -> None:
            processed_log_run_1.append(item)

        try:
            # RUN 1: Start process, interrupt at index 47 (when about to process 48th item, after 47 items completed)
            with pytest.raises(SimulatedInterruptError):
                process_with_checkpoint(
                    task_id=task_id,
                    items=items,
                    process_fn=worker_fn_run_1,
                    client=self.client,
                    interrupt_at_index=47,  # 0-based index 47 is item 48
                )

            # Confirm run 1 processed exactly 47 items (items 1 through 47, indices 0..46)
            assert len(processed_log_run_1) == 47
            assert processed_log_run_1[0] == "item_1"
            assert processed_log_run_1[-1] == "item_47"

            # Checkpoint stored in Fulcra after run 1
            checkpoint = read_checkpoint(task_id, client=self.client)
            assert checkpoint is not None
            assert checkpoint.last_processed_index == 46
            assert checkpoint.completed_items_count == 47
            assert checkpoint.status == "in_progress"

            # RUN 2: Fresh process session, resumption from Fulcra state
            processed_log_run_2: List[str] = []

            def worker_fn_run_2(item: str, idx: int) -> None:
                processed_log_run_2.append(item)

            summary = process_with_checkpoint(
                task_id=task_id,
                items=items,
                process_fn=worker_fn_run_2,
                client=self.client,
            )

            # Confirm run 2 resumed at index 47 (item 48) and processed remaining 53 items
            assert summary["status"] == "completed"
            assert summary["resumed_from_index"] == 47
            assert len(processed_log_run_2) == 53
            assert processed_log_run_2[0] == "item_48"
            assert processed_log_run_2[-1] == "item_100"

            # Combine log from both runs: exact match to complete 1..100 sequence with zero duplicates or gaps
            total_processed = processed_log_run_1 + processed_log_run_2
            assert len(total_processed) == 100
            assert total_processed == items

            # Final checkpoint in Fulcra reflects full completion
            final_checkpoint = read_checkpoint(task_id, client=self.client)
            assert final_checkpoint is not None
            assert final_checkpoint.status == "completed"
            assert final_checkpoint.last_processed_index == 99
            assert final_checkpoint.completed_items_count == 100

        finally:
            clear_checkpoint(task_id, client=self.client)

    def test_list_checkpoints(self) -> None:
        task_1 = generate_test_task_id()
        task_2 = generate_test_task_id()
        try:
            write_checkpoint(
                GitHubBackfillProgress(task_id=task_1, last_processed_index=10),
                client=self.client,
            )
            write_checkpoint(
                GitHubBackfillProgress(task_id=task_2, last_processed_index=20),
                client=self.client,
            )

            # Fulcra writes are eventually consistent -- poll (with a
            # generous timeout) until both just-written checkpoints
            # actually show up, rather than treating a single immediate
            # query as authoritative.
            checkpoints = list_checkpoints(
                client=self.client,
                expected_task_ids=[task_1, task_2],
                timeout_seconds=15.0,
            )
            assert task_1 in checkpoints
            assert task_2 in checkpoints
            assert checkpoints[task_1].last_processed_index == 10
            assert checkpoints[task_2].last_processed_index == 20
        finally:
            clear_checkpoint(task_1, client=self.client)
            clear_checkpoint(task_2, client=self.client)
