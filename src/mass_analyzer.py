import os
import re
from dataclasses import dataclass
from decimal import Context

import numpy as np
import scipy.stats as st
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

from ResourceManager import ResourceManager
from signal_processing.AudioFeatures import SignalTimeSeries
from signal_processing.TargetConfig import TargetConfig
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor

@dataclass
class StatisticItem:
    mean: float
    median: float
    min: float
    max: float
    stdev: float

    def __str__(self):
        # Using >7.2f to align the numbers neatly with 2 decimal places
        return (f"Mean: {self.mean:>7.2f} | "
                f"Median: {self.median:>7.2f} | "
                f"Min: {self.min:>7.2f} | "
                f"Max: {self.max:>7.2f} | "
                f"Stdev: {self.stdev:>7.2f}")


@dataclass
class Statistics:
    size: list[StatisticItem]
    pitch: list[StatisticItem]
    weight: list[StatisticItem]
    slopes: list[StatisticItem]

    def __init__(self):
        self.size: list[StatisticItem] = []
        self.pitch: list[StatisticItem] = []
        self.weight: list[StatisticItem] = []
        self.slopes: list[StatisticItem] = []


    def __str__(self):
        def format_category(name: str, items: list[StatisticItem]) -> str:
            if not items:
                return f"  {name}: (Empty)"

            lines = [f"  {name} ({len(items)} items):"]
            # for i, item in enumerate(items, 1):
            #     lines.append(f"    {i:>3}. {item}")

            # --- New CI Calculation Logic ---
            if len(items) >= 2:
                mins = [item.min for item in items]
                maxs = [item.max for item in items]
                means = [item.mean for item in items]
                medians = [item.median for item in items]

                min_ci = calculate_95_ci(mins)
                max_ci = calculate_95_ci(maxs)
                mean_ci = calculate_95_ci(means)
                median_ci = calculate_95_ci(medians)

                # lines.append(f"    ---")
                lines.append(f"    Pop. 95% CI (Mean):   [{engineering_notation(mean_ci[0])}, {engineering_notation(mean_ci[1])}]")
                lines.append(f"    Pop. 95% CI (Median): [{engineering_notation(median_ci[0])}, {engineering_notation(median_ci[1])}]")
                lines.append(f"    Pop. 95% CI (Min):    [{engineering_notation(min_ci[0])}, {engineering_notation(min_ci[1])}]")
                lines.append(f"    Pop. 95% CI (Max):    [{engineering_notation(max_ci[0])}, {engineering_notation(max_ci[1])}]")

            return "\n".join(lines)

        sections = [
            format_category("Size", self.size),
            format_category("Pitch", self.pitch),
            format_category("Weight", self.weight),
            format_category("Slopes", self.slopes)
        ]
        return "\n".join(sections)


def engineering_notation(val, sig_digits=3):
    """Formats a float to 3 significant digits in true engineering notation."""
    if val != val:  # Quick check for NaN
        return "      NaN"
    # Create a decimal with 3 sig figs and convert to engineering string
    eng_str = Context(prec=sig_digits).create_decimal(float(val)).to_eng_string()
    return f"{eng_str:>9}" # Right-align for neat columns

def calculate_95_ci(data: list[float]) -> tuple[float, float]:
    """Calculates the 95% Confidence Interval for a given list of floats using the t-distribution."""
    n = len(data)
    if n < 2:
        return (float('nan'), float('nan'))

    mean_val = np.mean(data)
    standard_error = np.std(data, ddof=1) / np.sqrt(n)

    # Calculate 95% CI using t-distribution
    ci_lower, ci_upper = st.t.interval(0.95, df=n - 1, loc=mean_val, scale=standard_error)
    return ci_lower, ci_upper

def get_robust_min_max_y(signal: SignalTimeSeries, eps: float = .3, min_samples: int = 5, stdev_distance=1) -> StatisticItem:
    """
    Uses DBSCAN to filter out outlier noise and find the true min/max y-values.
    """
    x_clean = signal.get_x_without_NaN()
    y_clean = signal.get_y_without_NaN()

    # Handle edge case where no valid data exists
    if len(y_clean) == 0:
        return None, None

    # 1. Prepare data (Stack x and y into a 2D array)
    data = np.column_stack((x_clean, y_clean))

    # 2. Scale the data
    # DBSCAN uses Euclidean distance. If your x (time) and y (amplitude)
    # are on vastly different scales, DBSCAN will fail. Scaling normalizes this.
    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(data)

    # 3. Apply DBSCAN
    # eps: Maximum distance between two samples to be considered in the same neighborhood.
    # min_samples: The number of samples in a neighborhood to be considered a core point.
    dbscan = DBSCAN(eps=eps, min_samples=min_samples)
    labels = dbscan.fit_predict(data_scaled)

    # 4. Filter out noise
    # DBSCAN assigns a label of -1 to any point it considers "noise" (an outlier)
    valid_signal_mask = labels != -1

    # Edge case: If DBSCAN thinks *everything* is noise, fallback to standard min/max
    if not np.any(valid_signal_mask):
        print("Warning: DBSCAN classified all points as noise. Returning absolute min/max.")
        return np.min(y_clean), np.max(y_clean)

    # 5. Extract the y-values that belong to actual clusters
    y_clustered = y_clean[valid_signal_mask]

    stdev = np.std(y_clustered)
    median = np.median(y_clustered)
    mean = np.mean(y_clustered)

    return StatisticItem(mean=mean, median=median, min=median-stdev*stdev_distance, max=median+stdev*stdev_distance, stdev=stdev)

def calculate_statistics_for_target(target, file_regex):
    statistics = Statistics()

    rm = ResourceManager()
    target = TargetConfig.from_json(rm.get_absolute_path(target))
    extractor = AudioFeatureExtractor(target)

    matching_files = []
    compiled_pattern = re.compile(file_regex)
    for root, _, files in os.walk("C:\\Users\\Fabian\\Sync\\transitionering\\vis2\\examples\\accent_gmu_edu\\swedish"):
        for file in files:
            if compiled_pattern.search(file):
                matching_files.append(os.path.join(root, file))

    for file in matching_files:
        print(f"Processing {file}")

        result = extractor.analyzeFile(file)

        statistics.pitch.append(get_robust_min_max_y(result.pitch))
        statistics.size.append(get_robust_min_max_y(result.size))
        statistics.weight.append(get_robust_min_max_y(result.weight_333ms_max, stdev_distance=1))
        statistics.slopes.append(get_robust_min_max_y(result.slopes, stdev_distance=1))

    return statistics


if __name__ == "__main__":
    stats_female = calculate_statistics_for_target("targets/target_female.json", "F.*.mp3")
    stats_male = calculate_statistics_for_target("targets/target_male.json", "M.*.mp3")

    print("Statistics, female")
    print(stats_female)

    print("Statistics, male")
    print(stats_male)
