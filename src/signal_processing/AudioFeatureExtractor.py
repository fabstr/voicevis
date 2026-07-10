import logging
import time

import opensmile
import miniaudio
import numpy as np
import pandas as pd
import wave

from scipy.signal import stft, spectrogram

from ResourceManager import ResourceManager
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, SpectrogramData
from signal_processing.TargetConfig import TargetConfig

nperseg = 2048
noverlap = 1536

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

    def analyzePCM(self, pcm_data, sampling_rate) -> AudioFeatures:
        """
        Perform analysis on samples.

        :param pcm_data:
        :param sampling_rate:
        :return:
        """
        df = self.smile.process_signal(pcm_data, sampling_rate)
        audio_length = len(pcm_data) / float(sampling_rate)
        return self.extractFeatures(df, sampling_rate, audio_length, pcm_data)

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

    def extractFeatures(self, df, sampling_rate, audio_length, pcm_data) -> AudioFeatures:
        # Extract timepoints
        timepoints = df.index.get_level_values('start').total_seconds().to_numpy()

        # Calculate pitch by converting semitones to frequencies
        semitones = df['F0semitoneFrom27.5Hz_sma3nz'].to_numpy()
        pitch = 27.5 * (2 ** (semitones / 12))

        # Extract formants
        f1 = df['F1frequency_sma3nz'].to_numpy()
        f2 = df['F2frequency_sma3nz'].to_numpy()
        f3 = df['F3frequency_sma3nz'].to_numpy()

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
            jitter=SignalTimeSeries(x=timepoints, y=jitter_clean),
            shimmer=SignalTimeSeries(x=timepoints, y=shimmer_clean),
            weight_instantaneous=calculate_weight(timepoints, h1_h2_clean, h1_h3_clean, h1_h4_clean),
            size=calculate_size(timepoints, f1_pitch_clean, f2_pitch_clean, f3_pitch_clean, self.target_config),
            spectrogram=calculate_spectrogram(pcm_data, sampling_rate),
            slopes=calculate_slopes(pcm_data, sampling_rate, timepoints),

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


        return result

def calculate_size(t, F1_Pitch, F2_Pitch, F3_Pitch, target_config) -> SignalTimeSeries:
    if target_config is None or len(t) == 0:
        return SignalTimeSeries()

    if not target_config.has_all_bounds(["f1_pitch", "f2_pitch", "f3_pitch"]):
        logging.error("No target defined for F1, F2 or F3. Size cannot be calculated.")
        return SignalTimeSeries()

    # Calculate signed error vectors (Actual - Target)
    err_F1 = calculate_target_error(F1_Pitch, target_config.get_mean("f1_pitch"))
    err_F2 = calculate_target_error(F2_Pitch, target_config.get_mean("f2_pitch"))
    err_F3 = calculate_target_error(F3_Pitch, target_config.get_mean("f3_pitch"))

    size_y = signed_rms([err_F1, err_F2, err_F3])

    return SignalTimeSeries(x=t, y=size_y)

def calculate_spectral_slope(audio_data, sample_rate, nperseg=1024, noverlap=512):
    """
    Calculates the spectral slope of an audio signal over time.
    Silence filtering is delegated to the master valid_mask in the extractor
    to prevent misaligned timeframes.
    """
    # 1. Compute the Short-Time Fourier Transform
    f, t, Zxx = stft(audio_data, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)

    # Use the magnitude spectrum
    mag_spectrum = np.abs(Zxx)

    # Guard clause: if the entire audio is empty, return empty arrays
    if mag_spectrum.shape[1] == 0:
        return np.array([]), np.array([])

    f_mean = np.mean(f)
    mag_mean = np.mean(mag_spectrum, axis=0)  # Mean across frequencies for each frame

    # Calculate covariance and variance
    f_diff = f - f_mean  # shape: (F,)
    mag_diff = mag_spectrum - mag_mean  # shape: (F, T)

    # Numerator: Sum of (x - x_mean) * (y - y_mean)
    # Denominator: Sum of (x - x_mean)^2
    numerator = np.sum(f_diff[:, None] * mag_diff, axis=0)
    denominator = np.sum(f_diff ** 2)

    # Slope (m) = Numerator / Denominator
    slopes = numerator / denominator
    slopes = np.negative(slopes)

    return t, slopes


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


def calculate_range(y, window_size):
    def trailing_window():
        # Pad the start of the file with the mean of the first window_size (e.g. 5 s)
        first_5s = y[:window_size]

        # Handle the edge case where the first 5 seconds is entirely silence/NaN
        if np.isnan(first_5s).all():
            first_5s_mean = 0  # Fallback value
        else:
            first_5s_mean = np.nanmean(first_5s)

        padded_y = np.pad(y, pad_width=(window_size - 1, 0), mode='constant', constant_values=first_5s_mean)

        def robust_ptp(x):
            if np.isnan(x).all():
                return np.nan  # If the whole 5s window is silent, the range is NaN

            # Calculate the distance between the 95th and 5th percentiles.
            # This inherently ignores extreme isolated spikes.
            return np.nanpercentile(x, 95) - np.nanpercentile(x, 5)

        # 3. Compute the rolling range using the robust percentile function
        rolling_range_series = pd.Series(padded_y).rolling(window=window_size, min_periods=1).apply(robust_ptp, raw=True)

        # Clean up created NaNs and convert back to numpy
        range_array = rolling_range_series.to_numpy()[window_size - 1:]
        return range_array

    def centered_window():
        def robust_ptp(x):
            if np.isnan(x).all():
                return np.nan
            return np.nanpercentile(x, 95) - np.nanpercentile(x, 5)

        # center=True eliminates the phase delay.
        # min_periods=1 handles the edges automatically (it looks forward at the start).
        rolling_range = pd.Series(y).rolling(
            window=window_size,
            center=True,
            min_periods=1
        ).apply(robust_ptp, raw=True)
        return rolling_range

    return centered_window()


def calculate_weight(t, H1_H2, H1_H3, H1_H4):
    weight = signed_rms([
        H1_H2,
        H1_H3,
        H1_H4
    ])

    return SignalTimeSeries(x=t, y=weight)


def signed_rms(array: np.ndarray) -> np.ndarray:
    # Stack them into a 2D array of shape (n, time_steps)
    stacked_errors = np.vstack(array)

    # Calculate standard RMS magnitude (always positive)
    # and extract the net direction of the errors at each timestamp
    rms_magnitude = np.sqrt(np.mean(stacked_errors ** 2, axis=0))
    net_direction = np.sign(np.sum(stacked_errors, axis=0))
    return net_direction * rms_magnitude

def calculate_slopes(samples, sampling_rate, timepoints) -> SignalTimeSeries:
    t_slopes, slopes = calculate_spectral_slope(samples, sampling_rate, nperseg=2048, noverlap=1024)

    #  Interpolate slopes to match the filtered timepoints
    if len(t_slopes) > 0 and len(timepoints) > 0:
        matched_slopes = np.interp(timepoints, t_slopes, slopes)
    else:
        matched_slopes = np.zeros_like(timepoints)

    return SignalTimeSeries(x=timepoints, y=matched_slopes)

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