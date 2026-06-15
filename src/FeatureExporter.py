#!/usr/bin/env python3
import sys
import os
import argparse
import csv
import numpy as np

# Add the directory containing this script to sys.path so that imports from signal_processing work
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.TargetConfig import TargetConfig

def main():
    parser = argparse.ArgumentParser(description="Extract mean and median values of Pitch, F3/Pitch, F2/Pitch, F1/Pitch and Weight to CSV")
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
    audio_files = sorted([
        os.path.join(input_dir, f) for f in os.listdir(input_dir)
        if f.lower().endswith(extensions)
    ])

    if not audio_files:
        print(f"No audio files (.wav or .mp3) found in '{input_dir}'.")
        sys.exit(0)

    print(f"Found {len(audio_files)} audio files to process.")

    # Initialize extractor
    target_config = TargetConfig()
    extractor = AudioFeatureExtractor(target_config)

    # CSV headers
    headers = [
        "Filename",
        "Pitch_Mean", "Pitch_Median",
        "F3_Pitch_Mean", "F3_Pitch_Median",
        "F2_Pitch_Mean", "F2_Pitch_Median",
        "F1_Pitch_Mean", "F1_Pitch_Median",
        "Weight_Mean", "Weight_Median"
    ]

    try:
        with open(output_csv, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)

            for idx, file_path in enumerate(audio_files):
                filename = os.path.basename(file_path)
                print(f"[{idx+1}/{len(audio_files)}] Processing: {filename}...")
                
                try:
                    features = extractor.analyzeFile(file_path)
                    
                    def get_stats(series):
                        if series is not None and hasattr(series, 'y') and len(series.y) > 0:
                            return float(np.mean(series.y)), float(np.median(series.y))
                        return "", ""

                    pitch_mean, pitch_med = get_stats(features.pitch)
                    f3_pitch_mean, f3_pitch_med = get_stats(features.F3_Pitch)
                    f2_pitch_mean, f2_pitch_med = get_stats(features.F2_Pitch)
                    f1_pitch_mean, f1_pitch_med = get_stats(features.F1_Pitch)
                    weight_mean, weight_med = get_stats(features.slopes)

                    writer.writerow([
                        filename,
                        pitch_mean, pitch_med,
                        f3_pitch_mean, f3_pitch_med,
                        f2_pitch_mean, f2_pitch_med,
                        f1_pitch_mean, f1_pitch_med,
                        weight_mean, weight_med
                    ])
                except Exception as e:
                    print(f"Error processing {filename}: {e}", file=sys.stderr)
                    # Write row with filename and empty values for errors
                    writer.writerow([filename] + [""] * (len(headers) - 1))

        print(f"\nDone! Successfully wrote results to: {output_csv}")

    except Exception as e:
        print(f"Error writing CSV file '{output_csv}': {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
