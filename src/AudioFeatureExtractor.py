import opensmile
import miniaudio
import numpy as np
import wave
import contextlib
from os import path


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

    features = [
        "F0semitoneFrom27.5Hz_sma3nz",
        "F1frequency_sma3nz",
        "F2frequency_sma3nz",
        "F3frequency_sma3nz",
        "logRelF0-H1-H2_sma3nz",
        "logRelF0-H1-A3_sma3nz",
        "slope0-500_sma3",
        "slope500-1500_sma3"
    ]

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
            df = self.smile.process_file(path)
            with contextlib.closing(wave.open(path, 'r')) as f:
                frames = f.getnframes()
                sampling_rate = f.getframerate()
                audio_length = frames / float(sampling_rate)
                return self.extractFeatures(df, sampling_rate, audio_length)
        elif (path.endswith('.mp3')):
            pcm_data, sampling_rate = self.convertMp3ToPcm(path)
            df = self.smile.process_signal(pcm_data, sampling_rate)
            audio_length = len(pcm_data) / float(sampling_rate)
            return self.extractFeatures(df, sampling_rate, audio_length)

    def extractFeatures(self, df, sampling_rate, audio_length):
        timepoints_raw = [t for t in df.index.get_level_values('start').total_seconds()]
        pitch = [27.5 * (2 ** (semitone/12)) for semitone in df['F0semitoneFrom27.5Hz_sma3nz']]
        F1_ratio = [r for r in df["logRelF0-H1-H2_sma3nz"]]
        A3_ratio = [r for r in df["logRelF0-H1-A3_sma3nz"]]
        F1 = [f for f in df['F1frequency_sma3nz']]
        F2 = [f for f in df['F2frequency_sma3nz']]
        F3 = [f for f in df['F3frequency_sma3nz']]
        slope_0_500 = [s for s in df['slope0-500_sma3']]
        slope_500_1500 = [s for s in df['slope500-1500_sma3']]

        result = {
            "timepoints": [],

            "pitch": [],

            "F1": [],
            "F2": [],
            "F3": [],

            "F1_ratio": [],
            "A3_ratio": [],

            "slope_0_500": [],
            "slope_500_1500": [],

            "sample_rate": sampling_rate,
            "length_seconds": audio_length
        }

        for i in range(0, len(timepoints_raw)):
            if pitch[i] > 27.5:
                result["timepoints"].append(timepoints_raw[i])
                result["pitch"].append(pitch[i])
                result["F1"].append(F1[i])
                result["F2"].append(F2[i])
                result["F3"].append(F3[i])
                result["slope_0_500"].append(slope_0_500[i])
                result["slope_500_1500"].append(slope_500_1500[i])
                #result["F1_ratio"].append(F1_ratio[i])
                #result["A3_ratio"].append(A3_ratio[i])

        result["F1_ratio"] = np.divide(result["F2"], result["F1"])
        result["A3_ratio"] = np.divide(result["F3"], result["F1"])

        return  result

if __name__ == "__main__":
    p = path.join("C:\\", "Users", "Fabian", "Sync", "transitionering", "vis2", "bbb.wav")
    afe = AudioFeatureExtractor()

    aa = afe.analyzeWaveFile(p)