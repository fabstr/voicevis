import argparse
import os
import sys


def main():
    # Dynamically find the user's Desktop path (works on Windows, Mac, and Linux)
    default_input = os.path.join(os.path.expanduser("~"), "Desktop", "spectrum.txt")

    parser = argparse.ArgumentParser(description="Filter spectrum data by removing lines below an amplitude threshold.")
    parser.add_argument("threshold", type=float, help="Minimum amplitude in dB to keep.")
    parser.add_argument("-i", "--input", type=str, default=default_input,
                        help=f"Path to input file. Default is: {default_input}")
    parser.add_argument("-o", "--output", type=str,
                        help="Path to output file. If omitted, prints to the screen.")

    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            # 1. Read and discard the first line (header)
            try:
                next(f)
            except StopIteration:
                print("Error: The file is empty.", file=sys.stderr)
                sys.exit(1)

            filtered_lines = []

            # 2. Process the remaining lines
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue  # Skip empty lines

                parts = stripped_line.split()
                if len(parts) >= 2:
                    try:
                        # Amplitude is the second column
                        amplitude = float(parts[1])

                        # 3. Filter out amplitudes below the threshold
                        if amplitude >= args.threshold:
                            filtered_lines.append(stripped_line)
                    except ValueError:
                        print(f"Warning: Could not parse numbers in line -> '{stripped_line}'", file=sys.stderr)

    except FileNotFoundError:
        print(f"Error: Could not find the file at '{args.input}'.", file=sys.stderr)
        sys.exit(1)

    # Output the results
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f_out:
            for line in filtered_lines:
                f_out.write(line + '\n')
        print(f"Successfully wrote {len(filtered_lines)} lines to '{args.output}'.")
    else:
        for line in filtered_lines:
            print(line)


if __name__ == "__main__":
    main()