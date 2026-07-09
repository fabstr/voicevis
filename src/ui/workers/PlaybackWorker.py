from PyQt6 import QtCore
import miniaudio
import logging
import os

class PlaybackWorker(QtCore.QThread):
    playback_finished = QtCore.pyqtSignal()

    def __init__(self, file_path, seek_frame):
        super().__init__()
        self.file_path = file_path
        self.seek_frame = seek_frame
        self.device = None
        self.stream = None
        self._is_running = True

    def run(self):
        try:
            if self.file_path is None or not os.path.exists(self.file_path):
                logging.warning(f"File {self.file_path} does not exist")
            else:
                self.stream = miniaudio.stream_file(self.file_path, seek_frame=self.seek_frame)
                self.device = miniaudio.PlaybackDevice()
                self.device.start(self.stream)

                # Keep thread alive while audio plays and stop wasn't requested
                while self._is_running and self.device.running:
                    self.msleep(50)  # Low overhead sleep

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
        # If it's still being stubborn, catching the ValueError allows the thread
        # to exit cleanly without crashing your UI console.
        if self.stream:
            try:
                self.stream.close()
            except ValueError:
                # The generator was still wrapping up its final yield cycle,
                # Python garbage collection will naturally discard it now anyway.
                pass
            self.stream = None