"""Tests for DSP idea extraction (clip cut + Key/BPM estimate).

See app/features/dsp_idea_extraction.md for acceptance criteria.
"""
from pathlib import Path

import pytest

from audio import (
    IdeaExtractionError,
    compute_extraction_window,
    convert_webm_to_wav,
    detect_key_and_bpm,
    extract_idea_clip,
    extract_musical_idea,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RAW_SESSION_WEBM = FIXTURES_DIR / "raw_session.webm"


@pytest.fixture(scope="module")
def session_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    processed_dir = tmp_path_factory.mktemp("processed")
    return convert_webm_to_wav(RAW_SESSION_WEBM, processed_dir / "raw_session.wav")


def test_compute_extraction_window_normal_case() -> None:
    """15s lookback ending at the marker, well after t=15s into the session."""
    start, duration = compute_extraction_window(38.6, lookback_seconds=15.0)
    assert start == pytest.approx(23.6, abs=0.01)
    assert duration == pytest.approx(15.0, abs=0.01)


def test_compute_extraction_window_marker_near_start() -> None:
    """Marker occurs less than 15s into the session: shift/truncate rather
    than producing a negative-length window."""
    start, duration = compute_extraction_window(5.0, lookback_seconds=15.0)
    assert start == 0.0
    assert duration == pytest.approx(5.0, abs=0.01)


def test_compute_extraction_window_marker_at_zero() -> None:
    """Marker essentially at t=0: no meaningful lookback available, but
    must still produce a valid, positive-duration window, not crash."""
    start, duration = compute_extraction_window(0.0, lookback_seconds=15.0)
    assert start == 0.0
    assert duration > 0


def test_compute_extraction_window_rejects_negative_timestamp() -> None:
    with pytest.raises(IdeaExtractionError):
        compute_extraction_window(-1.0)


def test_extract_idea_clip_produces_valid_file(session_wav: Path, tmp_path: Path) -> None:
    """Extraction around the real, validated marker timestamp (~t=38.6s)."""
    output_path = tmp_path / "idea.wav"
    result_path = extract_idea_clip(session_wav, 38.6, output_path, lookback_seconds=15.0)

    assert result_path.exists()
    assert result_path == output_path
    assert result_path.stat().st_size > 0


def test_extract_musical_idea_full_pipeline(session_wav: Path, tmp_path: Path) -> None:
    """Full pipeline: clip extraction + Key/BPM estimate, using the real
    validated marker timestamp."""
    output_path = tmp_path / "idea.wav"
    result = extract_musical_idea(session_wav, 38.6, output_path, lookback_seconds=15.0)

    assert result["clip_path"].exists()
    assert isinstance(result["key"], str) and result["key"] != ""
    assert isinstance(result["bpm"], int)
    assert result["bpm"] > 0
    assert result["start_time_seconds"] == pytest.approx(23.6, abs=0.01)
    assert result["duration_seconds"] == pytest.approx(15.0, abs=0.01)


def test_extract_idea_clip_missing_session_raises(tmp_path: Path) -> None:
    with pytest.raises(IdeaExtractionError, match="Session WAV not found"):
        extract_idea_clip(tmp_path / "missing.wav", 10.0, tmp_path / "out.wav")


def test_detect_key_and_bpm_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IdeaExtractionError, match="Audio file not found"):
        detect_key_and_bpm(tmp_path / "missing.wav")


def test_extract_near_start_uses_full_available_duration(
    session_wav: Path, tmp_path: Path
) -> None:
    """Marker very close to the start of the session: extracted clip
    duration should match the truncated (not full 15s) window."""
    output_path = tmp_path / "idea_near_start.wav"
    result = extract_musical_idea(session_wav, 3.0, output_path, lookback_seconds=15.0)

    assert result["start_time_seconds"] == 0.0
    assert result["duration_seconds"] == pytest.approx(3.0, abs=0.1)
    assert result["clip_path"].exists()
