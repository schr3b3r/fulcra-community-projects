"""Tests for custom Fulcra data types management and backward compatibility."""

from datetime import datetime, timedelta, timezone
import json
import time
from unittest.mock import MagicMock
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

        # 30s (not the more typical 15s used elsewhere in this file) --
        # this specific test has been observed flaking with a real
        # eventual-consistency delay exceeding 15s on Fulcra's backend
        # (confirmed passing cleanly on isolated retry every time this was
        # investigated; see app/CONTEXT.md's Decisions Log). read_checkpoint
        # already has real polling infrastructure -- this just gives it a
        # wider window before giving up, rather than treating a real but
        # slow eventual-consistency delay as a hard test failure.
        read_cp = read_checkpoint(
            task_id=task_id, client=client, use_cache=False, timeout_seconds=30.0
        )
        assert read_cp is not None
        assert read_cp.task_id == task_id
        assert read_cp.completed_items_count == 5
    finally:
        clear_checkpoint(task_id, client=client)


def test_get_or_create_tag_uuids_resolves_via_mocked_client():
    """Verify get_or_create_tag_uuids resolves distinct tag names to UUIDs
    via a single create_tags batch call, and caches results across calls."""
    fulcra_types.clear_tag_cache()

    mock_client = MagicMock()
    mock_client.create_tags.return_value = [
        {"name": "commit", "id": "11111111-1111-1111-1111-111111111111"},
        {"name": "pull_request", "id": "22222222-2222-2222-2222-222222222222"},
    ]

    result = fulcra_types.get_or_create_tag_uuids(
        ["commit", "pull_request"], client=mock_client
    )

    assert result == {
        "commit": "11111111-1111-1111-1111-111111111111",
        "pull_request": "22222222-2222-2222-2222-222222222222",
    }
    # Exactly one batch call for the two distinct names -- not one per tag.
    mock_client.create_tags.assert_called_once()
    called_names = mock_client.create_tags.call_args[0][0]
    assert set(called_names) == {"commit", "pull_request"}


def test_get_or_create_tag_uuids_dedupes_and_caches_across_calls():
    """Verify repeated/duplicate tag names within one call, and a second
    call reusing a name already resolved, do not trigger redundant
    create_tags calls -- this is the "resolve once per run, not once
    per record" cost-control property the resolver exists to provide."""
    fulcra_types.clear_tag_cache()

    mock_client = MagicMock()
    mock_client.create_tags.return_value = [
        {"name": "week", "id": "33333333-3333-3333-3333-333333333333"},
    ]

    # Duplicate "week" three times in one call -- should still be a single
    # create_tags call for the one distinct name.
    result1 = fulcra_types.get_or_create_tag_uuids(
        ["week", "week", "week"], client=mock_client
    )
    assert result1 == {"week": "33333333-3333-3333-3333-333333333333"}
    assert mock_client.create_tags.call_count == 1

    # A second, independent call for the same tag name should hit the
    # cache and NOT call create_tags again.
    result2 = fulcra_types.get_or_create_tag_uuids(["week"], client=mock_client)
    assert result2 == {"week": "33333333-3333-3333-3333-333333333333"}
    assert mock_client.create_tags.call_count == 1


def test_get_or_create_tag_uuids_empty_input_returns_empty_and_skips_api_call():
    """An empty tag name list should short-circuit without touching the client."""
    fulcra_types.clear_tag_cache()
    mock_client = MagicMock()

    result = fulcra_types.get_or_create_tag_uuids([], client=mock_client)

    assert result == {}
    mock_client.create_tags.assert_not_called()


def test_get_or_create_tag_uuids_real_batch_resolution():
    """Real live test: create_tags against the real Fulcra account resolves
    real tag UUIDs, and a repeat call for the same names returns the same
    UUIDs (idempotent, per the SDK's own documented behavior)."""
    fulcra_types.clear_tag_cache()
    client = get_fulcra_client()
    unique_suffix = str(int(time.time()))
    tag_names = [f"test_tag_a_{unique_suffix}", f"test_tag_b_{unique_suffix}"]

    result1 = fulcra_types.get_or_create_tag_uuids(tag_names, client=client)
    assert set(result1.keys()) == set(tag_names)
    assert all(len(v) > 0 for v in result1.values())

    # Real idempotency: re-resolving the same names returns identical UUIDs.
    fulcra_types.clear_tag_cache()
    result2 = fulcra_types.get_or_create_tag_uuids(tag_names, client=client)
    assert result2 == result1


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
            timeout_seconds=30.0,
        )
        assert len(recs) >= 1
        assert recs[0].username == username
        assert recs[0].stats.get("total_activities") == 12
    finally:
        clear_rollups(username=username, client=client)


def test_old_format_checkpoints_are_not_read_after_duration_annotation_migration():
    """Verify read_checkpoint does NOT merge in old-format (pre-Milestone-17)
    MomentAnnotation-shaped GitHubBackfillProgress records anymore.

    This is a deliberate, discussed design decision (see Milestone 17's
    Decisions Log entry): checkpoints are ephemeral process state, not
    durable historical data worth a dual-read/migration path across the
    MomentAnnotation -> DurationAnnotation type change. An old-format
    record for the same task_id must NOT be returned even if a real one
    exists in the account -- read_checkpoint only reads DurationAnnotation
    checkpoints now.
    """
    client = get_fulcra_client()
    now_iso = datetime.now(timezone.utc).isoformat()
    task_id = f"test_old_format_abandoned_{int(time.time())}"

    try:
        # Write an old-format (pre-migration) MomentAnnotation checkpoint
        # directly -- this is exactly the shape every real
        # GitHubBackfillProgress record had before Milestone 17.
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

        # No new-format (DurationAnnotation) checkpoint written for this
        # task_id -- read_checkpoint must find nothing, NOT fall back to
        # the old-format MomentAnnotation record above.
        read_cp = read_checkpoint(
            task_id=task_id, client=client, use_cache=False, timeout_seconds=5.0
        )
        assert read_cp is None

    finally:
        # The old-format record above was written directly as a plain
        # MomentAnnotation, outside this project's own tombstone-by-
        # record_type helpers (which now only look at DurationAnnotation)
        # -- clean it up directly rather than leaving stray test data.
        try:
            from checkpoint import _fetch_annotations_merged

            now = datetime.now(timezone.utc)
            anns = client.moment_annotations(
                (now - timedelta(days=1)).isoformat(), now.isoformat()
            )
            tombstones = []
            for ann in anns:
                note_str = ann.get("note")
                if not note_str:
                    continue
                try:
                    d = json.loads(note_str)
                except Exception:
                    continue
                if d.get("task_id") == task_id:
                    ann_id = ann.get("id")
                    if ann_id:
                        tombstones.append(
                            {"record_id": ann_id, "data_type": "MomentAnnotation"}
                        )
            if tombstones:
                client.record_data_type(
                    "DeletedRecord", tombstones, api_version="v1alpha1"
                )
        except Exception:
            pass
