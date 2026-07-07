from dataclasses import dataclass, field
from typing import Optional

import numpy as np

@dataclass
class SignalTimeSeries:
    """Represents a standard time-series coordinate mapping."""
    x: np.ndarray = field(default_factory=lambda: np.array([]))
    y: np.ndarray = field(default_factory=lambda: np.array([]))


@dataclass
class BandwidthTimeSeries(SignalTimeSeries):
    """Extends standard time-series to include Bandwidth (BW)."""
    BW: np.ndarray = field(default_factory=lambda: np.array([]))


@dataclass
class SpectrogramData:
    """Stores 2D spectrogram arrays and their axis bins."""
    x: np.ndarray = field(default_factory=lambda: np.array([]))  # Time bins
    y: np.ndarray = field(default_factory=lambda: np.array([]))  # Frequency bins
    magnitude_db: np.ndarray = field(default_factory=lambda: np.array([[]])) # 2D STFT matrix


@dataclass
class AudioFeatures:
    # Core Acoustic Features
    pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    loudness: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    slopes: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    weight_instantaneous: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    weight_0_1s: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    weight_1s: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    weight_5s: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    H1_H2: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    H1_H3: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    H1_H4: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    H1_A3: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    F1: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F1_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F1_Pitch_rel_amplitude: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    F2: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2_Pitch_rel_amplitude: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    F3: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3_Pitch_rel_amplitude: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    size: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    spectrogram: SpectrogramData = field(default_factory=SpectrogramData)

    # Metadata (Initialized via your audio processing pipeline)
    sample_rate: float = 0.0
    length_seconds: float = 0.0

@dataclass
class FeatureSnapshot:
    time: float

    pitch: float
    loudness: float
    weight: float
    slopes: float
    H1_H2: float
    H1_H3: float
    H1_H4: float
    H1_A3: float

    F1: float
    F2: float
    F3: float

    # Spectral Slopes
    # Formant to pitch ratios and BW
    F1_Pitch: Optional[float] = None
    F2_Pitch: Optional[float] = None
    F3_Pitch: Optional[float] = None

    size: Optional[float] = None
    spectrogram: Optional[SpectrogramData] = None
