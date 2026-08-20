import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger(__name__)


class AudioProcessingError(Exception):
    """Base exception for audio processing errors."""

    pass


class AudioConversionError(AudioProcessingError):
    """Raised when audio conversion fails."""

    pass


def get_wav_metadata(wav_path: Union[str, Path]) -> dict[str, Any]:
    """
    Read metadata parameters from a .wav file.

    Args:
        wav_path: Path to .wav file.

    Returns:
        Dict containing channels, sample_width, sample_rate, num_frames,
        duration_seconds, bit_depth.
    """
    path_obj = Path(wav_path)
    if not path_obj.is_file():
        raise AudioProcessingError(f"WAV file not found: {wav_path}")

    try:
        with wave.open(str(path_obj), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            duration = n_frames / float(framerate) if framerate > 0 else 0.0

            return {
                "channels": channels,
                "sample_width": sample_width,
                "sample_rate": framerate,
                "num_frames": n_frames,
                "duration_seconds": duration,
                "bit_depth": sample_width * 8,
            }
    except Exception as e:
        raise AudioProcessingError(f"Failed to read WAV metadata for {wav_path}: {e}") from e


def convert_webm_to_wav(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    sample_rate: int = 44100,
    channels: int = 2,
) -> Path:
    """
    Converts a raw .webm audio file to a 16-bit PCM .wav file using ffmpeg.

    Target format: PCM 16-bit (pcm_s16le), 44.1kHz (default), stereo (default).

    Args:
        input_path: Path to input .webm file.
        output_path: Target path for output .wav file.
        sample_rate: Target sample rate in Hz (default: 44100).
        channels: Target channel count (default: 2 for stereo).

    Returns:
        Path object pointing to converted .wav file.

    Raises:
        AudioProcessingError: If input file is missing, conversion fails,
                              or output is invalid.
    """
    inp = Path(input_path)
    out = Path(output_path)

    if not inp.exists():
        msg = f"Input audio file does not exist: {inp}"
        logger.error(msg)
        raise AudioProcessingError(msg)

    if not inp.is_file():
        msg = f"Input audio path is not a file: {inp}"
        logger.error(msg)
        raise AudioProcessingError(msg)

    out.parent.mkdir(parents=True, exist_ok=True)

    temp_fd, temp_path_str = tempfile.mkstemp(
        suffix=".tmp.wav", dir=out.parent
    )
    os.close(temp_fd)
    temp_path = Path(temp_path_str)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-err_detect",
        "ignore_err",
        "-i",
        str(inp),
        "-vn",
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        str(temp_path),
    ]

    try:
        logger.info("Converting %s to WAV at %s", inp, temp_path)
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            error_msg = (
                f"FFmpeg conversion failed (exit code {result.returncode}) for {inp}:\n"
                f"{result.stderr}"
            )
            logger.error(error_msg)
            raise AudioConversionError(error_msg)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            error_msg = f"FFmpeg produced an empty or missing output file for {inp}"
            logger.error(error_msg)
            raise AudioConversionError(error_msg)

        metadata = get_wav_metadata(temp_path)
        if metadata["channels"] != channels or metadata["sample_rate"] != sample_rate:
            error_msg = (
                f"Converted WAV format mismatch for {inp}: "
                f"got {metadata['channels']} ch / {metadata['sample_rate']} Hz, "
                f"expected {channels} ch / {sample_rate} Hz"
            )
            logger.error(error_msg)
            raise AudioConversionError(error_msg)

        temp_path.replace(out)
        logger.info("Successfully converted %s -> %s", inp, out)
        return out

    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

        if isinstance(e, AudioProcessingError):
            raise
        raise AudioProcessingError(f"Unexpected error during conversion of {inp}: {e}") from e


def process_audio_file(
    input_path: Union[str, Path],
    processed_dir: Union[str, Path] = "processed",
) -> Path:
    """
    Process a raw .webm audio file (session or reference marker) into the processed directory.

    Given input like 'raw/session123.webm', creates 'processed/session123.wav'.

    Args:
        input_path: Path to raw input file (e.g. .webm).
        processed_dir: Directory where processed .wav file should be saved.

    Returns:
        Path to processed .wav file.
    """
    inp = Path(input_path)
    p_dir = Path(processed_dir)

    output_filename = f"{inp.stem}.wav"
    output_path = p_dir / output_filename

    return convert_webm_to_wav(input_path=inp, output_path=output_path)
