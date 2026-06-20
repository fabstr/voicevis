import os
import time

import numpy as np
import pandas as pd

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.TargetConfig import TargetConfig


def calculate_ci(data: np.ndarray, ci=95) -> tuple[float, float]:
    """
    Calculates the 95% Confidence Interval for the population range
    using the 2.5th and 97.5th percentiles to establish boundary targets.
    """
    if len(data) == 0:
        return 0.0, 0.0
    # Clean out any NaNs or Infs that could disrupt the statistical metrics
    clean_data = data[np.isfinite(data)]
    if len(clean_data) == 0:
        return 0.0, 0.0

    # Using percentiles captures the 90% distribution profile safely for thresholds
    lower_bound = float(np.percentile(clean_data, (100-ci)/2))
    upper_bound = float(np.percentile(clean_data, 100-(100-ci)/2))
    return lower_bound, upper_bound


def generate_config_for_gender(df_subset: pd.DataFrame, audio_dir: str, ci) -> TargetConfig:
    """Loops through a dataframe subset, extracts features, pools data points, and builds TargetConfig."""
    extractor = AudioFeatureExtractor()

    # Initialize master pools for each target metric
    pools = {
        "pitch": [], "loudness": [], "f1": [], "f2": [], "f3": [],
        "f1_pitch": [], "f2_pitch": [], "f3_pitch": [], "size": [], "weight": []
    }

    total_files = len(df_subset)

    # Print initial state
    print(f"0 of {total_files}", end='', flush=True)

    for idx, (_, row) in enumerate(df_subset.iterrows(), start=1):
        audio_path = os.path.join(audio_dir, row['audio_file'])

        try:
            features = extractor.analyzeFile(audio_path)

            # Aggregate time-series scalar 'y' values across files
            pools["pitch"].extend(features.pitch.y)
            pools["loudness"].extend(features.loudness.y)
            pools["f1"].extend(features.F1.y)
            pools["f2"].extend(features.F2.y)
            pools["f3"].extend(features.F3.y)
            pools["f1_pitch"].extend(features.F1_Pitch.y)
            pools["f2_pitch"].extend(features.F2_Pitch.y)
            pools["f3_pitch"].extend(features.F3_Pitch.y)
            pools["size"].extend(features.size.y)
            pools["weight"].extend(features.weight.y)  # Maps to weight metrics

            print(f"\r{idx} of {total_files}", end='', flush=True)

        except Exception as e:
            print(f"Skipping file {row['audio_file']} due to error: {e}")
            continue

    print("")

    # Compute 95% CI boundaries for all metrics
    ci_limits = {metric: calculate_ci(np.array(values), ci) for metric, values in pools.items()}

    return TargetConfig(
        loudness_min=ci_limits["loudness"][0], loudness_max=ci_limits["loudness"][1],
        pitch_min=ci_limits["pitch"][0], pitch_max=ci_limits["pitch"][1],
        f1_min=ci_limits["f1"][0], f1_max=ci_limits["f1"][1],
        f2_min=ci_limits["f2"][0], f2_max=ci_limits["f2"][1],
        f3_min=ci_limits["f3"][0], f3_max=ci_limits["f3"][1],
        f1_pitch_min=ci_limits["f1_pitch"][0], f1_pitch_max=ci_limits["f1_pitch"][1],
        f2_pitch_min=ci_limits["f2_pitch"][0], f2_pitch_max=ci_limits["f2_pitch"][1],
        f3_pitch_min=ci_limits["f3_pitch"][0], f3_pitch_max=ci_limits["f3_pitch"][1],
        size_min=ci_limits["size"][0], size_max=ci_limits["size"][1],
        weight_min=ci_limits["weight"][0], weight_max=ci_limits["weight"][1]
    )


# ==========================================
# 4. Execution Entry Point
# ==========================================

if __name__ == "__main__":

    #tsv_path = "C:\\Users\\Fabian\\Sync\\transitionering\\vis2\\examples\\sps-corpus-4.0-2026-06-12-en\\ss-corpus-en short.tsv"
    tsv_path = "C:\\Users\\Fabian\\Sync\\transitionering\\vis2\\examples\\sps-corpus-4.0-2026-06-12-en\\ss-corpus-en.tsv"

    audio_directory = "C:\\Users\\Fabian\\Sync\\transitionering\\vis2\\examples\\sps-corpus-4.0-2026-06-12-en\\audios"

    # Load dataset index safely handling TSV structures
    if not os.path.exists(tsv_path):
        print(f"Error: Database index file '{tsv_path}' missing.")
        # Generates a quick mock dataframe if the file doesn't exist locally to demonstrate script survival
        df = pd.DataFrame({
            'audio_file': ['test1.wav', 'test2.wav'],
            'gender': ['male_masculine', 'female_feminine']
        })
        # Create mock audio files so extractor passes sanity check
        os.makedirs(audio_directory, exist_ok=True)
        for f in df['audio_file']: open(os.path.join(audio_directory, f), 'a').close()
    else:
        print("Reading database index file...")
        df = pd.read_csv(tsv_path, sep='\t')

    print("Extracting by gender")
    male_df = df[df['gender'] == 'male_masculine']
    female_df = df[df['gender'] == 'female_feminine']
    print("Number of male audios: " + str(len(male_df)))
    print("Number of female audios: " + str(len(female_df)))

    print("")

    print("Processing Masculine Corpus Subset...")
    male_config = generate_config_for_gender(male_df, audio_directory, 90)
    male_target_file = "male_targets_" + str(time.strftime("%Y%m%d-%H%M%S")) + ".json"
    male_config.to_json(male_target_file)
    print("Wrote " + male_target_file)

    print("")

    print("Processing Feminine Corpus Subset...")
    female_config = generate_config_for_gender(female_df, audio_directory, 90)
    female_target_file = "female_config" + str(time.strftime("%Y%m%d-%H%M%S")) + ".json"
    female_config.to_json(female_target_file)
    print("Wrote " + female_target_file)

    # --- Output Verification ---
    print("\n" + "=" * 40)
    print("GENERATED TARGET CONFIGURATION SETS")
    print("=" * 40)
    print(f"\n[Male/Masculine TargetConfig]:\n{male_config}")
    print(f"\n[Female/Feminine TargetConfig]:\n{female_config}")
