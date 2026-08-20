"""Tests for audio marker detection.

See app/features/audio_marker_detection.md for acceptance criteria, and
app/tests/fixtures/README.md for the validated ground truth used below
(exactly 1 marker detection at ~t=38.6s in raw_session.webm).
"""
from pathlib import Path

import pytest

from audio import (
    MarkerDetectionError,
    MFCCCorrelationDetector,
    NullMarkerDetector,
    convert_webm_to_wav,
    detect_marker,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RAW_SESSION_WEBM = FIXTURES_DIR / "raw_session.webm"
MARKER_WEBM = FIXTURES_DIR / "marker.webm"


@pytest.fixture(scope="module")
def processed_fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Convert the raw .webm fixtures to .wav once per test module, since
    marker detection operates on processed audio, not raw .webm (per
    audio_processing_pipeline.md)."""
    processed_dir = tmp_path_factory.mktemp("processed")
    session_wav = convert_webm_to_wav(
        RAW_SESSION_WEBM, processed_dir / "raw_session.wav"
    )
    marker_wav = convert_webm_to_wav(MARKER_WEBM, processed_dir / "marker.wav")
    return {"session": session_wav, "marker": marker_wav}


def test_detects_exactly_one_marker_at_known_timestamp(
    processed_fixtures: dict[str, Path],
) -> None:
    """Validated ground truth: exactly 1 marker at ~t=38.6s (see fixtures/README.md)."""
    timestamps = detect_marker(
        processed_fixtures["session"], processed_fixtures["marker"]
    )
    assert len(timestamps) == 1
    assert 37.5 < timestamps[0] < 39.5


def test_default_detector_is_mfcc_correlation(
    processed_fixtures: dict[str, Path],
) -> None:
    """detect_marker() with no detector arg behaves like an explicit
    MFCCCorrelationDetector (same default, verified equal results)."""
    default_result = detect_marker(
        processed_fixtures["session"], processed_fixtures["marker"]
    )
    explicit_result = detect_marker(
        processed_fixtures["session"],
        processed_fixtures["marker"],
        detector=MFCCCorrelationDetector(),
    )
    assert default_result == explicit_result


def test_swappable_interface_null_detector_returns_no_matches(
    processed_fixtures: dict[str, Path],
) -> None:
    """Proves the interface boundary is real: swapping in a trivial,
    completely different implementation (NullMarkerDetector) behind the
    same `detect_marker` call site changes the *result* without changing
    the *call*, and callers never need to know which one is plugged in."""
    result = detect_marker(
        processed_fixtures["session"],
        processed_fixtures["marker"],
        detector=NullMarkerDetector(),
    )
    assert result == []


def test_false_positive_rate_on_silence(tmp_path: Path) -> None:
    """A quiet/silent clip with no marker present should not hallucinate
    marker hits."""
    import numpy as np
    import soundfile as sf

    silence_path = tmp_path / "silence.wav"
    sample_rate = 44100
    duration_seconds = 20
    silence = np.zeros(sample_rate * duration_seconds, dtype="float32")
    sf.write(silence_path, silence, sample_rate)

    marker_wav = convert_webm_to_wav(MARKER_WEBM, tmp_path / "marker.wav")

    timestamps = detect_marker(silence_path, marker_wav)
    assert timestamps == []


def test_missing_session_file_raises_clear_error(tmp_path: Path) -> None:
    marker_wav = convert_webm_to_wav(MARKER_WEBM, tmp_path / "marker.wav")
    with pytest.raises(MarkerDetectionError, match="Session WAV not found"):
        detect_marker(tmp_path / "does_not_exist.wav", marker_wav)


def test_missing_marker_file_raises_clear_error(
    processed_fixtures: dict[str, Path], tmp_path: Path
) -> None:
    with pytest.raises(MarkerDetectionError, match="Marker WAV not found"):
        detect_marker(processed_fixtures["session"], tmp_path / "does_not_exist.wav")


def test_session_shorter_than_marker_returns_no_matches(
    processed_fixtures: dict[str, Path], tmp_path: Path
) -> None:
    """A session recording shorter than the marker sample itself has no
    valid correlation window -- should return no matches, not crash."""
    import soundfile as sf

    marker_audio, sr = sf.read(processed_fixtures["marker"])
    # Take a session clip shorter than the marker itself.
    short_session_path = tmp_path / "short_session.wav"
    sf.write(short_session_path, marker_audio[: len(marker_audio) // 4], sr)

    timestamps = detect_marker(short_session_path, processed_fixtures["marker"])
    assert timestamps == []
