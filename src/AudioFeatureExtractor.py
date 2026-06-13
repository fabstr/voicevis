import time

import opensmile
import miniaudio
import numpy as np
import wave
import contextlib


from PlotsSpec import outliers_m


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

    def __init__(self):
        self.smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
        )

    def analyzePCM(self, pcm_data, sampling_rate):
        df = self.smile.process_signal(pcm_data, sampling_rate)
        audio_length = len(pcm_data) / float(sampling_rate)
        return self.extractFeatures(df, sampling_rate, audio_length)

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

    def analyzeFile(self, path):
        df = None
        if (path.endswith('.wav')):
            start_time = time.perf_counter()
            df = self.smile.process_file(path)
            elapsed_time = time.perf_counter() - start_time
            print(f"Opensmile analysis time: {elapsed_time:.4f} seconds.")

            with contextlib.closing(wave.open(path, 'r')) as f:
                frames = f.getnframes()
                sampling_rate = f.getframerate()
                audio_length = frames / float(sampling_rate)
                return self.extractFeatures(df, sampling_rate, audio_length)

        elif (path.endswith('.mp3')):

            start_time = time.perf_counter()
            pcm_data, sampling_rate = self.convertMp3ToPcm(path)
            elapsed_time = time.perf_counter() - start_time
            print(f"MP3 convertion time: {elapsed_time:.4f} seconds.")

            start_time = time.perf_counter()
            df = self.smile.process_signal(pcm_data, sampling_rate)
            elapsed_time = time.perf_counter() - start_time
            print(f"Opensmile analysis time: {elapsed_time:.4f} seconds.")

            audio_length = len(pcm_data) / float(sampling_rate)
            return self.extractFeatures(df, sampling_rate, audio_length)

    def extractFeatures(self, df, sampling_rate, audio_length):
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
        slope_0_500 = df['slope0-500_sma3'].to_numpy()
        slope_500_1500 = df['slope500-1500_sma3'].to_numpy()
        loudness_raw = df['Loudness_sma3'].to_numpy()

        # 2. Vectorized Filtering (Replaces the slow 'for' loop)
        valid_mask = pitch > 27.5
        t_filtered = timepoints[valid_mask]

        # 3. Construct the result dictionary using filtered arrays
        result = {
            "pitch": {"x": t_filtered, "y": pitch[valid_mask]},
            "F1": {"x": t_filtered, "y": f1[valid_mask]},
            "F2": {"x": t_filtered, "y": f2[valid_mask]},
            "F3": {"x": t_filtered, "y": f3[valid_mask]},

            "F1_ratio": {"x": t_filtered, "y": f2[valid_mask] / f1[valid_mask]},
            "F3_ratio": {"x": t_filtered, "y": f3[valid_mask] / f1[valid_mask]},

            "slope_0_500": {"x": t_filtered, "y": slope_0_500[valid_mask]},
            "slope_500_1500": {"x": t_filtered, "y": slope_500_1500[valid_mask]},

            "loudness": {"x": t_filtered, "y": loudness_raw[valid_mask]},

            "sample_rate": sampling_rate,
            "length_seconds": audio_length
        }

        if len(t_filtered) > 0:
            # 4. Handle Outliers
            result["pitch"] = reject_outliers(result["pitch"])
            result["F1_ratio"] = reject_outliers(result["F1_ratio"])
            result["F3_ratio"] = reject_outliers(result["F3_ratio"])

            result["F3_ratio"]["y"] = np.negative(result["F3_ratio"]["y"])

            # 5. Vectorized Min-Max Normalization for Loudness
            l_arr = result["loudness"]["y"]
            l_min, l_max = l_arr.min(), l_arr.max()
            if l_max != l_min:
                result["loudness"]["y"] = (l_arr - l_min) / (l_max - l_min)


            # adjust weight slopes
            result["slope_0_500"]["y"] = result["slope_0_500"]["y"] + (0 - result["slope_0_500"]["y"].min())
            result["slope_500_1500"]["y"] = result["slope_500_1500"]["y"] + (0 - result["slope_500_1500"]["y"].min())
            result["slope_500_1500"]["y"] = np.negative(result["slope_500_1500"]["y"])

        else:
            # If the chunk is silent, keep arrays empty and avoid reduction crashes
            print("Silent/unvoiced frame skipped safely.")

        # Stop the timer and calculate elapsed time
        elapsed_time = time.perf_counter() - start_time
        print(f"Post opensmile analysis time: {elapsed_time:.4f} seconds.")

        return  result


def reject_outliers(pair, m=outliers_m):
    d = np.abs(pair["y"] - np.median(pair["y"]))
    mdev = np.median(d)
    s = d / mdev if mdev else np.zeros(len(d))
    filteredX = []
    filteredY = []
    for i in range(len(pair["x"])):
        if s[i] < m:
            filteredX.append(pair["x"][i])
            filteredY.append(pair["y"][i])
    return {"x": filteredX, "y": filteredY}
