from PyQt6 import QtCore
import miniaudio
import logging


class PlaybackWorker(QtCore.QThread):
    playback_finished = QtCore.pyqtSignal()

    def __init__(self, samples, seek_frame=0, sample_rate=44100, sample_format=miniaudio.SampleFormat.SIGNED16):
        """
        :param samples: Raw PCM mono audio data (bytes, bytearray, array.array, or numpy.tobytes())
        :param seek_frame: Frame to start playback from
        :param sample_rate: The playback frequency (Hz)
        :param sample_format: The bit depth/format of the raw samples
        """
        super().__init__()

        # memoryview provides zero-copy slicing for bytes/bytearrays
        self.samples = memoryview(samples)
        self.seek_frame = seek_frame
        self.sample_rate = sample_rate
        self.sample_format = sample_format

        # Hardcode channels to 1 (Mono)
        self.channels = 1

        # Determine sample width based on miniaudio format enum
        format_widths = {
            miniaudio.SampleFormat.UNSIGNED8: 1,
            miniaudio.SampleFormat.SIGNED16: 2,
            miniaudio.SampleFormat.SIGNED32: 4,
            miniaudio.SampleFormat.FLOAT32: 4
        }
        self.sample_width = format_widths.get(self.sample_format, 2)

        self.device = None
        self.stream = None
        self._is_running = True

    def _sample_generator(self):
        """Generator that streams frames of mono audio dynamically upon request."""
        # 1. Miniaudio initializes the generator by catching the first yield
        required_frames = yield b""

        # For mono, bytes per frame is simply the sample width
        bytes_per_frame = self.channels * self.sample_width
        current_idx = self.seek_frame * bytes_per_frame
        total_bytes = len(self.samples)

        # 2. Miniaudio repeatedly pulls required chunks via .send()
        while True:
            required_bytes = required_frames * bytes_per_frame
            end_idx = min(current_idx + required_bytes, total_bytes)

            chunk = self.samples[current_idx:end_idx]
            current_idx = end_idx

            # Stop if we run out of samples
            if not chunk or len(chunk) == 0:
                break

            required_frames = yield chunk

    def run(self):
        try:
            if not self.samples:
                logging.warning("Sample array is empty")
                return

            # Instantiate the generator and prime it up to the first yield
            self.stream = self._sample_generator()
            next(self.stream)

            # Explicitly define playback parameters for mono audio
            self.device = miniaudio.PlaybackDevice(
                output_format=self.sample_format,
                nchannels=self.channels,
                sample_rate=self.sample_rate
            )

            self.device.start(self.stream)

            # Keep thread alive while audio plays and stop wasn't requested
            while self._is_running and self.device.running:
                self.msleep(50)  # Low overhead sleep

        except Exception as e:
            logging.error(f"Playback error: {e}")
        finally:
            self.stop_backend()
            self.playback_finished.emit()

    def stop_backend(self):
        # 1. Break out of our local sleep loop immediately
        self._is_running = False

        # 2. Stop the device first. This forces miniaudio to stop pulling data
        # from the underlying generator stream.
        if self.device:
            self.device.stop()
            self.device = None  # Clear reference

        # 3. Clean up the stream generator safely.
        if self.stream:
            try:
                self.stream.close()
            except ValueError:
                pass
            self.stream = None