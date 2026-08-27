from dataclasses import dataclass, field
from typing import Optional

import numpy as np

@dataclass
class SignalTimeSeries:
    """Represents a standard time-series coordinate mapping."""
    x: np.ndarray = field(default_factory=lambda: np.array([]))
    y: np.ndarray = field(default_factory=lambda: np.array([]))

    def get_x_without_NaN(self):
        valid_mask = ~(np.isnan(self.x) | np.isnan(self.y))
        if not np.any(valid_mask):
            return np.array([])
        else:
            return self.x[valid_mask]

    def get_y_without_NaN(self):
        valid_mask = ~(np.isnan(self.x) | np.isnan(self.y))
        if not np.any(valid_mask):
            return np.array([])
        else:
            return self.y[valid_mask]

    def get_last_y(self):
        return self.y[-1]


@dataclass
class SpectrogramData:
    """Stores 2D spectrogram arrays and their axis bins."""
    x: np.ndarray = field(default_factory=lambda: np.array([]))  # Time bins
    y: np.ndarray = field(default_factory=lambda: np.array([]))  # Frequency bins
    magnitude_db: np.ndarray = field(default_factory=lambda: np.array([[]])) # 2D STFT matrix

    def get_x_without_NaN(self):
        # valid_mask = ~(np.isnan(self.x) | np.isnan(self.y) | np.isnan(self.magnitude_db))
        # if not np.any(valid_mask):
        #     return np.array([])
        # else:
        #     return self.x[valid_mask]
        return self.x

    def get_y_without_NaN(self):
        # valid_mask = ~(np.isnan(self.x) | np.isnan(self.y) | np.isnan(self.magnitude_db))
        # if not np.any(valid_mask):
        #     return np.array([])
        # else:
        #     return self.y[valid_mask]
        return self.y

    def get_magnitude_without_NaN(self):
        # valid_mask = ~(np.isnan(self.x) | np.isnan(self.y) | np.isnan(self.magnitude_db))
        # if not np.any(valid_mask):
        #     return np.array([])
        # else:
        #     return self.magnitude_db[valid_mask]
        return self.magnitude_db

    def get_last_y(self):
        return self.y[-1]

@dataclass
class AudioFeatures:
    # Core Acoustic Features
    pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    loudness: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    weight: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    jitter: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    shimmer: SignalTimeSeries = field(default_factory=SignalTimeSeries)

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
    jitter: float
    shimmer: float
    H1_H2: float
    H1_H3: float
    H1_H4: float
    H1_A3: float

    F1: float
    F2: float
    F3: float

    F1_Pitch: Optional[float] = None
    F2_Pitch: Optional[float] = None
    F3_Pitch: Optional[float] = None

    size: Optional[float] = None
    spectrogram: Optional[SpectrogramData] = None
