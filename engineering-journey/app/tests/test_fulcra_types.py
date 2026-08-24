"""Tests for custom Fulcra data types management and backward compatibility."""

from datetime import datetime, timezone
import json
import time
import pytest

from fulcra_client import get_fulcra_client
import fulcra_types
from checkpoint import (
    GitHubBackfillProgress,
    write_checkpoint,
    read_checkpoint,
    clear_checkpoint,
)
from rollup import (
    ActivityRollup,
    write_rollup,
    read_rollups,
    clear_rollups,
)


def test_custom_data_types_idempotent_creation():
    """Verify that custom data types are created idempotently and cached."""
    client = get_fulcra_client()
    fulcra_types.clear_custom_data_type_cache()

    uuid1 = fulcra_types.get_or_create_custom_data_type("GitHubBackfillProgress", client=client)
    assert uuid1 is not None and len(uuid1) > 0

    # Second call should return identical cached UUID
    uuid2 = fulcra_types.get_or_create_custom_data_type("GitHubBackfillProgress", client=client)
    assert uuid2 == uuid1

    tag = fulcra_types.get_custom_source_tag("GitHubBackfillProgress", client=client)
    assert tag == f"com.fulcradynamics.annotation.{uuid1}"


def test_all_four_custom_types_exist_in_catalog():
    """Verify all four custom data types exist and are visible in Fulcra catalog."""
    client = get_fulcra_client()
    user_id = client.get_fulcra_userid()
    catalog = client.v1_catalog(fulcra_userid=user_id)

    catalog_names = {item.get("name") for item in catalog if item.get("name")}

    for name in fulcra_types.RECORD_TYPE_DEFINITIONS:
        assert name in catalog_names, f"Custom data type {name} not found in catalog"


def test_checkpoint_custom_type_write_and_read():
    """Test write and read of GitHubBackfillProgress through custom data type source tags."""
    client = get_fulcra_client()
    task_id = f"test_custom_type_cp_{int(time.time())}"

    try:
        cp = GitHubBackfillProgress(
            task_id=task_id,
            stage="test_stage",
            completed_items_count=5,
            total_items=10,
            status="in_progress",
        )
        write_checkpoint(cp, client=client)

        read_cp = read_checkpoint(
            task_id=task_id, client=client, use_cache=False, timeout_seconds=15.0
        )
        assert read_cp is not None
        assert read_cp.task_id == task_id
        assert read_cp.completed_items_count == 5
    finally:
        clear_checkpoint(task_id, client=client)


def test_rollup_custom_type_write_and_read():
    """Test write and read of ActivityRollup through custom data type source tags."""
    client = get_fulcra_client()
    username = f"test_user_{int(time.time())}"

    try:
        rollup = ActivityRollup(
            period_type="week",
            start_date="2026-08-01",
            end_date="2026-08-07",
            username=username,
            summary="Test summary with custom data type source tag",
            stats={"total_activities": 12, "commit_count": 8},
        )
        write_rollup(rollup, client=client)

        recs = read_rollups(
            username=username,
            period_type="week",
            client=client,
            expected_min_count=1,
            timeout_seconds=15.0,
        )
        assert len(recs) >= 1
        assert recs[0].username == username
        assert recs[0].stats.get("total_activities") == 12
    finally:
        clear_rollups(username=username, client=client)


def test_backward_compatibility_old_and_new_records():
    """Verify read_checkpoint retrieves both legacy untagged records and new source-tagged records."""
    client = get_fulcra_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    task_id = f"test_backward_compat_{int(time.time())}"

    try:
        # Write legacy untagged record (no sources field) directly
        old_note = {
            "record_type": "GitHubBackfillProgress",
            "task_id": task_id,
            "stage": "legacy_stage",
            "last_processed_index": 1,
            "completed_items_count": 2,
            "total_items": 10,
            "status": "in_progress",
            "updated_at": now_iso,
        }
        client.record_data_type(
            "MomentAnnotation",
            [{"recorded_at": now_iso, "note": json.dumps(old_note)}],
            api_version="v1alpha1",
        )

        # Write new source-tagged record
        cp_new = GitHubBackfillProgress(
            task_id=task_id,
            stage="new_stage",
            last_processed_index=2,
            completed_items_count=3,
            total_items=10,
            status="in_progress",
        )
        write_checkpoint(cp_new, client=client)

        time.sleep(2.0)

        # Read back checkpoint - should select the latest checkpoint (index 2) without failing or orphaning
        read_cp = read_checkpoint(
            task_id=task_id, client=client, use_cache=False, timeout_seconds=15.0
        )
        assert read_cp is not None
        assert read_cp.last_processed_index == 2
        assert read_cp.stage == "new_stage"

    finally:
        clear_checkpoint(task_id, client=client)
