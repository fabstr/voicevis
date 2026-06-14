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
class AudioFeatures:
    # Core Acoustic Features
    pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    Pitch_BW: BandwidthTimeSeries = field(default_factory=BandwidthTimeSeries)

    loudness: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    slopes: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    # Formants & Initial Bandwidths (IBW)
    F1: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F1_IBW: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2_IBW: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3_IBW: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    # Formant Ratios
    F2_F1: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2_F1_IBW: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    F3_F1: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3_F1_IBW: SignalTimeSeries = field(default_factory=SignalTimeSeries)

    # Pitch-Relative Formants (Standard & Bandwidth variants)
    F1_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F1_Pitch_BW: BandwidthTimeSeries = field(default_factory=BandwidthTimeSeries)

    F2_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F2_Pitch_BW: BandwidthTimeSeries = field(default_factory=BandwidthTimeSeries)

    F3_Pitch: SignalTimeSeries = field(default_factory=SignalTimeSeries)
    F3_Pitch_BW: BandwidthTimeSeries = field(default_factory=BandwidthTimeSeries)

    # Metadata (Initialized via your audio processing pipeline)
    sample_rate: float = 0.0
    length_seconds: float = 0.0

@dataclass
class FeatureSnapshot:
    time: float

    # Independent Plots
    loudness: float
    pitch: float

    # Formant Ratios
    F1_ratio: float
    F3_ratio: float

    # Individual Formants
    F1: float
    F2: float
    F3: float

    # Spectral Slopes
    slopes: float

    # IBWs (Optional, as they can be None on empty/silent chunks)
    F1_IBW: Optional[float] = None
    F2_IBW: Optional[float] = None
    F3_IBW: Optional[float] = None
    F2_F1_IBW: Optional[float] = None
    F3_F1_IBW: Optional[float] = None