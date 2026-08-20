"""Audio marker detection.

See app/features/audio_marker_detection.md for the full spec. The key
design constraint: detection quality is expected to keep improving over
time, so the *interface* matters more than any one implementation. Every
caller should depend only on the `MarkerDetector` protocol (or the
`detect_marker` convenience function, which uses a default implementation)
-- never on the internals of a specific algorithm.
"""
import logging
from pathlib import Path
from typing import Protocol, Union

import librosa
import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


class MarkerDetectionError(Exception):
    """Raised when marker detection cannot be performed (e.g. bad input)."""


class MarkerDetector(Protocol):
    """Stable interface every marker-detection implementation must satisfy.

    Given a session recording and a reference marker sample (both as paths
    to WAV files), return a list of timestamps (seconds, floats) where the
    marker was detected in the session. Callers depend only on this
    signature, never on how detection is actually performed internally.
    """

    def detect(self, session_wav: PathLike, marker_wav: PathLike) -> list[float]:
        ...


class NullMarkerDetector:
    """Trivial "always returns no matches" implementation.

    Exists to prove the interface boundary is real: anything that calls a
    `MarkerDetector` should work identically (just with different results)
    regardless of which implementation is plugged in. Useful in tests and
    as a safe no-op default before a real detector is configured.
    """

    def detect(self, session_wav: PathLike, marker_wav: PathLike) -> list[float]:
        return []


class MFCCCorrelationDetector:
    """Detects a marker via normalized MFCC cross-correlation.

    Approach (informed by a prior implementation of this same concept,
    consulted for reference only -- this code is independent):
      1. Load both files, resampled to a lower rate suitable for MFCC math.
      2. Normalize amplitude on both (fixes low-gain mobile recordings).
      3. Trim leading/trailing silence from the marker sample only, so
         silence in the reference clip doesn't distort the correlation.
      4. Compute per-coefficient-normalized MFCCs for both signals.
      5. Cross-correlate each MFCC coefficient's time series and sum.
      6. Find peaks above `threshold_ratio` * max correlation, with a
         minimum time distance between peaks so one sustained marker isn't
         reported as many separate hits.
    """

    def __init__(
        self,
        analysis_sample_rate: int = 22050,
        silence_trim_top_db: float = 25.0,
        threshold_ratio: float = 0.94,
        min_peak_distance_seconds: float = 5.0,
    ) -> None:
        self.analysis_sample_rate = analysis_sample_rate
        self.silence_trim_top_db = silence_trim_top_db
        self.threshold_ratio = threshold_ratio
        self.min_peak_distance_seconds = min_peak_distance_seconds

    def detect(self, session_wav: PathLike, marker_wav: PathLike) -> list[float]:
        session_path = Path(session_wav)
        marker_path = Path(marker_wav)

        if not session_path.is_file():
            raise MarkerDetectionError(f"Session WAV not found: {session_path}")
        if not marker_path.is_file():
            raise MarkerDetectionError(f"Marker WAV not found: {marker_path}")

        sr = self.analysis_sample_rate
        try:
            y_session, _ = librosa.load(str(session_path), sr=sr)
            y_marker_raw, _ = librosa.load(str(marker_path), sr=sr)
        except Exception as exc:
            raise MarkerDetectionError(
                f"Failed to load audio for marker detection: {exc}"
            ) from exc

        if y_session.size == 0 or y_marker_raw.size == 0:
            raise MarkerDetectionError("Session or marker audio is empty.")

        y_session = librosa.util.normalize(y_session)
        y_marker_raw = librosa.util.normalize(y_marker_raw)
        y_marker, _ = librosa.effects.trim(y_marker_raw, top_db=self.silence_trim_top_db)

        mfcc_session = librosa.feature.mfcc(y=y_session, sr=sr)
        mfcc_marker = librosa.feature.mfcc(y=y_marker, sr=sr)

        if mfcc_session.shape[1] < mfcc_marker.shape[1]:
            # Session shorter than the marker itself -- no valid window to
            # correlate against, so there can be no detections.
            return []

        mfcc_session = self._normalize_per_coefficient(mfcc_session)
        mfcc_marker = self._normalize_per_coefficient(mfcc_marker)

        correlation = np.zeros(mfcc_session.shape[1] - mfcc_marker.shape[1] + 1)
        for coeff_idx in range(mfcc_marker.shape[0]):
            correlation += signal.correlate(
                mfcc_session[coeff_idx], mfcc_marker[coeff_idx], mode="valid"
            )

        max_corr = np.max(correlation)
        if max_corr <= 0:
            return []

        threshold = max_corr * self.threshold_ratio
        min_distance_frames = max(
            1, librosa.time_to_frames(self.min_peak_distance_seconds, sr=sr)
        )

        peaks, _ = signal.find_peaks(
            correlation, height=threshold, distance=min_distance_frames
        )

        timestamps = [float(librosa.frames_to_time(p, sr=sr)) for p in peaks]
        return timestamps

    @staticmethod
    def _normalize_per_coefficient(mfcc: np.ndarray) -> np.ndarray:
        mean = np.mean(mfcc, axis=1, keepdims=True)
        std = np.std(mfcc, axis=1, keepdims=True)
        return (mfcc - mean) / (std + 1e-8)


def detect_marker(
    session_wav: PathLike,
    marker_wav: PathLike,
    detector: "MarkerDetector | None" = None,
) -> list[float]:
    """Convenience entry point: detect marker timestamps using a detector.

    Defaults to `MFCCCorrelationDetector` if no detector is supplied, but
    callers are free to pass any object satisfying the `MarkerDetector`
    protocol -- this function (and everything downstream of it) never
    depends on which one is plugged in.
    """
    if detector is None:
        detector = MFCCCorrelationDetector()
    return detector.detect(session_wav, marker_wav)
