"""Tests for the optional Maha metadata-only provenance layer."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from provenance import (
    ProvenanceConsent,
    ProvenanceError,
    build_musical_idea_provenance,
    build_share_boundary_record,
    verify_musical_idea_provenance,
    verify_share_boundary_record,
    write_metadata_record,
)


RECORDED_AT = datetime(2026, 8, 26, 4, 30, tzinfo=timezone.utc)


def _audio_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    session = tmp_path / "session.wav"
    marker = tmp_path / "marker.wav"
    clip = tmp_path / "idea.wav"
    session.write_bytes(b"private full session audio bytes")
    marker.write_bytes(b"private marker audio bytes")
    clip.write_bytes(b"selected derived idea bytes")
    return session, marker, clip


def _record(tmp_path: Path, scope: str = "private") -> dict:
    session, marker, clip = _audio_files(tmp_path)
    return build_musical_idea_provenance(
        consent=ProvenanceConsent(
            consent_reference="consent-test-0001",
            opted_in=True,
            sharing_scope=scope,  # type: ignore[arg-type]
        ),
        recorded_at=RECORDED_AT,
        session_id="session-private-0001",
        session_audio_path=session,
        marker_audio_path=marker,
        clip_audio_path=clip,
        musical_idea_reference="fulcra:MusicalIdea:test-0001",
        processing_version="flow-state-v2-test@abc123",
        marker_detector="MFCCCorrelationDetector",
        marker_timestamp_seconds=38.6,
        window_start_seconds=23.6,
        window_duration_seconds=15.0,
        key_estimate="C# Major",
        bpm_estimate=99,
    )


def test_opt_in_is_required_before_audio_is_hashed(tmp_path: Path) -> None:
    with pytest.raises(ProvenanceError, match="explicit opt-in"):
        build_musical_idea_provenance(
            consent=ProvenanceConsent("consent-test", opted_in=False),
            recorded_at=RECORDED_AT,
            session_id="session-private-0001",
            session_audio_path=tmp_path / "missing-session.wav",
            marker_audio_path=tmp_path / "missing-marker.wav",
            clip_audio_path=tmp_path / "missing-clip.wav",
            musical_idea_reference="fulcra:MusicalIdea:test-0001",
            processing_version="test@abc123",
            marker_detector="MFCCCorrelationDetector",
            marker_timestamp_seconds=38.6,
            window_start_seconds=23.6,
            window_duration_seconds=15.0,
            key_estimate="C# Major",
            bpm_estimate=99,
        )


def test_record_is_deterministic_metadata_only_and_hides_paths(tmp_path: Path) -> None:
    first = _record(tmp_path)
    second = _record(tmp_path)
    assert first == second
    assert verify_musical_idea_provenance(first)
    serialized = str(first)
    assert "private full session audio bytes" not in serialized
    assert "session.wav" not in serialized
    assert "marker.wav" not in serialized
    assert "idea.wav" not in serialized
    assert "session-private-0001" not in serialized
    assert "consent-test-0001" not in serialized
    assert first["boundaries"]["raw_audio_retained_by_maha"] is False
    assert first["boundaries"]["fulcra_storage_or_access_policy_modified"] is False


def test_any_metadata_change_invalidates_the_record_digest(tmp_path: Path) -> None:
    record = _record(tmp_path)
    tampered = deepcopy(record)
    tampered["output"]["bpm_estimate"] = 100
    assert verify_musical_idea_provenance(tampered) is False


def test_private_consent_cannot_produce_a_share_record(tmp_path: Path) -> None:
    with pytest.raises(ProvenanceError, match="Private consent"):
        build_share_boundary_record(
            _record(tmp_path), audience_reference="collaboration-test"
        )


def test_share_record_discloses_only_the_selected_derived_idea(tmp_path: Path) -> None:
    provenance = _record(tmp_path, scope="selected_collaborators")
    shared = build_share_boundary_record(
        provenance, audience_reference="gregory-flow-state-test"
    )
    serialized = str(shared)
    assert provenance["source"]["session_audio_sha256"] not in serialized
    assert provenance["source"]["marker_audio_sha256"] not in serialized
    assert provenance["output"]["clip_audio_sha256"] in serialized
    assert "gregory-flow-state-test" not in serialized
    assert verify_share_boundary_record(shared)
    assert shared["boundaries"] == {
        "full_session_digest_disclosed": False,
        "marker_digest_disclosed": False,
        "audio_content_included": False,
        "creative_ownership_attested": False,
        "cryptographic_signature_present": False,
    }


def test_writer_accepts_json_only_and_writes_atomically(tmp_path: Path) -> None:
    record = _record(tmp_path)
    destination = write_metadata_record(record, tmp_path / "evidence" / "record.json")
    assert destination.is_file()
    assert not destination.with_suffix(".json.tmp").exists()
    with pytest.raises(ProvenanceError, match="must end in .json"):
        write_metadata_record(record, tmp_path / "evidence.wav")
    invalid = deepcopy(record)
    invalid["output"]["key_estimate"] = "tampered"
    with pytest.raises(ProvenanceError, match="invalid metadata"):
        write_metadata_record(invalid, tmp_path / "invalid.json")
