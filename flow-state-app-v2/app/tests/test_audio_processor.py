import logging
from pathlib import Path
import pytest
from audio import (
    AudioConversionError,
    AudioProcessingError,
    convert_webm_to_wav,
    get_wav_metadata,
    process_audio_file,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RAW_SESSION_WEBM = FIXTURES_DIR / "raw_session.webm"
MARKER_WEBM = FIXTURES_DIR / "marker.webm"


def test_convert_raw_session_webm_to_wav(tmp_path: Path) -> None:
    """Validate converting the raw session fixture to 16-bit PCM 44.1kHz stereo WAV."""
    output_wav = tmp_path / "raw_session.wav"
    result_path = convert_webm_to_wav(RAW_SESSION_WEBM, output_wav)

    assert result_path.exists()
    assert result_path == output_wav

    metadata = get_wav_metadata(result_path)
    assert metadata["channels"] == 2
    assert metadata["sample_rate"] == 44100
    assert metadata["bit_depth"] == 16
    assert 40.0 < metadata["duration_seconds"] < 43.0


def test_convert_marker_webm_to_wav(tmp_path: Path) -> None:
    """Validate converting the reference marker fixture to WAV."""
    output_wav = tmp_path / "marker.wav"
    result_path = convert_webm_to_wav(MARKER_WEBM, output_wav)

    assert result_path.exists()
    assert result_path == output_wav

    metadata = get_wav_metadata(result_path)
    assert metadata["channels"] == 2
    assert metadata["sample_rate"] == 44100
    assert metadata["bit_depth"] == 16
    assert 4.5 < metadata["duration_seconds"] < 6.0


def test_process_audio_file_directory_mirroring(tmp_path: Path) -> None:
    """Validate process_audio_file mirrors session stem into target processed directory."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    processed_dir = tmp_path / "processed"

    raw_session = raw_dir / "session_abc_123.webm"
    raw_session.write_bytes(RAW_SESSION_WEBM.read_bytes())

    output_path = process_audio_file(raw_session, processed_dir=processed_dir)

    assert output_path == processed_dir / "session_abc_123.wav"
    assert output_path.exists()

    metadata = get_wav_metadata(output_path)
    assert metadata["channels"] == 2
    assert metadata["sample_rate"] == 44100
    assert metadata["bit_depth"] == 16


def test_conversion_failure_nonexistent_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Validate error handling for non-existent input file."""
    non_existent = tmp_path / "does_not_exist.webm"
    output_wav = tmp_path / "output.wav"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AudioProcessingError) as exc_info:
            convert_webm_to_wav(non_existent, output_wav)

    assert "does not exist" in str(exc_info.value)
    assert "does not exist" in caplog.text
    assert not output_wav.exists()


def test_conversion_failure_corrupt_input(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Validate error handling for corrupted/invalid input file."""
    corrupt_file = tmp_path / "corrupt_session.webm"
    corrupt_file.write_text("This is invalid text data, not a WebM file.")
    processed_dir = tmp_path / "processed"
    target_wav = processed_dir / "corrupt_session.wav"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AudioProcessingError) as exc_info:
            process_audio_file(corrupt_file, processed_dir=processed_dir)

    assert "FFmpeg conversion failed" in str(exc_info.value)
    assert "FFmpeg conversion failed" in caplog.text
    assert not target_wav.exists()

    if processed_dir.exists():
        assert list(processed_dir.glob("*.tmp*")) == []
        assert list(processed_dir.glob("*.wav")) == []


def test_get_wav_metadata_invalid_file(tmp_path: Path) -> None:
    """Validate get_wav_metadata error handling."""
    missing = tmp_path / "missing.wav"
    with pytest.raises(AudioProcessingError) as exc:
        get_wav_metadata(missing)
    assert "WAV file not found" in str(exc.value)

    invalid = tmp_path / "invalid.wav"
    invalid.write_text("not a wav file")
    with pytest.raises(AudioProcessingError) as exc:
        get_wav_metadata(invalid)
    assert "Failed to read WAV metadata" in str(exc.value)
