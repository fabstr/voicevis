#!/usr/bin/env python3
import sys
import os
import argparse
import csv
import json
import numpy as np
import scipy.stats as stats
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the directory containing this script to sys.path so that imports from signal_processing work
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.TargetConfig import TargetConfig


def process_single_file(file_path):
    """
    Worker function executed in threads.
    Processes a single file and extracts features safely.
    """
    filename = os.path.basename(file_path)
    try:
        # Initialize an extractor per thread to prevent shared state issues
        target_config = TargetConfig()
        extractor = AudioFeatureExtractor(target_config)

        features = extractor.analyzeFile(file_path)

        def get_stats(series):
            if series is not None and hasattr(series, 'y') and len(series.y) > 0:
                return float(np.mean(series.y)), float(np.median(series.y))
            return None, None

        pitch_mean, pitch_med = get_stats(features.pitch)
        f3_pitch_mean, f3_pitch_med = get_stats(features.F3_Pitch)
        f2_pitch_mean, f2_pitch_med = get_stats(features.F2_Pitch)
        f1_pitch_mean, f1_pitch_med = get_stats(features.F1_Pitch)
        weight_mean, weight_med = get_stats(features.slopes)

        row_data = {
            "Filename": filename,
            "Pitch_Mean": pitch_mean, "Pitch_Median": pitch_med,
            "F3_Pitch_Mean": f3_pitch_mean, "F3_Pitch_Median": f3_pitch_med,
            "F2_Pitch_Mean": f2_pitch_mean, "F2_Pitch_Median": f2_pitch_med,
            "F1_Pitch_Mean": f1_pitch_mean, "F1_Pitch_Median": f1_pitch_med,
            "Weight_Mean": weight_mean, "Weight_Median": weight_med,
            "Success": True
        }
        return row_data

    except Exception as e:
        print(f"Error processing {filename}: {e}", file=sys.stderr)
        return {
            "Filename": filename,
            "Success": False
        }


def main():
    parser = argparse.ArgumentParser(
        description="Extract mean and median values of Pitch, F3/Pitch, F2/Pitch, F1/Pitch and Weight to CSV with 99% CI group summaries and target JSON export")
    parser.add_argument("-i", "--input", required=True, help="Directory path containing input .wav/.mp3 files")
    parser.add_argument("-o", "--output", required=True, help="Path to the output CSV file")
    args = parser.parse_known_args()[0]

    input_dir = args.input
    output_csv = args.output

    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' does not exist.")
        sys.exit(1)

    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(output_csv))
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Gather target audio files (.wav, .mp3)
    extensions = ('.wav', '.mp3')
    audio_files = [
        os.path.join(input_dir, f) for f in os.listdir(input_dir)
        if f.lower().endswith(extensions)
    ]

    if not audio_files:
        print(f"No audio files (.wav or .mp3) found in '{input_dir}'.")
        sys.exit(0)

    total_files = len(audio_files)
    print(f"Found {total_files} audio files to process. Using 16 worker threads...\n")

    results = []

    # Process files in parallel and stream progress updates to stdout
    with ThreadPoolExecutor(max_workers=16) as executor:
        # Submit all tasks to the pool
        futures = {executor.submit(process_single_file, file_path): file_path for file_path in audio_files}

        # As tasks complete, output to stdout immediately
        completed_count = 0
        for future in as_completed(futures):
            completed_count += 1
            result = future.result()
            results.append(result)

            status = "Successfully processed" if result["Success"] else "Failed"
            print(f"[{completed_count}/{total_files}] {status}: {result['Filename']}")

    # Explicitly sort final payload alphabetically by filename
    results.sort(key=lambda x: x["Filename"].lower())

    # CSV headers
    headers = [
        "Filename",
        "Pitch_Mean", "Pitch_Median",
        "F3_Pitch_Mean", "F3_Pitch_Median",
        "F2_Pitch_Mean", "F2_Pitch_Median",
        "F1_Pitch_Mean", "F1_Pitch_Median",
        "Weight_Mean", "Weight_Median"
    ]

    # Data structures to accumulate values for _M and _F files
    m_data = {col: [] for col in headers[1:]}
    f_data = {col: [] for col in headers[1:]}

    try:
        with open(output_csv, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)

            for result in results:
                filename = result["Filename"]

                if not result["Success"]:
                    # Write row with filename and empty values for errors
                    writer.writerow([filename] + [""] * (len(headers) - 1))
                    continue

                # Write successful row to CSV
                writer.writerow([
                    filename,
                    "" if result["Pitch_Mean"] is None else result["Pitch_Mean"],
                    "" if result["Pitch_Median"] is None else result["Pitch_Median"],
                    "" if result["F3_Pitch_Mean"] is None else result["F3_Pitch_Mean"],
                    "" if result["F3_Pitch_Median"] is None else result["F3_Pitch_Median"],
                    "" if result["F2_Pitch_Mean"] is None else result["F2_Pitch_Mean"],
                    "" if result["F2_Pitch_Median"] is None else result["F2_Pitch_Median"],
                    "" if result["F1_Pitch_Mean"] is None else result["F1_Pitch_Mean"],
                    "" if result["F1_Pitch_Median"] is None else result["F1_Pitch_Median"],
                    "" if result["Weight_Mean"] is None else result["Weight_Mean"],
                    "" if result["Weight_Median"] is None else result["Weight_Median"]
                ])

                # Categorize by gender based on filename
                upper_filename = filename.upper()
                if "_M" in upper_filename:
                    for col in headers[1:]:
                        if result[col] is not None:
                            m_data[col].append(result[col])
                elif "_F" in upper_filename:
                    for col in headers[1:]:
                        if result[col] is not None:
                            f_data[col].append(result[col])

        print(f"\nDone! Successfully wrote sorted results to: {output_csv}")

        # Compute Confidence Intervals
        def compute_99_ci(values):
            clean_values = np.array([v for v in values if v is not None], dtype=float)
            clean_values = clean_values[~np.isnan(clean_values)]
            n = len(clean_values)
            if n < 2:
                return np.nan, np.nan, n, np.nan if n == 0 else float(clean_values[0])

            mean_val = float(np.mean(clean_values))
            std_val = float(np.std(clean_values, ddof=1))
            if std_val == 0.0:
                return mean_val, mean_val, n, mean_val

            sem = std_val / np.sqrt(n)
            try:
                lower, upper = stats.t.interval(0.99, df=n - 1, loc=mean_val, scale=sem)
                return float(lower), float(upper), n, mean_val
            except Exception:
                return np.nan, np.nan, n, mean_val

        def print_group_summary(group_name, group_data):
            print("\n" + "=" * 70)
            print(f"SUMMARY STATISTICS & 99% CONFIDENCE INTERVALS: {group_name.upper()}")
            print("=" * 70)
            print(f"{'Feature / Metric':<18} | {'Count':<5} | {'Mean':<12} | {'99% Confidence Interval':<26}")
            print("-" * 70)

            has_data = False
            for col in headers[1:]:
                vals = group_data[col]
                if not vals:
                    continue
                has_data = True
                lower, upper, count, mean_val = compute_99_ci(vals)

                if np.isnan(mean_val):
                    mean_str = "N/A"
                    ci_str = "N/A"
                elif np.isnan(lower) or np.isnan(upper):
                    mean_str = f"{mean_val:.4g}"
                    ci_str = f"N/A (insufficient data, N={count})"
                else:
                    if "Weight" in col:
                        mean_str = f"{mean_val:.4e}"
                        ci_str = f"[{lower:.4e}, {upper:.4e}]"
                    else:
                        mean_str = f"{mean_val:.4f}"
                        ci_str = f"[{lower:.4f}, {upper:.4f}]"

                friendly_name = col.replace("_", " ")
                print(f"{friendly_name:<18} | {count:<5} | {mean_str:<12} | {ci_str:<26}")

            if not has_data:
                print("No valid data points found for this group.")
            print("-" * 70)

        # Print summaries for both groups
        print_group_summary("Male Files (_M)", m_data)
        print_group_summary("Female Files (_F)", f_data)

        # Function to export target JSONs
        def export_group_targets(group_data, output_paths):
            pitch_ci = compute_99_ci(group_data["Pitch_Mean"])[0:2]
            f3_pitch_ci = compute_99_ci(group_data["F3_Pitch_Mean"])[0:2]
            f2_pitch_ci = compute_99_ci(group_data["F2_Pitch_Mean"])[0:2]
            f1_pitch_ci = compute_99_ci(group_data["F1_Pitch_Mean"])[0:2]
            weight_ci = compute_99_ci(group_data["Weight_Mean"])[0:2]

            data = {
                "Loudness": {"Loudness": {"enabled": False, "min": 0.0, "max": 1.0}},
                "Pitch": {
                    "Pitch": {
                        "enabled": True,
                        "min": float(pitch_ci[0]) if not np.isnan(pitch_ci[0]) else 0.0,
                        "max": float(pitch_ci[1]) if not np.isnan(pitch_ci[1]) else 350.0
                    }
                },
                "F3_Pitch": {
                    "F3_Pitch": {
                        "enabled": True,
                        "min": float(f3_pitch_ci[0]) if not np.isnan(f3_pitch_ci[0]) else 1.0,
                        "max": float(f3_pitch_ci[1]) if not np.isnan(f3_pitch_ci[1]) else 50.0
                    }
                },
                "F2_Pitch": {
                    "F2_Pitch": {
                        "enabled": True,
                        "min": float(f2_pitch_ci[0]) if not np.isnan(f2_pitch_ci[0]) else 1.0,
                        "max": float(f2_pitch_ci[1]) if not np.isnan(f2_pitch_ci[1]) else 30.0
                    }
                },
                "F1_Pitch": {
                    "F1_Pitch": {
                        "enabled": True,
                        "min": float(f1_pitch_ci[0]) if not np.isnan(f1_pitch_ci[0]) else 1.0,
                        "max": float(f1_pitch_ci[1]) if not np.isnan(f1_pitch_ci[1]) else 15.0
                    }
                },
                "Size": {"Size": {"enabled": True, "min": -4.0, "max": 4.0}},
                "Weight": {
                    "Weight": {
                        "enabled": True,
                        "min": float(weight_ci[0]) if not np.isnan(weight_ci[0]) else 0.0,
                        "max": float(weight_ci[1]) if not np.isnan(weight_ci[1]) else 4.0e-7
                    }
                }
            }

            for path in output_paths:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)
                    print(f"Exported target JSON file: {path}")
                except Exception as ex:
                    print(f"Error exporting to {path}: {ex}", file=sys.stderr)

        # Output paths
        output_paths_male = [os.path.join(script_dir, "target_male.json")]
        output_paths_female = [os.path.join(script_dir, "target_female.json")]

        output_paths_male = list(set(os.path.abspath(p) for p in output_paths_male))
        output_paths_female = list(set(os.path.abspath(p) for p in output_paths_female))

        if any(m_data[col] for col in headers[1:]):
            export_group_targets(m_data, output_paths_male)
        if any(f_data[col] for col in headers[1:]):
            export_group_targets(f_data, output_paths_female)

    except Exception as e:
        print(f"Error writing CSV file '{output_csv}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()