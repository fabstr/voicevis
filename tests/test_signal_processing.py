import array
import os
import tempfile

import miniaudio
import numpy as np
import pytest

from conftest import soft_isch_aaa

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.TargetConfig import TargetConfig


@pytest.fixture
def analyzer():
    """Initializes a clean instance of your analyzer for each test."""
    config = TargetConfig()
    return AudioFeatureExtractor(config)

@pytest.fixture
def wav_file_path(soft_isch_aaa):
    """
    Fixture that saves the synthetic PCM data to a .wav file
    using miniaudio and returns the file path.
    """
    pcm_data, sr, _ = soft_isch_aaa
    wav_path = os.path.join(tempfile.mkdtemp(), "test_input.wav")

    # 1. Convert float signal (-1.0 to 1.0) to 16-bit signed integer values
    audio_int16 = (pcm_data * 32767).astype(np.int16)
    sample_array = array.array('h', audio_int16)

    # 2. Build the DecodedSoundFile wrapper (num_frames removed)
    sound_wrapper = miniaudio.DecodedSoundFile(
        wav_path,
        1,  # nchannels (Mono)
        sr,  # sample_rate
        miniaudio.SampleFormat.SIGNED16,  # sample_format
        sample_array  # array.array data samples
    )

    miniaudio.wav_write_file(wav_path, sound_wrapper)
    return wav_path

@pytest.fixture
def mp3_file_path(soft_isch_aaa, mocker):
    """
    Fixture that creates a dummy MP3 file path and mocks the internal
    convertMp3ToPcm function to return the fixture data directly,
    removing any dependency on FFmpeg.
    """
    pcm_data, sr, _ = soft_isch_aaa
    mp3_path = os.path.join(tempfile.mkdtemp(), "test_input.mp3")

    # Create an empty dummy file so os.path.exists passes if your code checks it
    with open(mp3_path, "wb") as f:
        f.write(b"")

    # Mock your conversion module function.
    # REPLACE 'your_module_path' with the actual import path of your convertMp3ToPcm function
    # (e.g., 'signal_processing.AudioFeatureExtractor.convertMp3ToPcm')
    mocker.patch(
        'signal_processing.AudioFeatureExtractor.convertMp3ToPcm',
        return_value=(pcm_data, sr)
    )

    return mp3_path


def test_metadata(analyzer, soft_isch_aaa):
    """
    Check that the audio length and sample ratio is returned.
    :param analyzer:
    :return:
    """
    pcm_data, sr, duration = soft_isch_aaa
    features = analyzer.analyzePCM(pcm_data, sr)
    assert features.sample_rate == sr
    assert features.length_seconds == pytest.approx(duration)


def basic_parameters(analyzer, soft_isch_aaa):
    """
    Check that pitch, F1, F2, F3 and loudness is correctly analysed.
    :param analyzer:
    :return:
    """
    # 2. Act
    pcm_data, sr, duration = soft_isch_aaa
    features = analyzer.analyzePCM(pcm_data, sr)

    # Extract the underlying data arrays from your custom TimeSeries objects
    # (Replace '.values' or '.data' with whatever your SignalTimeSeries uses internally)
    pitch_array = features.pitch.y
    f1_array = features.F1.y
    f2_array = features.F2.y
    f3_array = features.F3.y

    # Filter out unvoiced/zero frames if your pipeline sets unvoiced to 0 or NaN
    valid_pitch = pitch_array[pitch_array > 0]

    # Verify Core Pitch tracks the dominant fundamental frequency (150 Hz)
    assert len(valid_pitch) > 0, "No pitch frames detected."
    assert np.mean(valid_pitch) == pytest.approx(223.0, abs=5.0)

    # Verify Formants track your higher injected frequencies
    # Adjust tolerances (abs) based on openSMILE's LPC/formant tracker quirks
    assert np.mean(f1_array[f1_array > 0]) == pytest.approx(850.0, abs=100)
    assert np.mean(f2_array[f2_array > 0]) == pytest.approx(1600.0, abs=100.0)
    assert np.mean(f3_array[f3_array > 0]) == pytest.approx(3000.0, abs=100.0)

    # 1. Pitch Bandwidth
    pitch_bw_array = features.Pitch_BW.y
    assert len(pitch_bw_array) > 0, "Pitch bandwidth array is empty."
    assert not np.isnan(pitch_bw_array).all(), "Pitch bandwidth contains only NaNs."

    # 2. Formant Initial Bandwidths (IBW)
    f1_ibw_array = features.F1_IBW.y
    f2_ibw_array = features.F2_IBW.y
    f3_ibw_array = features.F3_IBW.y

    # Bandwidths should be positive, non-empty values
    assert np.mean(f1_ibw_array[f1_ibw_array > 0]) > 0
    assert np.mean(f2_ibw_array[f2_ibw_array > 0]) > 0
    assert np.mean(f3_ibw_array[f3_ibw_array > 0]) > 0

    # 3. Loudness
    loudness_array = features.loudness.y
    assert len(loudness_array) > 0, "Loudness array is empty."
    # Ensure loudness reflects a signal is playing (greater than zero/silence floor)
    assert np.mean(loudness_array) > 0.01

def test_derived_properties(analyzer, soft_isch_aaa):
    """
    Test that formant ratios and weight is analyzed
    :param analyzer:
    :return:
    """
    # 1. Arrange & Act
    pcm_data, sr, duration = soft_isch_aaa
    features = analyzer.analyzePCM(pcm_data, sr)

    # 2. Extract Derived Pitch-Relative Formant arrays
    f1_pitch_array = features.F1_Pitch.y
    f2_pitch_array = features.F2_Pitch.y
    f3_pitch_array = features.F3_Pitch.y

    # Assuming Fx_Pitch is a direct harmonic ratio relative to F0 (e.g., Formant / Pitch)
    # Expected ratios based on your basic parameters:
    # F1/F0 = 850/223 ≈ 3.81 | F2/F0 = 1600/223 ≈ 7.17 | F3/F0 = 3000/223 ≈ 13.45
    expected_f1_ratio = 850.0 / 223.0
    expected_f2_ratio = 1600.0 / 223.0
    expected_f3_ratio = 3000.0 / 223.0

    assert np.mean(f1_pitch_array[f1_pitch_array > 0]) == pytest.approx(expected_f1_ratio, abs=1.0)
    assert np.mean(f2_pitch_array[f2_pitch_array > 0]) == pytest.approx(expected_f2_ratio, abs=1.5)
    assert np.mean(f3_pitch_array[f3_pitch_array > 0]) == pytest.approx(expected_f3_ratio, abs=2.0)

    # 3. Extract Pitch-Relative Formant Bandwidths (BW)
    f1_pitch_bw = features.F1_Pitch_BW.y
    f2_pitch_bw = features.F2_Pitch_BW.y
    f3_pitch_bw = features.F3_Pitch_BW.y

    assert len(f1_pitch_bw) > 0 and not np.isnan(f1_pitch_bw).all()
    assert len(f2_pitch_bw) > 0 and not np.isnan(f2_pitch_bw).all()
    assert len(f3_pitch_bw) > 0 and not np.isnan(f3_pitch_bw).all()

    weight_array = features.weight.y
    assert len(weight_array) > 0, "Weight array was not populated."
    assert np.isfinite(weight_array).all()

def test_analyze_wav_file(analyzer, wav_file_path):
    """Verify analyzeFile correctly opens and processes a WAV file."""
    features = analyzer.analyzeFile(wav_file_path)

    pitch_array = features.pitch.y
    valid_pitch = pitch_array[pitch_array > 0]

    assert len(valid_pitch) > 0, "No pitch frames detected from WAV file."
    assert np.mean(valid_pitch) == pytest.approx(223.0, abs=5.0)

def test_analyze_mp3_file(analyzer, mp3_file_path):
    """Verify analyzeFile correctly routes, mocks, and processes an MP3 file footprint."""
    features = analyzer.analyzeFile(mp3_file_path)

    pitch_array = features.pitch.y
    valid_pitch = pitch_array[pitch_array > 0]

    assert len(valid_pitch) > 0, "No pitch frames detected from mocked MP3 processing."

    # Since it's using the clean fixture data directly via the mock,
    # we can use the strict WAV tolerance here!
    assert np.mean(valid_pitch) == pytest.approx(223.0, abs=5.0)

def test_analyze_unknown_extension(analyzer, tmp_path):
    """Ensure unsupported extensions safely return default initialized features."""
    invalid_path = os.path.join(tmp_path, "invalid_file.txt")
    with open(invalid_path, "w") as f:
        f.write("Not an audio file")

    features = analyzer.analyzeFile(invalid_path)

    assert features.sample_rate == 0.0
    assert features.length_seconds == 0.0