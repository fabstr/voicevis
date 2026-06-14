from dataclasses import dataclass

@dataclass
class TargetConfig:
    # Loudness
    loudness_min: float = 0.0
    loudness_max: float = 1.0

    # Pitch
    pitch_min: float = 0.0
    pitch_max: float = 350.0

    # Formants
    f1_min: float = 300.0
    f1_max: float = 500.0
    f2_min: float = 1300.0
    f2_max: float = 1700.0
    f3_min: float = 2550.0
    f3_max: float = 2750.0

    # Formant / Pitch Ratios
    f3_pitch_min: float = 1.0
    f3_pitch_max: float = 50.0
    f2_pitch_min: float = 1.0
    f2_pitch_max: float = 30.0
    f1_pitch_min: float = 1.0
    f1_pitch_max: float = 15.0

    # Formant Ratios
    f3_f1_min: float = 1.0
    f3_f1_max: float = 9.0
    f2_f1_min: float = 1.0
    f2_f1_max: float = 5.0

    # Advanced Metrics
    size_min: float = -500.0
    size_max: float = 1000.0
    weight_min: float = 0.0
    weight_max: float = 4.0e-7