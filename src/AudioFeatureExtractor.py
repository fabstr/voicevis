import opensmile
import miniaudio
import numpy as np
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

    def convertMp3ToPcm(self, mp3_path):
        # 1. Decode MP3 to raw PCM using miniaudio
        print(mp3_path)
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

    def analyze(self, path):
        df = None
        if (path.endswith('.wav')):
            df = self.smile.process_file(path)
        elif (path.endswith('.mp3')):
            pcm_data, sampling_rate = self.convertMp3ToPcm(path)
            df = self.smile.process_signal(pcm_data, sampling_rate)

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
            "slope_500_1500": []
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

    aa = afe.analyze(p)
    print(aa["F1_ratio"])
    print(aa["A3_ratio"])

#
# # 1. Initialize the openSMILE extractor using the eGeMAPS v02 standard set
# # We select 'LowLevelDescriptors' to get values frame-by-frame (every 10-20ms)
#
# # 2. Process your audio file (must be a .wav file)
# # This returns a multi-indexed Pandas DataFrame
#
# p = path.join("C:\\", "Users", "Fabian", "Sync", "transitionering", "vis2", "bbb.wav")
#
# df = smile.process_file(str(p))
#
# # 3. Filter out the specific features related to Vocal Weight / Spectral Tilt
# # selected_features = [
# #     "F0semitoneFrom27.5Hz_sma3nz", # pitch (?)
# #
# #     # Formant frequencyies
# #     "F1frequency_sma3nz",
# #     "F2frequency_sma3nz",
# #     "F3frequency_sma3nz"
# # ]
#
# pitch = [27.5 * (2 ** (semitone/12)) for semitone in df['F0semitoneFrom27.5Hz_sma3nz']]
# F1 = [f for f in df['F1frequency_sma3nz']]
# F2 = [f for f in df['F2frequency_sma3nz']]
# F3 = [f for f in df['F3frequency_sma3nz']]
#
#
# print(pitch)
# print(F1)
# print(F2)
# print(F3)
#
# # # selected_features = [
# # #     "logRelF0-H1-H2_sma3nz",     # H1-H2 (Harmonic difference)
# # #     "alphaRatio_sma3",          # Ratio of lower vs higher frequency energy
# # #     "hammarbergIndex_sma3",     # Spectral tilt measure
# # #     "slope0-500_sma3",          # Slope of the spectrum between 0-500 Hz
# # #     "jitterLocal_sma3nz"        # Micro-instability in stamen frequencies
# # # ]
# # #
# # # 4. Display the results
# # filtered_df = df[selected_features]
# # print(filtered_df.head())
# #
# # print(filtered_df.get(
# #     'F3frequency_sma3nz'
# # ))
# #
# # with open("features.txt", "w") as features:
# #     for f in df.head():
# #         features.write(str(f) + "\n")
# #
# # print(semitoneToHz(13.1529399))
# # print(semitoneToHz(13.1529399))
# # print(semitoneToHz(13.609562))
# # print(semitoneToHz(14.963234))
# # print(semitoneToHz(15.920908))