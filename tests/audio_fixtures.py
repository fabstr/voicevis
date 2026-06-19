import numpy as np
import pytest


def generate_multi_tone(frequencies, db_weights, duration, sample_rate=16000):
    """Generates mixed frequencies with explicit dB relative gains."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    combined_signal = np.zeros_like(t)
    for freq, db in zip(frequencies, db_weights):
        combined_signal += (10 ** (db / 20)) * np.sin(2 * np.pi * freq * t)
    if np.max(np.abs(combined_signal)) > 0:
        combined_signal /= np.max(np.abs(combined_signal))
    return combined_signal, sample_rate


@pytest.fixture
def soft_isch_aaa():
    freqs = [225, 446, 670, 894, 1116, 1338, 1558, 1790, 2014, 2235, 2454, 2668, 5000, 7638, 10341, 13052, 14562]
    dbs =   [ -5, -16, -19, -14,  -23,   -30, -48,  -53,  -53,  -60,  -60,  -55,  -50,  -57,   -61,   -70,   -72]  # Sloping spectral envelope
    duration = 2
    sample_rate = 44800
    pcm_data, sr = generate_multi_tone(freqs, dbs, duration, sample_rate)
    return pcm_data, sr, duration
