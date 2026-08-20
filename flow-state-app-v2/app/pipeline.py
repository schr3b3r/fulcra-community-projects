"""Pipeline orchestration: wires together the individually-built features
(audio_processing_pipeline, audio_marker_detection, dsp_idea_extraction,
processing_status_tracking, musical_idea_publishing) into the end-to-end
flow that runs once a session recording finishes.

This module is intentionally the "glue" layer -- it doesn't implement any
DSP/Fulcra logic itself, it just calls the already-tested feature modules
in the right order and records status at each step.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from audio import (
    AudioProcessingError,
    IdeaExtractionError,
    MarkerDetectionError,
    convert_webm_to_wav,
    detect_marker,
    extract_musical_idea,
)
from fulcra_client import FulcraAuthError, get_fulcra_client
from idea_publishing import PublishingError, publish_musical_idea
from status_tracking import StatusTrackingError, record_status

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
RAW_DIR = APP_DIR / "raw"
PROCESSED_DIR = APP_DIR / "processed"
IDEAS_DIR = APP_DIR / "ideas"

ProgressCallback = Optional[Callable[[str], None]]


def _notify(on_progress: ProgressCallback, message: str) -> None:
    if on_progress is not None:
        try:
            on_progress(message)
        except Exception:  # noqa: BLE001 - progress reporting must never
            # break the actual pipeline.
            logger.exception("Progress callback raised; continuing pipeline.")


def _safe_record_status(
    session_id: str, stage: str, detail: Optional[str] = None, error: Optional[str] = None
) -> None:
    """Record a status update, but never let a Fulcra outage take down the
    pipeline itself -- status tracking is observability, not a hard
    dependency of the pipeline succeeding."""
    try:
        client = get_fulcra_client()
        record_status(client, session_id, stage=stage, detail=detail, error=error)
    except (FulcraAuthError, StatusTrackingError) as exc:
        logger.warning("Could not record status (%s) for %s: %s", stage, session_id, exc)


CURRENT_MARKER_POINTER = PROCESSED_DIR / ".current_marker"


def find_latest_processed_marker() -> Optional[Path]:
    """Find the most recently processed marker .wav file, if any.

    Mirrors the "current marker" concept from a prior implementation of
    this same concept: whichever marker was most recently recorded is
    treated as the active one for detecting future sessions against.

    Tracked via an explicit pointer file (written by
    process_marker_recording) rather than a filename convention, since
    session_ids for marker recordings aren't guaranteed to contain
    "marker_" as a substring -- that mismatch previously caused this
    function to silently find nothing even after a marker was
    successfully processed.
    """
    if not CURRENT_MARKER_POINTER.is_file():
        return None
    marker_path = Path(CURRENT_MARKER_POINTER.read_text().strip())
    return marker_path if marker_path.is_file() else None


def process_marker_recording(
    session_id: str, on_progress: ProgressCallback = None
) -> Path:
    """Process a freshly-recorded marker sample: convert its raw .webm to
    a processed .wav so it can be used as the reference for future session
    detection.

    Updates the "current marker" pointer (see find_latest_processed_marker)
    to point at this newly processed marker, so it becomes the one used
    for detecting markers in subsequently-recorded sessions.

    Returns:
        Path to the processed marker .wav.
    """
    raw_path = RAW_DIR / f"{session_id}.webm"
    _safe_record_status(session_id, stage="received", detail="marker sample received")

    _notify(on_progress, "Processing marker sample...")
    _safe_record_status(session_id, stage="processing")
    try:
        processed_path = convert_webm_to_wav(
            raw_path, PROCESSED_DIR / f"{session_id}.wav"
        )
    except AudioProcessingError as exc:
        _safe_record_status(session_id, stage="failed", error=str(exc))
        _notify(on_progress, f"Marker processing failed: {exc}")
        raise

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_MARKER_POINTER.write_text(str(processed_path))

    _safe_record_status(session_id, stage="processed")
    _notify(on_progress, "Marker ready for future session detection.")
    return processed_path


def process_completed_session(
    session_id: str, on_progress: ProgressCallback = None
) -> list[dict]:
    """Run the full pipeline for a completed session recording:
    convert -> detect marker(s) -> extract idea(s) -> publish to Fulcra.

    Every stage records its status via processing_status_tracking, and
    failures at any stage are recorded as "failed" (with the error) rather
    than silently dropped, per that feature's acceptance criteria.

    Returns:
        A list of dicts describing each published idea (or an empty list
        if no marker was detected / no marker sample exists yet).
    """
    raw_path = RAW_DIR / f"{session_id}.webm"
    _safe_record_status(session_id, stage="received", detail="session recording received")

    if not raw_path.is_file() or raw_path.stat().st_size == 0:
        _safe_record_status(
            session_id, stage="failed", error="Raw session file missing or empty."
        )
        _notify(on_progress, "No audio was recorded for this session.")
        return []

    _notify(on_progress, "Converting session audio...")
    _safe_record_status(session_id, stage="processing")
    try:
        processed_session_wav = convert_webm_to_wav(
            raw_path, PROCESSED_DIR / f"{session_id}.wav"
        )
    except AudioProcessingError as exc:
        _safe_record_status(session_id, stage="failed", error=str(exc))
        _notify(on_progress, f"Audio conversion failed: {exc}")
        return []

    _safe_record_status(session_id, stage="processed")

    marker_wav = find_latest_processed_marker()
    if marker_wav is None:
        _safe_record_status(
            session_id,
            stage="processed",
            detail="No marker sample recorded yet; skipping detection.",
        )
        _notify(on_progress, "No marker sample available yet -- session saved, but not scanned for ideas.")
        return []

    _notify(on_progress, "Scanning for marker...")
    _safe_record_status(session_id, stage="marker_detection")
    try:
        timestamps = detect_marker(processed_session_wav, marker_wav)
    except MarkerDetectionError as exc:
        _safe_record_status(session_id, stage="failed", error=str(exc))
        _notify(on_progress, f"Marker detection failed: {exc}")
        return []

    if not timestamps:
        _safe_record_status(
            session_id, stage="processed", detail="No marker detected in this session."
        )
        _notify(on_progress, "No marker detected in this session.")
        return []

    _notify(on_progress, f"Found {len(timestamps)} marker(s)! Extracting ideas...")

    published_ideas = []
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)

    for idx, timestamp in enumerate(timestamps):
        idea_id = f"{session_id}_idea{idx}"
        _safe_record_status(
            idea_id, stage="extracting", detail=f"marker at t={timestamp:.1f}s"
        )
        try:
            clip_path = IDEAS_DIR / f"{idea_id}.wav"
            extraction = extract_musical_idea(
                processed_session_wav, timestamp, clip_path
            )
        except IdeaExtractionError as exc:
            _safe_record_status(idea_id, stage="failed", error=str(exc))
            _notify(on_progress, f"Idea extraction failed at t={timestamp:.1f}s: {exc}")
            continue

        try:
            client = get_fulcra_client()
            publish_result = publish_musical_idea(
                client,
                extraction["clip_path"],
                key=extraction["key"],
                bpm=extraction["bpm"],
                session_id=session_id,
                marker_timestamp_seconds=timestamp,
            )
        except (FulcraAuthError, PublishingError) as exc:
            _safe_record_status(idea_id, stage="failed", error=str(exc))
            _notify(on_progress, f"Publishing failed for idea at t={timestamp:.1f}s: {exc}")
            continue

        _safe_record_status(idea_id, stage="published")
        _notify(
            on_progress,
            f"Published idea: {extraction['key']} @ {extraction['bpm']} BPM "
            f"(t={timestamp:.1f}s)",
        )
        published_ideas.append(
            {
                "idea_id": idea_id,
                "session_id": session_id,
                "marker_timestamp_seconds": timestamp,
                "key": extraction["key"],
                "bpm": extraction["bpm"],
                "local_clip_path": str(extraction["clip_path"]),
                "fulcra_file_path": publish_result["file_path"],
            }
        )

    return published_ideas
