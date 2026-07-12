"""
Define a worker to perform analysis in a separate thread.
"""

from PyQt6 import QtCore

from signal_processing.AudioFeatures import AudioFeatures
import numpy as np
import logging

class AnalysisWorker(QtCore.QThread):
    # Signals to communicate back to the main GUI thread safely
    result_ready = QtCore.pyqtSignal(AudioFeatures)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, extractor, audio_bytes, sample_rate):
        """
        :param extractor: Instance of AudioFeatureExtractor
        :param audio_bytes: Raw PCM audio data from memory
        :param sample_rate: The sampling rate of the audio data
        """
        super().__init__()
        self.extractor = extractor
        self.audio_bytes = audio_bytes
        self.sample_rate = sample_rate

    def run(self):
        """This runs in a separate background thread."""
        audio_array = np.frombuffer(self.audio_bytes, dtype=np.int16)
        audio_array = audio_array.astype(np.float32) / 32768.0
        results = self.extractor.analyzePCM(audio_array, self.sample_rate)

        # Emit the results back to the GUI
        self.result_ready.emit(results)
