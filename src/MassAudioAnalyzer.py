import os
import time

import numpy as np
import pandas as pd
import pyqtgraph as pg
import pyqtgraph.exporters

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
    lower_bound = float(np.percentile(clean_data, (100 - ci) / 2))
    upper_bound = float(np.percentile(clean_data, 100 - (100 - ci) / 2))
    return lower_bound, upper_bound


def export_quality_plots(pools: dict, prefix: str):
    """
    Takes the pooled time-series data and exports a pyqtgraph image
    for each respective quality against time.
    """
    # PyQtGraph requires a QApplication instance to run, even headless
    app = pg.mkQApp("Plotting App")

    print(f"\nExporting plots for {prefix}...")
    for metric, data in pools.items():
        x = np.array(data["x"])
        y = np.array(data["y"])

        if len(x) == 0 or len(y) == 0:
            continue

        # Clean out NaNs for plotting
        valid_mask = np.isfinite(y) & np.isfinite(x)
        x_clean = x[valid_mask]
        y_clean = y[valid_mask]

        # Initialize an off-screen PlotWidget
        plot_widget = pg.PlotWidget(title=f"{prefix} - {metric.capitalize()} over Time")
        plot_widget.setLabel('bottom', 'Time (s)')
        plot_widget.setLabel('left', metric.capitalize())
        plot_widget.setBackground('w')

        # Using a scatter plot because line plots across multiple files will zigzag back to 0
        plot_widget.plot(
            x_clean, y_clean,
            pen=None,
            symbol='o',
            symbolSize=1,
            symbolPen=None,
            symbolBrush=(50, 100, 255, 100)  # Semi-transparent blue
        )

        # Export the plot to an image file
        exporter = pg.exporters.ImageExporter(plot_widget.plotItem)
        exporter.parameters()['width'] = 1000  # Set high resolution width

        filename = f"{prefix}_{metric}_plot.png"
        exporter.export(filename)
        print(f" -> Saved {filename}")


def generate_config_for_gender(df_subset: pd.DataFrame, audio_dir: str, ci: int, prefix: str) -> TargetConfig:
    """Loops through a dataframe subset, extracts features, pools data points, and builds TargetConfig."""
    extractor = AudioFeatureExtractor()

    # Initialize master pools for each target metric tracking both x (time) and y (value)
    pools = {
        "pitch": {"x": [], "y": []},
        "loudness": {"x": [], "y": []},
        "f1": {"x": [], "y": []},
        "f2": {"x": [], "y": []},
        "f3": {"x": [], "y": []},
        "f1_pitch": {"x": [], "y": []},
        "f2_pitch": {"x": [], "y": []},
        "f3_pitch": {"x": [], "y": []},
        "size": {"x": [], "y": []},
        "weight": {"x": [], "y": []}
    }

    total_files = len(df_subset)

    # Print initial state
    print(f"0 of {total_files}", end='', flush=True)

    for idx, (_, row) in enumerate(df_subset.iterrows(), start=1):
        audio_path = os.path.join(audio_dir, row['audio_file'])

        try:
            features = extractor.analyzeFile(audio_path)

            # Aggregate time-series scalar 'y' and 'x' values across files
            # Assuming features.[quality].x exists to represent time.
            pools["pitch"]["y"].extend(features.pitch.y);
            pools["pitch"]["x"].extend(features.pitch.x)
            pools["loudness"]["y"].extend(features.loudness.y);
            pools["loudness"]["x"].extend(features.loudness.x)
            pools["f1"]["y"].extend(features.F1.y);
            pools["f1"]["x"].extend(features.F1.x)
            pools["f2"]["y"].extend(features.F2.y);
            pools["f2"]["x"].extend(features.F2.x)
            pools["f3"]["y"].extend(features.F3.y);
            pools["f3"]["x"].extend(features.F3.x)
            pools["f1_pitch"]["y"].extend(features.F1_Pitch.y);
            pools["f1_pitch"]["x"].extend(features.F1_Pitch.x)
            pools["f2_pitch"]["y"].extend(features.F2_Pitch.y);
            pools["f2_pitch"]["x"].extend(features.F2_Pitch.x)
            pools["f3_pitch"]["y"].extend(features.F3_Pitch.y);
            pools["f3_pitch"]["x"].extend(features.F3_Pitch.x)
            pools["size"]["y"].extend(features.size.y);
            pools["size"]["x"].extend(features.size.x)
            pools["weight"]["y"].extend(features.weight.y);
            pools["weight"]["x"].extend(features.weight.x)

            print(f"\r{idx} of {total_files}", end='', flush=True)

        except Exception as e:
            print(f"\nSkipping file {row['audio_file']} due to error: {e}")
            continue

    print("")

    # Generate pyqtgraph images for the pooled data
    export_quality_plots(pools, prefix)

    # Compute 95% CI boundaries for all metrics (extracting just the 'y' values for the CI calculation)
    ci_limits = {metric: calculate_ci(np.array(data["y"]), ci) for metric, data in pools.items()}

    return TargetConfig()
   # return TargetConfig(
   #     loudness_min=ci_limits["loudness"][0], loudness_max=ci_limits["loudness"][1],
   #     pitch_min=ci_limits["pitch"][0], pitch_max=ci_limits["pitch"][1],
   #     f1_min=ci_limits["f1"][0], f1_max=ci_limits["f1"][1],
   #     f2_min=ci_limits["f2"][0], f2_max=ci_limits["f2"][1],
   #     f3_min=ci_limits["f3"][0], f3_max=ci_limits["f3"][1],
   #     f1_pitch_min=ci_limits["f1_pitch"][0], f1_pitch_max=ci_limits["f1_pitch"][1],
   #     f2_pitch_min=ci_limits["f2_pitch"][0], f2_pitch_max=ci_limits["f2_pitch"][1],
   #     f3_pitch_min=ci_limits["f3_pitch"][0], f3_pitch_max=ci_limits["f3_pitch"][1],
    #    size_min=ci_limits["size"][0], size_max=ci_limits["size"][1],
   #     weight_min=ci_limits["weight"][0], weight_max=ci_limits["weight"][1]
    #)


# ==========================================
# 4. Execution Entry Point
# ==========================================

if __name__ == "__main__":

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
    male_config = generate_config_for_gender(male_df, audio_directory, 90, prefix="male")
    male_target_file = "male_targets_" + str(time.strftime("%Y%m%d-%H%M%S")) + ".json"
    male_config.to_json(male_target_file)
    print("Wrote " + male_target_file)

    print("")

    print("Processing Feminine Corpus Subset...")
    female_config = generate_config_for_gender(female_df, audio_directory, 90, prefix="female")
    female_target_file = "female_config" + str(time.strftime("%Y%m%d-%H%M%S")) + ".json"
    female_config.to_json(female_target_file)
    print("Wrote " + female_target_file)

    # --- Output Verification ---
    print("\n" + "=" * 40)
    print("GENERATED TARGET CONFIGURATION SETS")
    print("=" * 40)
    print(f"\n[Male/Masculine TargetConfig]:\n{male_config}")
    print(f"\n[Female/Feminine TargetConfig]:\n{female_config}")