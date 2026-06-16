#!/usr/bin/env python3
import sys
import os
import argparse
import urllib.request
import re
import csv
from tqdm import tqdm
import time

def main():
    parser = argparse.ArgumentParser(description="Download and tag audio files from the Speech Accent Archive")
    parser.add_argument("-o", "--output", default="downloads", help="Directory where downloaded audio files and metadata CSV will be saved")
    parser.add_argument("-l", "--limit", type=int, default=20, help="Number of files to download (default: 20, set to 0 or negative for all)")
    args = parser.parse_known_args()[0]

    output_dir = args.output
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("Fetching speaker list from Speech Accent Archive...")
    # url = "https://accent.gmu.edu/browse_language.php?function=find&language=english"
    url = "https://accent.gmu.edu/browse_language.php?function=find"
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching speaker list: {e}", file=sys.stderr)
        sys.exit(1)

    # Regex to find speaker links and metadata:
    # <p><a href="browse_language.php?function=detail&speakerid=61">english1,</a> male, pittsburgh, pennsylvania, usa</p>
    pattern = re.compile(
        r'<p><a href="browse_language\.php\?function=detail&speakerid=(\d+)">([^<]+)</a>\s*(male|female),\s*([^<]+)</p>',
        re.IGNORECASE
    )
    
    matches = pattern.findall(html)
    if not matches:
        print("No speakers found on the page. The HTML structure might have changed.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(matches)} total speakers in Speech Accent Archive.")

    # Determine files to download
    limit = args.limit
    if limit > 0:
        matches = matches[:limit]
        print(f"Limiting to first {limit} speakers for download.")
    else:
        print("Downloading all speakers.")

    metadata = []
    
    # Process and download each speaker
    for speakerid, full_name, gender, location in tqdm(matches, desc="Downloading", unit="file"):
        original_name = full_name.replace(',', '').strip()
        gender = gender.strip().lower()
        location = location.strip()
        
        # Parse country (last part of location)
        location_parts = [p.strip() for p in location.split(',')]
        country = location_parts[-1] if location_parts else "unknown"
        
        # Parse language and number
        match_name = re.match(r'^([a-zA-Z]+)(\d+)$', original_name)
        if match_name:
            language = match_name.group(1)
            number = match_name.group(2)
        else:
            language = "english"
            number = "0"

        if language == "english" or language == "swedish":
                continue

        gender_char = 'M' if gender == 'male' else 'F'
        country_clean = country.replace(' ', '_').lower()
        
        # New filename format: {language}{number}_{gender}_{country}.mp3
        tagged_filename = f"{language}{number}_{gender_char}_{country_clean}.mp3"
        local_path = os.path.join(output_dir, tagged_filename)
        
        # Download audio
        audio_url = f"https://accent.gmu.edu/soundtracks/{original_name}.mp3"
        try:
            req_audio = urllib.request.Request(
                audio_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req_audio) as response_audio:
                with open(local_path, 'wb') as out_file:
                    out_file.write(response_audio.read())
                    
            metadata.append({
                "Filename": tagged_filename,
                "Original_Name": original_name,
                "Gender": gender_char,
                "Language": language,
                "Number": number,
                "Country": country,
                "Location": location,
                "SpeakerID": speakerid
            })
        except Exception as e:
            tqdm.write(f"Error downloading {original_name} from {audio_url}: {e}")

    # Write metadata.csv
    csv_path = os.path.join(output_dir, "metadata.csv")
    csv_headers = ["Filename", "Original_Name", "Gender", "Language", "Number", "Country", "Location", "SpeakerID"]
    try:
        with open(csv_path, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=csv_headers)
            writer.writeheader()
            writer.writerows(metadata)
        print(f"\nMetadata successfully saved to: {csv_path}")
    except Exception as e:
        print(f"Error saving metadata CSV: {e}", file=sys.stderr)

if __name__ == '__main__':
    main()
