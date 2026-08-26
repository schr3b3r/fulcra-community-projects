"""Metadata-only provenance records for one opted-in Flow State session.

This module deliberately does not upload, copy, delete, or retain audio. It
reads local files once to compute SHA-256 digests and returns JSON-compatible
metadata. Flow State and Fulcra retain their existing storage responsibilities;
Maha's record describes the transformation without becoming an audio store.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Union

PathLike = Union[str, Path]
SharingScope = Literal["private", "selected_collaborators", "public"]

PROVENANCE_SCHEMA_VERSION = "maha.flow-state-provenance.v1"
SHARE_SCHEMA_VERSION = "maha.flow-state-share-boundary.v1"
PROCESSING_SYSTEM = "flow-state-app-v2"
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    """Raised when consent or transformation metadata is incomplete."""


@dataclass(frozen=True)
class ProvenanceConsent:
    """A narrow consent receipt; it intentionally contains no person data."""

    consent_reference: str
    opted_in: bool
    sharing_scope: SharingScope = "private"
    purpose: str = "metadata_only_transformation_provenance"


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: PathLike) -> str:
    source = Path(path)
    if not source.is_file():
        raise ProvenanceError(f"Evidence input file not found: {source}")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _bounded_text(name: str, value: str, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProvenanceError(f"{name} must be a non-empty string of at most {maximum} characters.")
    return value.strip()


def _non_negative_number(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ProvenanceError(f"{name} must be a finite non-negative number.")
    return float(value)


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProvenanceError("recorded_at must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_musical_idea_provenance(
    *,
    consent: ProvenanceConsent,
    recorded_at: datetime,
    session_id: str,
    session_audio_path: PathLike,
    marker_audio_path: PathLike,
    clip_audio_path: PathLike,
    musical_idea_reference: str,
    processing_version: str,
    marker_detector: str,
    marker_timestamp_seconds: float,
    window_start_seconds: float,
    window_duration_seconds: float,
    key_estimate: str,
    bpm_estimate: int,
) -> dict[str, Any]:
    """Build a deterministic evidence record without embedding audio or paths."""

    if consent.opted_in is not True:
        raise ProvenanceError("Metadata provenance requires explicit opt-in consent.")
    if consent.sharing_scope not in {"private", "selected_collaborators", "public"}:
        raise ProvenanceError("Unsupported sharing_scope.")
    if consent.purpose != "metadata_only_transformation_provenance":
        raise ProvenanceError("Consent purpose does not authorize this record type.")
    consent_reference = _bounded_text("consent_reference", consent.consent_reference)
    session_reference = _sha256_text(_bounded_text("session_id", session_id))
    idea_reference = _bounded_text("musical_idea_reference", musical_idea_reference)
    version = _bounded_text("processing_version", processing_version)
    detector = _bounded_text("marker_detector", marker_detector)
    key = _bounded_text("key_estimate", key_estimate, maximum=80)
    if not isinstance(bpm_estimate, int) or isinstance(bpm_estimate, bool) or not 0 <= bpm_estimate <= 400:
        raise ProvenanceError("bpm_estimate must be an integer between 0 and 400.")

    payload: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "recorded_at": _utc_timestamp(recorded_at),
        "consent": {
            "consent_reference_sha256": _sha256_text(consent_reference),
            "opted_in": True,
            "purpose": consent.purpose,
            "sharing_scope": consent.sharing_scope,
        },
        "source": {
            "session_reference": session_reference,
            "session_audio_sha256": _sha256_file(session_audio_path),
            "marker_audio_sha256": _sha256_file(marker_audio_path),
        },
        "transformation": {
            "processing_system": PROCESSING_SYSTEM,
            "processing_version": version,
            "marker_detector": detector,
            "marker_timestamp_seconds": _non_negative_number(
                "marker_timestamp_seconds", marker_timestamp_seconds
            ),
            "window_start_seconds": _non_negative_number(
                "window_start_seconds", window_start_seconds
            ),
            "window_duration_seconds": _non_negative_number(
                "window_duration_seconds", window_duration_seconds
            ),
            "derived_fields": ["musical_key_estimate", "bpm_estimate"],
        },
        "output": {
            "musical_idea_reference": idea_reference,
            "clip_audio_sha256": _sha256_file(clip_audio_path),
            "key_estimate": key,
            "bpm_estimate": bpm_estimate,
        },
        "boundaries": {
            "audio_content_included": False,
            "audio_path_included": False,
            "raw_audio_retained_by_maha": False,
            "fulcra_storage_or_access_policy_modified": False,
            "fulcra_enforcement_attested": False,
            "creative_ownership_attested": False,
            "marker_detection_accuracy_guaranteed": False,
            "key_or_bpm_accuracy_guaranteed": False,
        },
    }
    payload["record_sha256"] = _sha256_text(_canonical_json(payload))
    return payload


def verify_musical_idea_provenance(record: Mapping[str, Any]) -> bool:
    """Verify the record digest and the non-negotiable metadata boundary."""

    if set(record) != {
        "schema_version", "recorded_at", "consent", "source",
        "transformation", "output", "boundaries", "record_sha256",
    }:
        return False
    if record.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        return False
    consent = record.get("consent")
    if not isinstance(consent, Mapping) or consent.get("opted_in") is not True:
        return False
    if consent.get("purpose") != "metadata_only_transformation_provenance":
        return False
    if consent.get("sharing_scope") not in {"private", "selected_collaborators", "public"}:
        return False
    if not _is_sha256(consent.get("consent_reference_sha256")):
        return False
    source = record.get("source")
    output = record.get("output")
    if not isinstance(source, Mapping) or not isinstance(output, Mapping):
        return False
    if not all(
        _is_sha256(value)
        for value in (
            source.get("session_reference"),
            source.get("session_audio_sha256"),
            source.get("marker_audio_sha256"),
            output.get("clip_audio_sha256"),
        )
    ):
        return False
    boundaries = record.get("boundaries")
    if not isinstance(boundaries, Mapping) or boundaries != {
        "audio_content_included": False,
        "audio_path_included": False,
        "raw_audio_retained_by_maha": False,
        "fulcra_storage_or_access_policy_modified": False,
        "fulcra_enforcement_attested": False,
        "creative_ownership_attested": False,
        "marker_detection_accuracy_guaranteed": False,
        "key_or_bpm_accuracy_guaranteed": False,
    }:
        return False
    supplied_digest = record.get("record_sha256")
    if not isinstance(supplied_digest, str):
        return False
    unsigned = dict(record)
    del unsigned["record_sha256"]
    return supplied_digest == _sha256_text(_canonical_json(unsigned))


def build_share_boundary_record(
    record: Mapping[str, Any], *, audience_reference: str
) -> dict[str, Any]:
    """Derive a narrow sharing record for one selected MusicalIdea.

    The share record deliberately omits the full-session and marker digests. It
    binds the selected derived clip to its provenance record while disclosing
    only the fields the consent receipt permits.
    """

    if not verify_musical_idea_provenance(record):
        raise ProvenanceError("Cannot derive a share record from invalid provenance.")
    consent = record["consent"]
    if not isinstance(consent, Mapping) or consent.get("sharing_scope") == "private":
        raise ProvenanceError("Private consent does not authorize a share record.")
    output = record["output"]
    transformation = record["transformation"]
    if not isinstance(output, Mapping) or not isinstance(transformation, Mapping):
        raise ProvenanceError("Invalid provenance structure.")

    payload: dict[str, Any] = {
        "schema_version": SHARE_SCHEMA_VERSION,
        "provenance_record_sha256": record["record_sha256"],
        "sharing_scope": consent["sharing_scope"],
        "audience_reference_sha256": _sha256_text(
            _bounded_text("audience_reference", audience_reference)
        ),
        "musical_idea_reference": output["musical_idea_reference"],
        "clip_audio_sha256": output["clip_audio_sha256"],
        "processing_system": transformation["processing_system"],
        "processing_version": transformation["processing_version"],
        "marker_timestamp_seconds": transformation["marker_timestamp_seconds"],
        "window_start_seconds": transformation["window_start_seconds"],
        "window_duration_seconds": transformation["window_duration_seconds"],
        "key_estimate": output["key_estimate"],
        "bpm_estimate": output["bpm_estimate"],
        "boundaries": {
            "full_session_digest_disclosed": False,
            "marker_digest_disclosed": False,
            "audio_content_included": False,
            "creative_ownership_attested": False,
            "cryptographic_signature_present": False,
        },
    }
    payload["share_record_sha256"] = _sha256_text(_canonical_json(payload))
    return payload


def verify_share_boundary_record(record: Mapping[str, Any]) -> bool:
    """Verify a derived share receipt and its disclosure boundary."""

    if set(record) != {
        "schema_version", "provenance_record_sha256", "sharing_scope",
        "audience_reference_sha256", "musical_idea_reference",
        "clip_audio_sha256", "processing_system", "processing_version",
        "marker_timestamp_seconds", "window_start_seconds",
        "window_duration_seconds", "key_estimate", "bpm_estimate",
        "boundaries", "share_record_sha256",
    }:
        return False
    if record.get("schema_version") != SHARE_SCHEMA_VERSION:
        return False
    if record.get("sharing_scope") not in {"selected_collaborators", "public"}:
        return False
    if not all(
        _is_sha256(record.get(field))
        for field in (
            "provenance_record_sha256",
            "audience_reference_sha256",
            "clip_audio_sha256",
        )
    ):
        return False
    if record.get("boundaries") != {
        "full_session_digest_disclosed": False,
        "marker_digest_disclosed": False,
        "audio_content_included": False,
        "creative_ownership_attested": False,
        "cryptographic_signature_present": False,
    }:
        return False
    supplied_digest = record.get("share_record_sha256")
    if not isinstance(supplied_digest, str):
        return False
    unsigned = dict(record)
    del unsigned["share_record_sha256"]
    return supplied_digest == _sha256_text(_canonical_json(unsigned))


def write_metadata_record(record: Mapping[str, Any], destination: PathLike) -> Path:
    """Atomically persist JSON metadata; audio is never accepted as input."""

    target = Path(destination)
    if target.suffix.lower() != ".json":
        raise ProvenanceError("Metadata evidence destination must end in .json.")
    if not (
        verify_musical_idea_provenance(record)
        or verify_share_boundary_record(record)
    ):
        raise ProvenanceError("Refusing to write an invalid metadata evidence record.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(f"{json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False)}\n")
    temporary.replace(target)
    return target
