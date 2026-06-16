import time
from dataclasses import dataclass

import opensmile
import miniaudio
import numpy as np
import wave

from scipy.signal import stft

from PlotsSpec import outliers_m
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, BandwidthTimeSeries
from signal_processing.TargetConfig import TargetConfig


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

    def __init__(self, targets: TargetConfig):
        self.smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
        )
        self.target_config = targets
        self.cachedResults = None

    def analyzePCM(self, pcm_data, sampling_rate) -> AudioFeatures:
        df = self.smile.process_signal(pcm_data, sampling_rate)
        audio_length = len(pcm_data) / float(sampling_rate)
        return self.extractFeatures(df, sampling_rate, audio_length, pcm_data)

    def convertMp3ToPcm(self, mp3_path):
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

        # 3. Normalize to floating-point values between -1.0 and 1.0
        # openSMILE expects standard normalized float32/64 audio signals
        signal = pcm_data.astype(np.float32) / 32768.0
        return signal, sampling_rate

    def analyzeFile(self, path) -> AudioFeatures:
        if (path.endswith('.wav')):
            samples, sampling_rate, audio_length = load_pcm_from_wave(path)
            
            # Peak amplitude normalization
            max_val = np.max(np.abs(samples))
            if max_val > 0:
                samples = samples / max_val

            start_time = time.perf_counter()
            df = self.smile.process_signal(samples, sampling_rate)
            elapsed_time = time.perf_counter() - start_time
            # print(f"Opensmile analysis time: {elapsed_time:.4f} seconds.")

            return self.extractFeatures(df, sampling_rate, audio_length, samples)

        elif (path.endswith('.mp3')):

            start_time = time.perf_counter()
            pcm_data, sampling_rate = self.convertMp3ToPcm(path)
            elapsed_time = time.perf_counter() - start_time
            # print(f"MP3 convertion time: {elapsed_time:.4f} seconds.")

            # Peak amplitude normalization
            max_val = np.max(np.abs(pcm_data))
            if max_val > 0:
                pcm_data = pcm_data / max_val

            start_time = time.perf_counter()
            df = self.smile.process_signal(pcm_data, sampling_rate)
            elapsed_time = time.perf_counter() - start_time
            # print(f"Opensmile analysis time: {elapsed_time:.4f} seconds.")

            audio_length = len(pcm_data) / float(sampling_rate)
            return self.extractFeatures(df, sampling_rate, audio_length, pcm_data)
        else:
            print("Unknown file extension")
            return AudioFeatures()

    def extractFeatures(self, df, sampling_rate, audio_length, pcm_data) -> AudioFeatures:
        start_time = time.perf_counter()

        # 1. Vectorized calculations directly on the DataFrame
        timepoints = df.index.get_level_values('start').total_seconds().to_numpy()

        # Calculate pitch using vectorized numpy math
        semitones = df['F0semitoneFrom27.5Hz_sma3nz'].to_numpy()
        pitch = 27.5 * (2 ** (semitones / 12))

        # Extract formants and features as fast NumPy arrays
        f1 = df['F1frequency_sma3nz'].to_numpy()
        f2 = df['F2frequency_sma3nz'].to_numpy()
        f3 = df['F3frequency_sma3nz'].to_numpy()
        loudness_raw = df['Loudness_sma3'].to_numpy()

        # Determine a floor threshold (e.g., dropping the quietest 10% of frames)
        # Since your range is -1 to 1, quiet frames will sit near -1.
        loudness_floor = -0.8

        # Vectorized Filtering
        valid_mask = (pitch > 27.5) & (f1 > 0) & (loudness_raw > loudness_floor)
        t_filtered = timepoints[valid_mask]

        # 3. Construct the result dictionary using filtered arrays
        result = AudioFeatures(
            pitch=SignalTimeSeries(x=t_filtered, y=pitch[valid_mask]),
            F1=SignalTimeSeries(x=t_filtered, y=f1[valid_mask]),
            F2=SignalTimeSeries(x=t_filtered, y=f2[valid_mask]),
            F3=SignalTimeSeries(x=t_filtered, y=f3[valid_mask]),

            F2_F1=SignalTimeSeries(x=t_filtered, y=f2[valid_mask] / f1[valid_mask]),
            F3_F1=SignalTimeSeries(x=t_filtered, y=f3[valid_mask] / f1[valid_mask]),

            loudness=SignalTimeSeries(x=t_filtered, y=loudness_raw[valid_mask]),

            sample_rate=sampling_rate,
            length_seconds=audio_length
        )

        # Calculate and assign spectral slopes
        t_slopes, slopes = calculate_spectral_slope(pcm_data, sampling_rate, nperseg=2048, noverlap=1024)
        result.slopes = SignalTimeSeries(x=t_slopes, y=slopes)

        if len(t_filtered) > 0:
            # 4. Handle Outliers (Note: reject_outliers should now accept/return SignalTimeSeries)
            # result.pitch = reject_outliers(result.pitch)

            # 5. Vectorized Min-Max Normalization for Loudness
            l_arr = result.loudness.y
            l_min, l_max = l_arr.min(), l_arr.max()
            if l_max != l_min:
                result.loudness.y = (l_arr - l_min) / (l_max - l_min)

            elapsed_time = time.perf_counter() - start_time
            # print(f"Post opensmile analysis time: {elapsed_time:.4f} seconds.")

            # Compute IBW for the formant ratios
            window_size_samples = 50
            step_size_samples = 1

            start_time_bw = time.perf_counter()

            # Note: If calculate_bw_and_cf returns a dict like {"x":..., "y":..., "BW":...},
            # unpack it into the dataclass fields as shown below.


            bw_pitch = calculate_bw_and_cf(
                result.pitch.x, result.pitch.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.Pitch_BW = BandwidthTimeSeries(x=bw_pitch["x"], y=bw_pitch["y"], BW=bw_pitch["BW"])

            bw_f2_f1 = calculate_bw_and_cf(
                result.F2_F1.x, result.F2_F1.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F2_F1_IBW = BandwidthTimeSeries(x=bw_f2_f1["x"], y=bw_f2_f1["y"], BW=bw_f2_f1["BW"])

            bw_f3_f1 = calculate_bw_and_cf(
                result.F3_F1.x, result.F3_F1.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F3_F1_IBW = BandwidthTimeSeries(x=bw_f3_f1["x"], y=bw_f3_f1["y"], BW=bw_f3_f1["BW"])

            bw_f1 = calculate_bw_and_cf(
                result.F1.x, result.F1.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F1_IBW = BandwidthTimeSeries(x=bw_f1["x"], y=bw_f1["y"], BW=bw_f1["BW"])

            bw_f2 = calculate_bw_and_cf(
                result.F2.x, result.F2.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F2_IBW = BandwidthTimeSeries(x=bw_f2["x"], y=bw_f2["y"], BW=bw_f2["BW"])

            bw_f3 = calculate_bw_and_cf(
                result.F3.x, result.F3.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F3_IBW = BandwidthTimeSeries(x=bw_f3["x"], y=bw_f3["y"], BW=bw_f3["BW"])

            # Formant / Pitch Ratios
            result.F1_Pitch = SignalTimeSeries(x=t_filtered, y=f1[valid_mask] / pitch[valid_mask])
            bw_f1_pitch = calculate_bw_and_cf(
                result.F1_Pitch.x, result.F1_Pitch.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F1_Pitch_BW = BandwidthTimeSeries(x=bw_f1_pitch["x"], y=bw_f1_pitch["y"], BW=bw_f1_pitch["BW"])

            result.F2_Pitch = SignalTimeSeries(x=t_filtered, y=f2[valid_mask] / pitch[valid_mask])
            bw_f2_pitch = calculate_bw_and_cf(
                result.F2_Pitch.x, result.F2_Pitch.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F2_Pitch_BW = BandwidthTimeSeries(x=bw_f2_pitch["x"], y=bw_f2_pitch["y"], BW=bw_f2_pitch["BW"])

            result.F3_Pitch = SignalTimeSeries(x=t_filtered, y=f3[valid_mask] / pitch[valid_mask])
            bw_f3_pitch = calculate_bw_and_cf(
                result.F3_Pitch.x, result.F3_Pitch.y, result.loudness.y,
                window_size=window_size_samples, step_size=step_size_samples
            )
            result.F3_Pitch_BW = BandwidthTimeSeries(x=bw_f3_pitch["x"], y=bw_f3_pitch["y"], BW=bw_f3_pitch["BW"])

            elapsed_time_bw = time.perf_counter() - start_time_bw
            # print(f"BW and CF: {elapsed_time_bw:.4f} seconds.")

            self.cachedResults = result
            self.recalculate_size()

        else:
            print("Silent/unvoiced frame skipped safely.")
            elapsed_time_bw = 0

        return result

    def recalculate_size(self):
        if self.cachedResults is None:
            return None

        print([
            self.target_config.f1_pitch_min, self.target_config.f1_pitch_max,
            self.target_config.f2_pitch_min, self.target_config.f2_pitch_max,
            self.target_config.f3_pitch_min, self.target_config.f3_pitch_max
        ])

        f1_min = self.target_config.f1_pitch_min
        f1_max = self.target_config.f1_pitch_max
        f2_min = self.target_config.f2_pitch_min
        f2_max = self.target_config.f2_pitch_max
        f3_min = self.target_config.f3_pitch_min
        f3_max = self.target_config.f3_pitch_max

        size_y = calculate_size(self.cachedResults.F1_Pitch_BW.y,
                                self.cachedResults.F2_Pitch_BW.y,
                                self.cachedResults.F3_Pitch_BW.y,
                                f1_min,
                                f1_max,
                                f2_min,
                                f2_max,
                                f3_min,
                                f3_max)
        self.cachedResults.size = SignalTimeSeries(x=self.cachedResults.F1_Pitch_BW.x, y=size_y)
        return self.cachedResults

def calculate_bw_and_cf(x_time, y_freq, y_mag, window_size=500, step_size=100):
    """Performs a sliding window analysis over 1D spectral arrays to compute

    the center frequency and RMS bandwidth over time.
    """
    out_times = []
    out_center_freqs = []
    out_bandwidths = []

    num_elements = len(y_mag)

    # Slide across the array indices
    for start_idx in range(0, num_elements - window_size + 1, step_size):
        end_idx = start_idx + window_size

        # CRITICAL FIX: Slice ALL arrays using the exact same indices
        # This guarantees window_freqs and window_mags have identical shapes (e.g., shape: (200,))
        window_freqs = y_freq[start_idx:end_idx]
        window_mags = y_mag[start_idx:end_idx]

        # Calculate the time point corresponding to the center of this window
        mid_idx = start_idx + (window_size // 2)
        current_time = x_time[mid_idx]

        # --- Core Calculations with -20dB Filter ---
        power = window_mags ** 2
        peak_power = np.max(power)
        threshold = 0.01 * peak_power  # -20dB filter

        # Clean the noise, keeping the exact same array shape
        clean_power = np.where(power >= threshold, power, 0.0)
        total_power = np.sum(clean_power)

        if total_power == 0:
            continue

        # Element-wise operations (Safe now because shapes are identical)
        center_freq = np.sum(window_freqs * clean_power) / total_power

        freq_deviations_squared = (window_freqs - center_freq) ** 2
        variance = np.sum(freq_deviations_squared * clean_power) / total_power
        rms_bandwidth = np.sqrt(variance)

        # Save calculations
        out_times.append(current_time)
        out_center_freqs.append(center_freq)
        out_bandwidths.append(rms_bandwidth)

    return {
        "x": out_times,
        "y": out_center_freqs,
        "BW": out_bandwidths,
    }


def reject_outliers(pair: SignalTimeSeries, m: float = outliers_m) -> SignalTimeSeries:
    # 1. Calculate absolute deviation from the median
    y_data = pair.y
    d = np.abs(y_data - np.median(y_data))
    mdev = np.median(d)

    # 2. Calculate scaled deviation score
    s = d / mdev if mdev else np.zeros(len(d))

    # 3. Create a vectorized boolean mask for points below the threshold
    valid_mask = s < m

    # 4. Return a brand new SignalTimeSeries using fast NumPy indexing
    return SignalTimeSeries(
        x=pair.x[valid_mask],
        y=y_data[valid_mask]
    )


def calculate_spectral_slope(audio_data, sample_rate, nperseg=1024, noverlap=512, silence_threshold_db=-30):
    """
    Calculates the spectral slope of an audio signal over time, filtering out silent frames.
    """
    # 1. Compute the Short-Time Fourier Transform
    f, t, Zxx = stft(audio_data, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)

    # Use the magnitude spectrum
    mag_spectrum = np.abs(Zxx)

    # 2. Filter out silence based on frame energy
    # Calculate the power of each frame (sum of squared magnitudes)
    frame_power = np.sum(mag_spectrum ** 2, axis=0)

    # Avoid log of zero issues by applying a tiny floor value
    frame_power = np.maximum(frame_power, 1e-20)

    # Convert power to decibels (dB)
    frame_power_db = 10 * np.log10(frame_power)

    # Determine the absolute threshold relative to the loudest frame
    max_power_db = np.max(frame_power_db)
    threshold = max_power_db + silence_threshold_db

    # Create a boolean mask of frames that are above the silence threshold
    active_frames = frame_power_db > threshold

    # Apply the mask to filter out silent frames from the time array and magnitude spectrum
    t = t[active_frames]
    mag_spectrum = mag_spectrum[:, active_frames]

    # Guard clause: if the entire audio is silent, return empty arrays
    if mag_spectrum.shape[1] == 0:
        return np.array([]), np.array([])

    # 3. Calculate the spectral slope for each frame using vectorized linear regression
    # f shape: (F,)
    # mag_spectrum shape: (F, T) where F is freq bins, T is remaining active time frames

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
        # 1. Extract audio metadata
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

        # 5. Optional: Normalize to floating point (-1.0 to 1.0)
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

def calculate_size(
        F1,
        F2,
        F3,
        f1_min,
        f1_max,
        f2_min,
        f2_max,
        f3_min,
        f3_max):
    """
    Calculates the Signed RMS Error time series for three features
    based on their respective min/max target boundaries.
    """
    f1_target = (f1_max + f1_min) / 2
    f2_target = (f2_max + f2_min) / 2
    f3_target = (f3_max + f3_min) / 2
    # 1. Calculate signed error vectors (Actual - Target)
    err_F1 = calculate_target_error(F1, f1_target)
    err_F2 = calculate_target_error(F2, f2_target)
    err_F3 = calculate_target_error(F3, f3_target)

    # 2. Stack them into a 2D array of shape (3, time_steps)
    stacked_errors = np.vstack([err_F1, err_F2, err_F3])

    # 3. Calculate standard RMS magnitude (always positive)
    rms_magnitude = np.sqrt(np.mean(stacked_errors ** 2, axis=0))

    # 4. Extract the net direction of the errors at each timestamp
    net_direction = np.sign(np.sum(stacked_errors, axis=0))

    # 5. Combine magnitude and direction
    signed_rms_time_series = net_direction * rms_magnitude

    return signed_rms_time_series


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