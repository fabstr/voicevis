import logging

import librosa
import opensmile
import miniaudio
import numpy as np
import pandas as pd
import wave

from scipy.signal import spectrogram

from ResourceManager import ResourceManager
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, SpectrogramData
from signal_processing.TargetConfig import TargetConfig
from signal_processing.Weight import calculate_weight

from time import perf_counter

class AudioFeatureExtractor:

    #### Available features:
    #     Loudness_sma3
    #     alphaRatio_sma3
    #     hammarbergIndex_sma3
    #     slope0-500_sma3
    #     slope500-1500_sma3
    #     spectralFlux_sma3
    #     mfcc1_sma3
    #     mfcc2_sma3
    #     mfcc3_sma3
    #     mfcc4_sma3
    #     F0semitoneFrom27.5Hz_sma3nz
    #     jitterLocal_sma3nz
    #     shimmerLocaldB_sma3nz
    #     HNRdBACF_sma3nz
    #     logRelF0-H1-H2_sma3nz
    #     logRelF0-H1-H3_sma3nz
    #     logRelF0-H1-H4_sma3nz
    #     logRelF0-H1-A3_sma3nz
    #     F1frequency_sma3nz
    #     F1bandwidth_sma3nz
    #     F1amplitudeLogRelF0_sma3nz
    #     F2frequency_sma3nz
    #     F2bandwidth_sma3nz
    #     F2amplitudeLogRelF0_sma3nz
    #     F3frequency_sma3nz
    #     F3bandwidth_sma3nz
    #     F3amplitudeLogRelF0_sma3nz

    def __init__(self, targets: TargetConfig = TargetConfig(), resource_manager: ResourceManager = ResourceManager()):
        """
        Constructor for AudioFeatureExtractor.

        A custom configuration has been defined for Opensmile to compute more harmonics.

        :param targets: The default target config to use when analysis requires targets to compare against.
        """
        self.smile = opensmile.Smile(
            feature_set=resource_manager.get_absolute_path('smile_configs/egemaps/v02/eGeMAPSv02.conf'),
            feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
        )
        self.target_config = targets


        # warmup librosa
        dummy_frame = np.zeros(1024, dtype=np.float32)
        dummy_order = 2 + int(44100 / 1000)

        # Force Numba to compile the function silently during startup
        try:
            _ = librosa.lpc(dummy_frame, order=dummy_order)
        except Exception:
            pass

    def analyzePCM(self, pcm_data, sampling_rate) -> AudioFeatures:
        """
        Perform analysis on samples.

        :param pcm_data:
        :param sampling_rate:
        :return:
        """
        df = self.smile.process_signal(pcm_data, sampling_rate)
        audio_length = len(pcm_data) / float(sampling_rate)
        result = self.extractFeatures(df, sampling_rate, audio_length, pcm_data)
        return result

    def analyzeChunk(self, pcm_data, sampling_rate) -> AudioFeatures:
        """Analyse one chunk of a longer recording.

        The rolling means are left out: their window spans several seconds, so a
        chunk on its own would get the frames near its edges wrong. The caller
        stitches the chunks together and applies :func:`apply_derived_features`
        to the whole timeline instead. See
        :class:`signal_processing.ChunkedAnalysis.ChunkedAudioAnalysis`.
        """
        df = self.smile.process_signal(pcm_data, sampling_rate)
        audio_length = len(pcm_data) / float(sampling_rate)
        return self.extractFeatures(df, sampling_rate, audio_length, pcm_data,
                                    derive=False)

    def analyzeFile(self, path) -> AudioFeatures:
        """
        Analyse a complete audio file, wav and mp3 files are supported.

        :param path: The wav/mp3 file to analyse.
        :return:
        """
        if path.endswith('.wav'):
            samples, sampling_rate, audio_length = load_pcm_from_wave(path)
            df = self.smile.process_signal(samples, sampling_rate)
            return self.extractFeatures(df, sampling_rate, audio_length, samples)

        elif path.endswith('.mp3'):
            samples, sampling_rate = convertMp3ToPcm(path)
            audio_length = len(samples) / float(sampling_rate)
        else:
            logging.error("Unknown file extension")
            return AudioFeatures()

        # Peak amplitude normalization
        max_val = np.max(np.abs(samples))
        if max_val > 0:
            samples = samples / max_val

        df = self.smile.process_signal(samples, sampling_rate)
        return self.extractFeatures(df, sampling_rate, audio_length, samples)

    def extractFeatures(self, df, sampling_rate, audio_length, pcm_data,
                        derive=True) -> AudioFeatures:
        # Extract timepoints
        timepoints = df.index.get_level_values('start').total_seconds().to_numpy()

        # Calculate pitch by converting semitones to frequencies
        semitones = df['F0semitoneFrom27.5Hz_sma3nz'].to_numpy()
        pitch = 27.5 * (2 ** (semitones / 12))

        # Extract formants
        f1 = df['F1frequency_sma3nz'].to_numpy()
        f2 = df['F2frequency_sma3nz'].to_numpy()
        f3 = df['F3frequency_sma3nz'].to_numpy()
        f1_amp = df['F1amplitudeLogRelF0_sma3nz'].to_numpy()
        f2_amp = df['F2amplitudeLogRelF0_sma3nz'].to_numpy()
        f3_amp = df['F3amplitudeLogRelF0_sma3nz'].to_numpy()

        # Extract loudness
        loudness = df['Loudness_sma3'].to_numpy()

        # Define a filter to remove rubbish data points, we want to skip obviously incorrect pitches and too quite areas
        valid_mask = (pitch > 65) & \
                     (pitch < 500) \
                     & (f1 > 0) \
                     & (loudness > -0.8)

        pitch_clean = np.where(valid_mask, pitch, np.nan)
        loudness_clean = np.where(valid_mask, loudness, np.nan)
        jitter_clean = np.where(valid_mask, df['jitterLocal_sma3nz'].to_numpy(), np.nan)
        shimmer_clean = np.where(valid_mask, df['shimmerLocaldB_sma3nz'].to_numpy(), np.nan)

        f1_clean = np.where(valid_mask, f1, np.nan)
        f2_clean = np.where(valid_mask, f2, np.nan)
        f3_clean = np.where(valid_mask, f3, np.nan)

        # Do the same for your H1_H2, H1_H3, etc.
        h1_h2_clean = remove_local_outliers_robust(np.where(valid_mask, df['logRelF0-H1-H2_sma3nz'].to_numpy(), np.nan))
        h1_h3_clean = remove_local_outliers_robust(np.where(valid_mask, df['logRelF0-H1-H3_sma3nz'].to_numpy(), np.nan))
        h1_h4_clean = remove_local_outliers_robust(np.where(valid_mask, df['logRelF0-H1-H4_sma3nz'].to_numpy(), np.nan))
        h1_a3_clean = remove_local_outliers_robust(np.where(valid_mask, df['logRelF0-H1-A3_sma3nz'].to_numpy(), np.nan))

        # It is assumed that this data don't need cleaning again
        f1_pitch_clean = f1_clean / pitch_clean
        f2_pitch_clean = f2_clean / pitch_clean
        f3_pitch_clean = f3_clean / pitch_clean

        # 3. Construct the result dictionary using filtered arrays
        result = AudioFeatures(
            sample_rate=sampling_rate,
            length_seconds=audio_length,

            pitch=SignalTimeSeries(x=timepoints, y=pitch_clean),
            loudness=SignalTimeSeries(x=timepoints, y=loudness_clean),
            weight=calculate_weight(timepoints, h1_a3_clean, loudness_clean),
            jitter=SignalTimeSeries(x=timepoints, y=jitter_clean),
            shimmer=SignalTimeSeries(x=timepoints, y=shimmer_clean),
            size=calculate_size(timepoints, f1_pitch_clean, f2_pitch_clean, f3_pitch_clean, self.target_config),
            spectrogram=calculate_spectrogram(pcm_data, sampling_rate),

            F1=SignalTimeSeries(x=timepoints, y=f1_clean),
            F2=SignalTimeSeries(x=timepoints, y=f2_clean),
            F3=SignalTimeSeries(x=timepoints, y=f3_clean),

            F1_Pitch=SignalTimeSeries(x=timepoints, y=f1_pitch_clean),
            F2_Pitch=SignalTimeSeries(x=timepoints, y=f2_pitch_clean),
            F3_Pitch=SignalTimeSeries(x=timepoints, y=f3_pitch_clean),

            H1_H2=SignalTimeSeries(x=timepoints, y=h1_h2_clean),
            H1_H3=SignalTimeSeries(x=timepoints, y=h1_h3_clean),
            H1_H4=SignalTimeSeries(x=timepoints, y=h1_h4_clean),
            H1_A3=SignalTimeSeries(x=timepoints, y=h1_a3_clean),
        )

        if derive:
            apply_derived_features(result)

        return result


def apply_derived_features(features: AudioFeatures) -> AudioFeatures:
    """Fill in whatever depends on the whole timeline, in place.

    Split out of :meth:`AudioFeatureExtractor.extractFeatures` so that a chunked
    analysis can run it once over the assembled timeline, after the chunks are
    stitched together, rather than per chunk (which would get any windowed
    calculation wrong at the edges). Currently nothing needs it -- the rolling
    means this used to compute (pitch/size 5 s mean, weight 333 ms max) were
    removed along with the ``weight`` feature -- but the seam stays for the next
    whole-timeline feature that needs it.
    """
    return features


def calculate_size(t, F1_Pitch, F2_Pitch, F3_Pitch, target_config) -> SignalTimeSeries:
    # if target_config is None or len(t) == 0:
    #     return SignalTimeSeries()
    #
    # if not target_config.has_all_bounds(["f1_pitch", "f2_pitch", "f3_pitch"]):
    #     logging.error("No target defined for F1, F2 or F3. Size cannot be calculated.")
    #     return SignalTimeSeries()
    #
    # # Calculate signed error vectors (Actual - Target)
    # err_F1 = calculate_target_error(F1_Pitch, target_config.get_mean("f1_pitch"))
    # err_F2 = calculate_target_error(F2_Pitch, target_config.get_mean("f2_pitch"))
    # err_F3 = calculate_target_error(F3_Pitch, target_config.get_mean("f3_pitch"))
    #
    # size_y = signed_rms([err_F1, err_F2, err_F3])

    size_y = signed_rms([F1_Pitch, F2_Pitch, F3_Pitch])
    return SignalTimeSeries(x=t, y=size_y)

def load_pcm_from_wave(file_path):
    with wave.open(file_path, 'rb') as wav_file:
        # Extract audio metadata
        n_channels = wav_file.getnchannels()
        samp_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        n_frames = wav_file.getnframes()

        # Guard rail: Ensure it's mono as per your application setup
        if n_channels != 1:
            raise ValueError(f"Expected mono audio, but found {n_channels} channels.")

        # 2. Read the raw byte data from the file
        raw_bytes = wav_file.readframes(n_frames)

        # 3. Determine the correct NumPy data type based on sample width
        if samp_width == 1:
            dtype = np.uint8  # 8-bit WAV is typically unsigned
        elif samp_width == 2:
            dtype = np.int16  # 16-bit WAV is signed integer (most common)
        elif samp_width == 4:
            dtype = np.int32  # 32-bit WAV is signed integer
        else:
            raise ValueError(f"Unsupported sample width: {samp_width} bytes")

        # 4. Convert the buffer to a NumPy array
        audio_samples = np.frombuffer(raw_bytes, dtype=dtype)

        # 5. Optional: Normalise to floating point (-1.0 to 1.0)
        # This is highly recommended for spectral analysis / STFT
        if samp_width == 1:
            # Convert unsigned 8-bit (0 to 255) to (-1.0 to 1.0)
            audio_samples = (audio_samples.astype(np.float32) - 128) / 128.0
        else:
            # Convert signed 16-bit or 32-bit to (-1.0 to 1.0)
            max_val = float(np.iinfo(dtype).max)
            audio_samples = audio_samples.astype(np.float32) / max_val

        audio_length = n_frames / float(frame_rate)

        return audio_samples, frame_rate, audio_length


def calculate_target_error(vector, target):
    """
    Calculates the directional distance a vector deviates from its target value.
    Positive = over target, Negative = under target, 0 = exactly on target.

    Supports time-varying targets via NumPy array broadcasting.
    """
    # Ensure inputs are numpy arrays for reliable vector operations
    vector = np.asarray(vector)
    target = np.asarray(target)

    # Simple subtraction replaces np.clip
    return vector - target

def convertMp3ToPcm(mp3_path):
    # 1. Decode MP3 to raw PCM using miniaudio
    audio_file = miniaudio.decode_file(mp3_path)
    sampling_rate = audio_file.sample_rate
    num_channels = audio_file.nchannels

    # Convert raw memory buffer to a standard 16-bit integer array
    pcm_data = np.frombuffer(audio_file.samples, dtype=np.int16)

    # 2. Convert to Mono if Stereo
    # openSMILE speech features (like pitch/formants) expect a single channel
    if num_channels > 1:
        pcm_data = pcm_data.reshape(-1, num_channels)
        pcm_data = pcm_data.mean(axis=1)  # Average left and right channels

    # 3. Normalise to floating-point values between -1.0 and 1.0
    # openSMILE expects standard normalised float32/64 audio signals
    signal = pcm_data.astype(np.float32) / 32768.0
    return signal, sampling_rate


def remove_local_outliers_robust(data_array, window=50, threshold=3.0):
    """Replaces points with NaN using robust Median Absolute Deviation (MAD)."""
    series = pd.Series(data_array)

    # 1. Calculate local rolling median (immune to extreme outliers)
    rolling_median = series.rolling(window=window, center=True, min_periods=1).median()

    # 2. Calculate absolute deviations from the local median
    deviations = np.abs(series - rolling_median)

    # 3. Calculate the rolling MAD
    # (Multiplying by 1.4826 scales MAD to be equivalent to a standard deviation for a normal distribution)
    rolling_mad = deviations.rolling(window=window, center=True, min_periods=1).median() * 1.4826

    # 4. Prevent division by zero in perfectly flat/silent sections
    rolling_mad = rolling_mad.replace(0, np.nan)

    # 5. Calculate robust Z-score
    robust_z_scores = deviations / rolling_mad

    # 6. Keep original data where robust Z-score is below threshold, otherwise set to NaN
    # We use np.nan_to_num on the z-scores to handle any lingering NaNs from the division safely
    cleaned_series = np.where(np.nan_to_num(robust_z_scores, nan=0.0) < threshold, data_array, np.nan)

    return cleaned_series

def signed_rms(array: np.ndarray) -> np.ndarray:
    # Stack them into a 2D array of shape (n, time_steps)
    stacked_errors = np.vstack(array)

    # Calculate standard RMS magnitude (always positive)
    # and extract the net direction of the errors at each timestamp
    rms_magnitude = np.sqrt(np.mean(stacked_errors ** 2, axis=0))
    net_direction = np.sign(np.sum(stacked_errors, axis=0))
    return net_direction * rms_magnitude

def calculate_spectrogram(samples, sampling_rate):
    # 4. Change window to 'blackmanharris' or 'nuttall' for less spectral leakage
    f_spec, t_spec, Sxx = spectrogram(
        samples,
        fs=sampling_rate,
        window='blackmanharris',
        nperseg=4096,
        noverlap=3072,
        nfft=8192
    )

    # Convert magnitude to log scale (Decibels), strictly clipping to prevent log(0) errors
    Sxx_db = 10 * np.log10(np.clip(Sxx, 1e-10, None))

    return SpectrogramData(x=t_spec, y=f_spec, magnitude_db=Sxx_db)