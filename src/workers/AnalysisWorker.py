"""
Define a worker to perform analysis in a separate thread.
"""

import logging

from PyQt6 import QtCore

from signal_processing.AudioFeatureExtractor import apply_derived_features
from signal_processing.AudioFeatures import AudioFeatures
from signal_processing.ChunkedAnalysis import AnalysisCancelled, ChunkedAudioAnalysis
import numpy as np


class AnalysisWorker(QtCore.QThread):
    # Signals to communicate back to the main GUI thread safely
    result_ready = QtCore.pyqtSignal(AudioFeatures)
    error_occurred = QtCore.pyqtSignal(str)
    #: ``(samples_done, total_samples)`` as the chunked analysis walks the
    #: timeline. Not emitted on the whole-buffer path, which has no steps to
    #: report.
    progress = QtCore.pyqtSignal(int, int)

    def __init__(self, extractor, audio_bytes, sample_rate, cache: ChunkedAudioAnalysis = None):
        """
        :param extractor: Instance of AudioFeatureExtractor
        :param audio_bytes: Raw PCM audio data from memory
        :param sample_rate: The sampling rate of the audio data
        :param cache: Chunk cache to analyse through, so that only the audio
            that changed since the last run is looked at again. Without one the
            whole buffer is analysed, as it always was.
        """
        super().__init__()
        self.extractor = extractor
        self.audio_bytes = audio_bytes
        self.sample_rate = sample_rate
        self.cache = cache
        self._cancelled = False

    def cancel(self):
        """Give up at the next chunk boundary, emitting no result.

        Called when a further edit has already made this run's answer stale.
        Only the chunked path can stop part-way; a whole-buffer analysis runs to
        completion and its result is dropped instead.
        """
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        """This runs in a separate background thread."""
        try:
            results = self._analyse()
        except AnalysisCancelled:
            logging.debug("Analysis cancelled; a newer one is queued")
            return
        except Exception as error:
            logging.exception("Analysis failed")
            self.error_occurred.emit(str(error))
            return

        if not self._cancelled:
            # Emit the results back to the GUI
            self.result_ready.emit(results)

    def _analyse(self) -> AudioFeatures:
        if self.cache is not None:
            results = self.cache.analyse(self.audio_bytes, self.sample_rate,
                                         self.extractor.analyzeChunk,
                                         is_cancelled=lambda: self._cancelled,
                                         on_progress=self.progress.emit)
            return apply_derived_features(results)

        audio_array = np.frombuffer(self.audio_bytes, dtype=np.int16)
        audio_array = audio_array.astype(np.float32) / 32768.0
        return self.extractor.analyzePCM(audio_array, self.sample_rate)
