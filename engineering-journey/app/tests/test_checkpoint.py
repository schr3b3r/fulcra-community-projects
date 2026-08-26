"""Tests for Fulcra progress checkpointing and resumable execution."""

from datetime import datetime, timezone
import json
import uuid
from typing import List
import pytest

from fulcra_client import get_fulcra_client
from checkpoint import (
    CATALOG_TYPE_NAME,
    GitHubBackfillProgress,
    SimulatedInterruptError,
    _fetch_annotations_merged,
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

    def test_fulcra_record_format_duration_shape(self) -> None:
        progress = GitHubBackfillProgress(
            task_id="task-999",
            start_date="2024-03-01",
            end_date="2024-03-07",
        )
        rec = progress.to_fulcra_record()
        assert "recorded_at" in rec
        assert isinstance(rec["recorded_at"], dict)
        assert rec["recorded_at"]["start_time"] == "2024-03-01T00:00:00Z"
        # end_time uses end-of-day (23:59:59Z), not the same 00:00:00Z as
        # start_time -- confirmed empirically that Fulcra's backend
        # silently drops a DurationAnnotation whose start_time == end_time
        # exactly (a genuine zero-length duration): the write succeeds,
        # but the record is never returned by any later read. A single-
        # day period (start_date == end_date, as here effectively -- a
        # 7-day span ending on 2024-03-07) must still have a real,
        # non-zero duration.
        assert rec["recorded_at"]["end_time"] == "2024-03-07T23:59:59Z"
        assert "note" in rec
        assert "GitHubBackfillProgress" in rec["note"]

        # When dates are missing, recorded_at falls back to updated_at ISO strings
        progress_no_dates = GitHubBackfillProgress(task_id="task-999")
        rec_no_dates = progress_no_dates.to_fulcra_record()
        assert isinstance(rec_no_dates["recorded_at"], dict)
        assert "start_time" in rec_no_dates["recorded_at"]
        assert "end_time" in rec_no_dates["recorded_at"]


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

            read_back = read_checkpoint(task_id, client=self.client, timeout_seconds=30.0)
            assert read_back is not None
            assert read_back.task_id == task_id
            assert read_back.stage == "testing"
            assert read_back.repo_name == "org/repo-a"
            assert read_back.last_processed_index == 19
            assert read_back.completed_items_count == 20
            assert read_back.status == "in_progress"
        finally:
            clear_checkpoint(task_id, client=self.client)

    def test_duration_annotation_checkpoint_time_range_query_real(self) -> None:
        """Verify a checkpoint written with known start_date/end_date is written as a DurationAnnotation
        and queryable via duration_annotations scoped to that historical window."""
        task_id = generate_test_task_id()
        start_date = "2024-03-01"
        end_date = "2024-03-07"

        try:
            progress = GitHubBackfillProgress(
                task_id=task_id,
                stage="testing",
                start_date=start_date,
                end_date=end_date,
                completed_items_count=1,
                total_items=5,
                status="in_progress",
            )
            write_checkpoint(progress, client=self.client)

            read_back = read_checkpoint(
                task_id,
                client=self.client,
                use_cache=False,
                start_time="2024-03-01T00:00:00Z",
                end_time="2024-03-08T00:00:00Z",
                timeout_seconds=30.0,
            )
            assert read_back is not None
            assert read_back.task_id == task_id
            assert read_back.start_date == start_date
            assert read_back.end_date == end_date
        finally:
            clear_checkpoint(task_id, client=self.client)

    def test_checkpoint_with_single_day_or_no_date_range_is_still_readable_real(self) -> None:
        """Regression test for a real bug found while verifying this migration: a
        DurationAnnotation whose start_time and end_time are EXACTLY equal (a
        genuine zero-length duration) is silently dropped by Fulcra's backend --
        the write call reports success, but the record is never returned by any
        later read, filtered or not. This would have silently broken every
        checkpoint with no item-level date range (the fallback-to-updated_at
        case) and every single-day period chunk (start_date == end_date),
        without ever raising an error anywhere. Confirmed fixed by using
        end-of-day for the end_time bound (see _format_iso_timestamp's
        end_of_day parameter and to_fulcra_record's no-date fallback, which
        adds a real 1-second offset instead of repeating the same instant)."""
        # Case 1: no start_date/end_date at all (the fallback path).
        task_id_nodate = generate_test_task_id()
        try:
            progress = GitHubBackfillProgress(
                task_id=task_id_nodate,
                stage="testing",
                completed_items_count=1,
                total_items=5,
                status="in_progress",
            )
            write_checkpoint(progress, client=self.client)
            read_back = read_checkpoint(
                task_id_nodate, client=self.client, use_cache=False, timeout_seconds=15.0
            )
            assert read_back is not None
            assert read_back.task_id == task_id_nodate
        finally:
            clear_checkpoint(task_id_nodate, client=self.client)

        # Case 2: start_date == end_date (a genuine single-day period).
        task_id_singleday = generate_test_task_id()
        try:
            progress = GitHubBackfillProgress(
                task_id=task_id_singleday,
                stage="testing",
                start_date="2024-05-15",
                end_date="2024-05-15",
                completed_items_count=1,
                total_items=5,
                status="in_progress",
            )
            write_checkpoint(progress, client=self.client)
            read_back = read_checkpoint(
                task_id_singleday,
                client=self.client,
                use_cache=False,
                start_time="2024-05-14T00:00:00Z",
                end_time="2024-05-16T00:00:00Z",
                timeout_seconds=15.0,
            )
            assert read_back is not None
            assert read_back.task_id == task_id_singleday
            assert read_back.start_date == "2024-05-15"
            assert read_back.end_date == "2024-05-15"
        finally:
            clear_checkpoint(task_id_singleday, client=self.client)

    def test_process_with_checkpoint_derives_item_date_range(self) -> None:
        """Verify process_with_checkpoint populates progress.start_date and progress.end_date
        from work item dicts during processing."""
        task_id = generate_test_task_id()
        items = [
            {"repo_name": "org/repo1", "start_date": "2024-01-01", "end_date": "2024-01-07"},
            {"repo_name": "org/repo1", "start_date": "2024-01-08", "end_date": "2024-01-15"},
        ]

        observed_dates = []

        def progress_cb(event: dict) -> None:
            if event.get("kind") == "item_completed":
                cp = read_checkpoint(task_id, client=self.client, use_cache=True)
                if cp:
                    observed_dates.append((cp.start_date, cp.end_date))

        try:
            process_with_checkpoint(
                task_id=task_id,
                items=items,
                process_fn=lambda item, idx: None,
                client=self.client,
                progress_callback=progress_cb,
            )

            assert len(observed_dates) == 2
            assert observed_dates[0] == ("2024-01-01", "2024-01-07")
            assert observed_dates[1] == ("2024-01-08", "2024-01-15")
        finally:
            clear_checkpoint(task_id, client=self.client)

    def test_fetch_annotations_merged_does_not_overfetch_unrelated_types(self) -> None:
        """Verify _fetch_annotations_merged with base_type='DurationAnnotation' returns only
        DurationAnnotation checkpoints and does not overfetch MomentAnnotation records."""
        now_iso = datetime.now(timezone.utc).isoformat()
        start_iso = "2020-01-01T00:00:00Z"

        cp_records = _fetch_annotations_merged(
            client=self.client,
            record_type_name="GitHubBackfillProgress",
            start_iso=start_iso,
            end_iso=now_iso,
            base_type="DurationAnnotation",
            catalog_type_name=CATALOG_TYPE_NAME,
        )

        for rec in cp_records:
            note_str = rec.get("note")
            if note_str:
                data = json.loads(note_str)
                assert data.get("record_type") == "GitHubBackfillProgress"

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
                timeout_seconds=30.0,
            )
            assert task_1 in checkpoints
            assert task_2 in checkpoints
            assert checkpoints[task_1].last_processed_index == 10
            assert checkpoints[task_2].last_processed_index == 20
        finally:
            clear_checkpoint(task_1, client=self.client)
            clear_checkpoint(task_2, client=self.client)
