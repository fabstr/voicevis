import os
import tempfile
import wave

def save_to_temp_wav(pcm_bytes, sample_rate):
    # 1. Generate a path in the system's temporary directory
    temp_dir = tempfile.gettempdir()
    temp_name = tempfile.gettempprefix();
    wav_filepath = os.path.join(temp_dir, "voicevis" + temp_name + ".wav")

    # 2. Open the file in binary write mode ('wb')
    with wave.open(wav_filepath, 'wb') as wav_file:
        # 3. Configure the WAV header parameters
        wav_file.setnchannels(1)  # 1 channel (Mono)
        wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
        wav_file.setframerate(sample_rate)  # e.g., 44100 Hz

        # 4. Write the raw PCM data
        wav_file.writeframes(pcm_bytes)

    print(f"WAV file saved to: {wav_filepath}")
    return wav_filepath
