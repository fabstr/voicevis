import time

import opensmile
import miniaudio
import numpy as np
import wave

from scipy.signal import stft, spectrogram

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

    def __init__(self, targets: TargetConfig = TargetConfig()):
        """
        Constructor for AudioFeatureExtractor.

        A custom configuration has been defined for Opensmile to compute more harmonics.

        :param targets: The default target config to use when analysis requires targets to compare against.
        """
        self.smile = opensmile.Smile(
            feature_set='resources/smile_configs/egemaps/v02/eGeMAPSv02.conf',
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
            print("Unknown file extension")
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

        # Apply the filter and extract the valid time points
        t_filtered = timepoints[valid_mask]

        # 3. Construct the result dictionary using filtered arrays
        result = AudioFeatures(
            sample_rate=sampling_rate,
            length_seconds=audio_length,

            pitch=SignalTimeSeries(x=t_filtered, y=pitch[valid_mask]),
            loudness=SignalTimeSeries(x=t_filtered, y=loudness[valid_mask]),
            weight=calculate_weight(pcm_data, sampling_rate, t_filtered),
            spectrogram=calculate_spectrogram(pcm_data, sampling_rate),

            F1=SignalTimeSeries(x=t_filtered, y=f1[valid_mask]),
            F1_Pitch=SignalTimeSeries(x=t_filtered, y=f1[valid_mask] / pitch[valid_mask]),
            F1_Pitch_rel_amplitude=SignalTimeSeries(x=t_filtered, y=df['F1amplitudeLogRelF0_sma3nz'].to_numpy()[valid_mask]),

            F2=SignalTimeSeries(x=t_filtered, y=f2[valid_mask]),
            F2_Pitch=SignalTimeSeries(x=t_filtered, y=f2[valid_mask] / pitch[valid_mask]),
            F2_Pitch_rel_amplitude=SignalTimeSeries(x=t_filtered, y=df['F2amplitudeLogRelF0_sma3nz'].to_numpy()[valid_mask]),

            F3=SignalTimeSeries(x=t_filtered, y=f3[valid_mask]),
            F3_Pitch=SignalTimeSeries(x=t_filtered, y=f3[valid_mask] / pitch[valid_mask]),
            F3_Pitch_rel_amplitude=SignalTimeSeries(x=t_filtered, y=df['F3amplitudeLogRelF0_sma3nz'].to_numpy()[valid_mask]),

            H1_H2=SignalTimeSeries(x=t_filtered, y=np.subtract(0, df['logRelF0-H1-H2_sma3nz'].to_numpy()[valid_mask])),
            H1_H3=SignalTimeSeries(x=t_filtered, y=np.subtract(0, df['logRelF0-H1-H3_sma3nz'].to_numpy()[valid_mask])),
            H1_H4=SignalTimeSeries(x=t_filtered, y=np.subtract(0, df['logRelF0-H1-H4_sma3nz'].to_numpy()[valid_mask])),
            H1_A3=SignalTimeSeries(x=t_filtered, y=np.subtract(0, df['logRelF0-H1-A3_sma3nz'].to_numpy()[valid_mask])),
        )

        result.weight2 = calculate_weight2(result.H1_H2, result.H1_H3, result.H1_H4, self.target_config)
        result.size = calculate_size(result, self.target_config)

        return result

def calculate_size(results: AudioFeatures, target_config) -> SignalTimeSeries:
    if target_config is None or len(results.pitch.x) == 0:
        return SignalTimeSeries()

    if not target_config.has_all_bounds(["f1_pitch", "f2_pitch", "f3_pitch"]):
        print("No target defined for F1, F2 or F3. Size cannot be calculated.")
        return SignalTimeSeries()

    # Calculate signed error vectors (Actual - Target)
    err_F1 = calculate_target_error(results.F1_Pitch.y, target_config.get_mean("f1_pitch"))
    err_F2 = calculate_target_error(results.F2_Pitch.y, target_config.get_mean("f2_pitch"))
    err_F3 = calculate_target_error(results.F3_Pitch.y, target_config.get_mean("f3_pitch"))

    # Stack them into a 2D array of shape (3, time_steps)
    stacked_errors = np.vstack([err_F1, err_F2, err_F3])

    # Calculate standard RMS magnitude (always positive)
    # and extract the net direction of the errors at each timestamp
    rms_magnitude = np.sqrt(np.mean(stacked_errors ** 2, axis=0))
    net_direction = np.sign(np.sum(stacked_errors, axis=0))
    size_y = net_direction * rms_magnitude

    return SignalTimeSeries(x=results.F1_Pitch.x, y=size_y)

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

    # 2. Calculate the spectral slope for each frame using vectorized linear regression
    # f shape: (F,)
    # mag_spectrum shape: (F, T)
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

    # 3. Normalize to floating-point values between -1.0 and 1.0
    # openSMILE expects standard normalized float32/64 audio signals
    signal = pcm_data.astype(np.float32) / 32768.0
    return signal, sampling_rate

def calculate_weight2(H1_H2: SignalTimeSeries, H1_H3: SignalTimeSeries, H1_H4: SignalTimeSeries, targets: TargetConfig, window_duration = 10):
    # TODO fix
    return SignalTimeSeries()

def calculate_weight(samples, sampling_rate, timepoints) -> SignalTimeSeries:
    t_weight, weight = calculate_spectral_slope(samples, sampling_rate, nperseg=2048, noverlap=1024)

    #  Interpolate slopes to match the filtered timepoints
    if len(t_weight) > 0 and len(timepoints) > 0:
        matched_weight = np.interp(timepoints, t_weight, weight)
    else:
        matched_weight = np.zeros_like(timepoints)

    return SignalTimeSeries(x=timepoints, y=matched_weight)

def calculate_spectrogram(samples, sampling_rate) -> SpectrogramData:
    f_spec, t_spec, Sxx = spectrogram(samples, fs=sampling_rate, window='hann', nperseg=nperseg, noverlap=noverlap)

    # Convert magnitude to log scale (Decibels), strictly clipping to prevent log(0) errors
    Sxx_db = 10 * np.log10(np.clip(Sxx, 1e-10, None))

    return SpectrogramData(x=t_spec, y=f_spec, magnitude_db=Sxx_db)

