import os


def save_to_file(save_path, annotations, source_file):
    with open(save_path, 'w', encoding='utf-8') as f:
        # Write header
        f.write(f"Source: {source_file}\n")
        f.write("-" * 80 + "\n")

        # Column headers
        f.write("Time\tFeature\tY-Value\tText\n")

        for annotation in annotations:
            try:
                # Extract attributes
                time_val = annotation.get('time', 0.0)
                y_val = annotation.get('y', 0.0)
                text_val = annotation.get('text', '')
                plot_name = annotation.get('plot', '')

                # Format time to 2 decimals
                formatted_time = f"{float(time_val):.2f}"

                # Format y to 4 figures (using .4g for 4 significant figures)
                formatted_y = f"{float(y_val):.4g}"

                # Write to file separated by tabs
                f.write(f"{formatted_time}\t{plot_name}\t{formatted_y}\t{text_val}\n")

            except (ValueError, TypeError, AttributeError) as item_error:
                print(f"Skipping malformed annotation marker: {item_error}")

def load_from_file(txt_file_path):
    with open(txt_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("The annotation file is empty.")

    # 1. Parse the source audio file
    source_line = lines[0].strip()
    if not source_line.startswith("Source: "):
        raise ValueError("Invalid format: Missing 'Source:' on the first line.")

    original_audio_path = source_line[len("Source: "):].strip()

    # --- [NEW] Fallback Path Logic ---
    # Extract just the filename (e.g., 'audio.wav') from the original path
    audio_filename = os.path.basename(original_audio_path)
    # Create a fallback path assuming the audio is in the same folder as the .txt file
    fallback_audio_path = os.path.join(os.path.dirname(txt_file_path), audio_filename)

    # Check both locations
    if os.path.exists(original_audio_path):
        active_audio_path = original_audio_path
    elif os.path.exists(fallback_audio_path):
        active_audio_path = fallback_audio_path
    else:
        return None, [], original_audio_path, fallback_audio_path

    results = []
    for line in lines[3:]:
        # Strip trailing newlines but keep tabs
        line = line.strip('\n')
        if not line:
            continue

        # Split by tab since save_annotations joined them with \t
        parts = line.split('\t')

        # Check if we have at least Time, Feature, Y, and Text
        if len(parts) >= 4:
            try:
                time_val = float(parts[0])
                plot_name = parts[1]
                y_val = float(parts[2])
                text_val = parts[3]
            except ValueError:
                print(f"Skipping malformed data row: {line}")
                continue

            results.append({
                "time": time_val,
                "y": y_val,
                "text": text_val,
                "plot": plot_name,
            })

    return active_audio_path, results, audio_filename, fallback_audio_path