"""DSP idea extraction: given a marker timestamp, extract a fixed-length
clip and estimate its musical Key and BPM.

See app/features/dsp_idea_extraction.md for the full spec.
"""
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Union

import librosa
import numpy as np

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

DEFAULT_LOOKBACK_SECONDS = 15.0

# Krumhansl-Schmuckler key profiles (simplified), consulted from a prior
# implementation of this same concept for reference only -- this code is
# independent.
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class IdeaExtractionError(Exception):
    """Raised when clip extraction or musical analysis fails."""


def compute_extraction_window(
    marker_timestamp_seconds: float,
    lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
) -> tuple[float, float]:
    """Compute the (start_time, duration) window to extract for a marker.

    This is a lookback window *ending* at the marker, not a centered one:
    the marker is played at the moment the musician decides an idea is
    worth keeping, so the idea itself already happened just before that
    moment.

    Handles the edge case where the marker occurs less than
    `lookback_seconds` into the session by starting at 0 and using
    whatever duration is actually available, rather than a negative or
    zero-length window.
    """
    if marker_timestamp_seconds < 0:
        raise IdeaExtractionError(
            f"marker_timestamp_seconds must be >= 0, got {marker_timestamp_seconds}"
        )

    start_time = max(0.0, marker_timestamp_seconds - lookback_seconds)
    duration = marker_timestamp_seconds - start_time

    if duration <= 0:
        # Marker is right at (or before) t=0 -- nothing to look back on.
        # Fall back to a minimal-but-valid window starting at 0.
        start_time = 0.0
        duration = min(lookback_seconds, max(marker_timestamp_seconds, 0.1))

    return start_time, duration


def detect_key_and_bpm(audio_path: PathLike) -> tuple[str, int]:
    """Estimate musical Key and BPM (tempo) for an audio clip.

    Returns:
        (key_label, bpm) e.g. ("C Major", 120). Accuracy is not
        guaranteed to be perfect -- this produces an estimate, per
        dsp_idea_extraction.md's acceptance criteria.
    """
    path_obj = Path(audio_path)
    if not path_obj.is_file():
        raise IdeaExtractionError(f"Audio file not found: {path_obj}")

    try:
        y, sr = librosa.load(str(path_obj), sr=22050)
    except Exception as exc:
        raise IdeaExtractionError(f"Failed to load audio for analysis: {exc}") from exc

    if y.size == 0:
        raise IdeaExtractionError(f"Audio file is empty: {path_obj}")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(np.round(tempo[0] if isinstance(tempo, np.ndarray) else tempo))

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_sum = np.sum(chroma, axis=1)

    best_corr = -1.0
    best_key = "Unknown"
    for i in range(12):
        rotated_major = np.roll(_MAJOR_PROFILE, i)
        rotated_minor = np.roll(_MINOR_PROFILE, i)

        corr_major = float(np.corrcoef(chroma_sum, rotated_major)[0, 1])
        corr_minor = float(np.corrcoef(chroma_sum, rotated_minor)[0, 1])

        if corr_major > best_corr:
            best_corr = corr_major
            best_key = f"{_PITCH_CLASSES[i]} Major"
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = f"{_PITCH_CLASSES[i]} minor"

    return best_key, bpm


def extract_idea_clip(
    session_wav: PathLike,
    marker_timestamp_seconds: float,
    output_path: PathLike,
    lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
) -> Path:
    """Extract a fixed-length clip around a marker timestamp from a
    processed session .wav, using ffmpeg for the actual cut.

    Raises:
        IdeaExtractionError: if the session file is missing or ffmpeg
            fails to produce the clip.
    """
    session_path = Path(session_wav)
    out_path = Path(output_path)

    if not session_path.is_file():
        raise IdeaExtractionError(f"Session WAV not found: {session_path}")

    start_time, duration = compute_extraction_window(
        marker_timestamp_seconds, lookback_seconds
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_time),
        "-t",
        str(duration),
        "-i",
        str(session_path),
        str(out_path),
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        error_msg = (
            f"FFmpeg clip extraction failed (exit code {result.returncode}) "
            f"for {session_path} at t={start_time}s, duration={duration}s:\n"
            f"{result.stderr}"
        )
        logger.error(error_msg)
        if out_path.exists():
            out_path.unlink()
        raise IdeaExtractionError(error_msg)

    return out_path


def extract_musical_idea(
    session_wav: PathLike,
    marker_timestamp_seconds: float,
    output_path: PathLike,
    lookback_seconds: float = DEFAULT_LOOKBACK_SECONDS,
) -> dict:
    """Full extraction pipeline: cut the clip, then estimate Key and BPM.

    Returns:
        A dict: {"clip_path": Path, "key": str, "bpm": int,
                 "start_time_seconds": float, "duration_seconds": float}
    """
    start_time, duration = compute_extraction_window(
        marker_timestamp_seconds, lookback_seconds
    )
    clip_path = extract_idea_clip(
        session_wav, marker_timestamp_seconds, output_path, lookback_seconds
    )
    key, bpm = detect_key_and_bpm(clip_path)

    return {
        "clip_path": clip_path,
        "key": key,
        "bpm": bpm,
        "start_time_seconds": start_time,
        "duration_seconds": duration,
    }
