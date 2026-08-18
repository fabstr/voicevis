import logging

import librosa
import opensmile
import miniaudio
import numpy as np
import pandas as pd
import wave

from scipy.signal import stft, spectrogram, lfilter
from scipy.ndimage import uniform_filter1d

from ResourceManager import ResourceManager
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, SpectrogramData
from signal_processing.TargetConfig import TargetConfig
from signal_processing.genderer import calculate_target_probabilities

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

        # 2. Compute the perceived heuristic profile using the new isolated method
        weight3, weight3_average = calculate_weight3(pcm_data, sampling_rate, pitch_clean, timepoints, pitch_clean)
        weight3_clean = np.where(valid_mask, weight3, np.nan)

        # 3. Construct the result dictionary using filtered arrays
        result = AudioFeatures(
            sample_rate=sampling_rate,
            length_seconds=audio_length,

            pitch=SignalTimeSeries(x=timepoints, y=pitch_clean),
            loudness=SignalTimeSeries(x=timepoints, y=loudness_clean),
            jitter=SignalTimeSeries(x=timepoints, y=jitter_clean),
            shimmer=SignalTimeSeries(x=timepoints, y=shimmer_clean),
            weight_instantaneous=SignalTimeSeries(x=timepoints, y=weight3_clean), #calculate_weight(timepoints, h1_h2_clean, h1_h3_clean, h1_h4_clean),
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

        if derive:
            apply_derived_features(result)

        # probabilities = calculate_target_probabilities(result.size_5s_mean, result.pitch_5s_mean, result.weight_333ms_max)
        # print(str(probabilities))

        return result


def apply_derived_features(features: AudioFeatures) -> AudioFeatures:
    """Fill in the rolling means, in place, from the series already extracted.

    Split out of :meth:`AudioFeatureExtractor.extractFeatures` so that a chunked
    analysis can run it once over the assembled timeline. The windows are
    hundreds of frames wide, so computing them per chunk would leave a seam at
    every boundary.
    """
    timepoints = np.asarray(features.pitch.x, dtype=float)
    if timepoints.size == 0:
        return features

    # Pitch is NaN exactly where the extractor rejected the frame, so it doubles
    # as the validity mask without having to be carried along separately.
    valid_mask = ~np.isnan(np.asarray(features.pitch.y, dtype=float))

    features.size_5s_mean = rolling_mean(timepoints, features.size, valid_mask)
    features.pitch_5s_mean = rolling_mean(timepoints, features.pitch, valid_mask)
    features.weight_333ms_max = rolling_mean(timepoints, features.weight_instantaneous,
                                             valid_mask)
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

def calculate_weight(t, H1_H2, H1_H3, H1_H4):
    weight = signed_rms([H1_H2, H1_H3, H1_H4])
    return SignalTimeSeries(x=t, y=weight)

def rolling_mean(t: np.ndarray, series: SignalTimeSeries, valid_mask, window=500):
    y = pd.Series(series.y).rolling(
        window=window, # 2 s
        center=True,
        min_periods=1
    ).mean()

    y = np.where(valid_mask, y, np.nan)

    return SignalTimeSeries(x=t, y=y)

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


def calculate_weight3(pcm_data, sampling_rate, pitch_clean, timepoints, f0_timeline) -> tuple[np.ndarray, float]:
    def compute_native_naq_timeline(pcm_data, sampling_rate, f0_timeline, timepoints) -> np.ndarray:
        """
        Natively isolates the glottal flow wave using frame-by-frame LPC
        inverse filtering and calculates the Normalized Amplitude Quotient.
        """
        naq_timeline = np.zeros_like(timepoints)
        window_duration = 0.050
        window_samples = int(window_duration * sampling_rate)
        lpc_order = 2 + int(sampling_rate / 1000)

        for i, tp in enumerate(timepoints):
            f0_val = f0_timeline[i]

            # ⚠️ Updated: Handle np.nan checks introduced by your valid_mask
            if np.isnan(f0_val) or f0_val <= 0:
                continue

            start_idx = max(0, int((tp - window_duration / 2) * sampling_rate))
            end_idx = min(len(pcm_data), start_idx + window_samples)
            audio_frame = pcm_data[start_idx:end_idx]

            if len(audio_frame) < lpc_order * 2:
                continue

            try:
                a_coefficients = librosa.lpc(audio_frame, order=lpc_order)
                glottal_derivative = lfilter(a_coefficients, [1.0], audio_frame)
                glottal_flow = lfilter([1.0], [1.0, -0.98], glottal_derivative)

                av_discrete = np.max(glottal_flow) - np.min(glottal_flow)
                dmin_discrete = np.abs(np.min(glottal_derivative))
                t0_samples = sampling_rate / f0_val

                if dmin_discrete > 1e-6:
                    naq_timeline[i] = av_discrete / (dmin_discrete * t0_samples)
            except Exception:
                continue

        return naq_timeline

    # 1. Generate the raw structural NAQ array
    naq_timeline = compute_native_naq_timeline(pcm_data, sampling_rate, pitch_clean, timepoints)

    eps = 1e-6

    # 1. Invert thickness: small NAQ profiles mean tight, sudden, heavy fold closures
    glottal_heaviness = 1.0 / (naq_timeline + eps)

    # 2. Min-max scale baseline variations to cleanly clip artifacts between 0.0 and 1.0
    glottal_heaviness_norm = np.clip((glottal_heaviness - 1.0) / 10.0, 0, 1)

    # 3. ⚠️ Updated: Clean NaNs from f0_timeline to prevent math scaling warnings
    f0_safe = np.nan_to_num(f0_timeline, nan=0.0)

    # Apply Pitch Interaction: Scales heavier configurations upward if pitch rises
    f0_factor = f0_safe / 150.0
    vocal_weight_timeline = glottal_heaviness_norm * f0_factor

    # 4. Suppress metric entirely during silence or unvoiced speech pauses
    vocal_weight_timeline[f0_safe == 0] = 0.0

    # 5. Extract strict average tracking exclusively from active voiced frames
    voiced_frames = vocal_weight_timeline[vocal_weight_timeline > 0]
    average_vocal_weight = float(np.mean(voiced_frames)) if len(voiced_frames) > 0 else 0.0

    return vocal_weight_timeline, average_vocal_weight

def calculate_weight4(path):
    def zff_gci(x, fs):
        """Zero-frequency filtering GCI detection (Murty & Yegnanarayana, 2008)."""
        diff = np.diff(x, prepend=x[0]).astype(float)
        y = lfilter([1], [1, -2, 1], diff)
        y = lfilter([1], [1, -2, 1], y)
        wlen = max(1, int(0.001 * fs))  # ~1 ms averaging window, applied 3x
        for _ in range(3):
            y = y - uniform_filter1d(y, size=2 * wlen + 1)
        gci = np.where((y[:-1] < 0) & (y[1:] >= 0))[0]
        return gci

    def lpc_inverse_filter(x, fs, order=None):
        order = order or int(2 + fs / 1000)
        a = librosa.lpc(x.astype(float), order=order)
        residual = lfilter(a, [1], x)  # ~ glottal flow derivative
        flow = lfilter([1], [1, -0.99], residual)  # leaky integration -> flow
        return flow

    def compute_quotients(flow, gcis):
        oqs, cqs, sqs = [], [], []
        for i0, i1 in zip(gcis[:-1], gcis[1:]):
            cycle = flow[i0:i1]
            T0 = i1 - i0
            if T0 < 4:
                continue
            goi = np.argmin(cycle)  # most-closed point = opening instant
            open_seg = cycle[goi:]
            if len(open_seg) < 2:
                continue
            peak = np.argmax(open_seg) + goi  # instant of max glottal opening
            OQ = (T0 - goi) / T0
            CQ = 1 - OQ
            opening_dur = peak - goi
            closing_dur = T0 - peak
            if closing_dur <= 0:
                continue
            SQ = opening_dur / closing_dur
            oqs.append(OQ);
            cqs.append(CQ);
            sqs.append(SQ)
        return np.array(oqs), np.array(cqs), np.array(sqs)

    x, fs = librosa.load(path, sr=None, mono=True)
    flow = lpc_inverse_filter(x, fs)
    gcis = zff_gci(x, fs)
    oq, cq, sq = compute_quotients(flow, gcis)
    return dict(OQ=oq.mean(), CQ=cq.mean(), SQ=sq.mean(), n_cycles=len(oq))