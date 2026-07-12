import queue

import numpy as np
from PyQt6 import QtCore

from signal_processing.AudioFeatures import FeatureSnapshot, SpectrogramData
from signal_processing.AudioFeatureExtractor import nperseg, noverlap


class RealTimeAnalysisWorker(QtCore.QThread):
    new_data_point = QtCore.pyqtSignal(FeatureSnapshot)

    def __init__(self, extractor, audio_queue, sample_rate=44100):
        super().__init__()
        self.extractor = extractor
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.is_running = True

        # 500ms sliding window buffer to give openSMILE enough context
        self.window_size_samples = int(self.sample_rate * 0.5)
        self.sliding_buffer = np.zeros(self.window_size_samples, dtype=np.float32)

        # Set an analysis step size (e.g., 100ms = 10 FPS)
        self.analysis_step_samples = int(self.sample_rate * 0.01)
        self.samples_since_last_analysis = 0
        self.total_samples_processed = 0

        # Tracks the last chronological point we emitted so we don't output duplicates
        self.last_emitted_time = 0.0

        self.nperseg = nperseg
        self.noverlap = noverlap

    def _safe_get_float(self, ts, idx):
        """Helper to extract a float from a TimeSeries at a given index safely."""
        if ts is None or not hasattr(ts, 'y') or len(ts.y) == 0:
            return 0.0
        return float(ts.y[idx]) if idx < len(ts.y) else float(ts.y[-1])

    def _safe_get_opt(self, ts, idx):
        """Helper to extract an Optional float from a TimeSeries safely."""
        if ts is None or not hasattr(ts, 'y') or len(ts.y) == 0:
            return None
        return float(ts.y[idx]) if idx < len(ts.y) else float(ts.y[-1])

    def run(self):
        while self.is_running or not self.audio_queue.empty():
            try:
                # Drain the queue to prevent the worker from falling behind
                chunks = []

                # Block on the first get to avoid CPU spinning when idle
                chunks.append(self.audio_queue.get(timeout=0.1))

                # Instantly grab any backlogged chunks so we process the freshest data
                while not self.audio_queue.empty():
                    try:
                        chunks.append(self.audio_queue.get_nowait())
                    except queue.Empty:
                        break

                # Combine all backlogged chunks into a single array
                pcm_bytes = b"".join(chunks)
                new_samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                if len(new_samples) == 0:
                    continue

                # --- THE FIX ---
                # If the backlog is larger than our entire sliding window,
                # just take the newest samples that fit into the window.
                if len(new_samples) >= self.window_size_samples:
                    self.sliding_buffer[:] = new_samples[-self.window_size_samples:]
                else:
                    # Shift buffer and append new samples
                    self.sliding_buffer = np.roll(self.sliding_buffer, -len(new_samples))
                    self.sliding_buffer[-len(new_samples):] = new_samples
                # ---------------

                # Track time based on samples processed
                self.total_samples_processed += len(new_samples)
                self.samples_since_last_analysis += len(new_samples)
                current_time = self.total_samples_processed / self.sample_rate

                # Wait until buffer is at least half full to avoid early noise
                if self.total_samples_processed > (self.window_size_samples / 2):

                    # Throttling: Only run the heavy analysis if our step threshold is met
                    if self.samples_since_last_analysis >= self.analysis_step_samples:
                        self.samples_since_last_analysis = 0  # Reset counter

                        results = self.extractor.analyzePCM(self.sliding_buffer, self.sample_rate)

                        if results and hasattr(results, 'pitch') and len(results.pitch.x) > 0:

                            # Determine the exact chronological start time of the sliding buffer
                            buffer_duration = self.window_size_samples / self.sample_rate
                            buffer_start_time = current_time - buffer_duration

                            num_points = len(results.pitch.x)

                            # Iterate through every point returned in the current analysis frame
                            for i in range(num_points):
                                point_rel_time = results.pitch.x[i]
                                point_abs_time = buffer_start_time + point_rel_time

                                # Only emit points newer than what we've already dispatched
                                if point_abs_time > self.last_emitted_time:

                                    # --- LIVE SPECTROGRAM SLICING ---
                                    latest_spec = None
                                    if hasattr(results, 'spectrogram') and results.spectrogram.magnitude_db.size > 0:
                                        spec_db = results.spectrogram.magnitude_db
                                        spec_x = results.spectrogram.x

                                        # Align the spectrogram time bin to the current point
                                        if len(spec_x) == num_points and i < spec_db.shape[1]:
                                            col_idx = i
                                        else:
                                            col_idx = (np.abs(spec_x - point_rel_time)).argmin() if len(
                                                spec_x) > 0 else -1

                                        latest_spec = SpectrogramData(
                                            x=np.array([point_abs_time]),
                                            y=results.spectrogram.y,
                                            magnitude_db=spec_db[:, col_idx:col_idx + 1]
                                        )
                                    # --------------------------------

                                    latest_point = FeatureSnapshot(
                                        time=point_abs_time,
                                        pitch=self._safe_get_float(results.pitch, i),
                                        loudness=self._safe_get_float(results.loudness, i),
                                        slopes=self._safe_get_float(results.slopes, i),
                                        jitter=self._safe_get_float(results.jitter, i),
                                        shimmer=self._safe_get_float(results.shimmer, i),
                                        weight_instantaneous=self._safe_get_float(results.weight_instantaneous, i),
                                        weight_333ms_max=0,
                                        pitch_5s_mean=0,
                                        size_5s_mean=0,

                                        # Individual Formants
                                        F1=self._safe_get_float(results.F1, i),
                                        F2=self._safe_get_float(results.F2, i),
                                        F3=self._safe_get_float(results.F3, i),

                                        # Weight
                                        H1_H2=self._safe_get_float(results.H1_H2, i),
                                        H1_H3=self._safe_get_float(results.H1_H3, i),
                                        H1_H4=self._safe_get_float(results.H1_H4, i),
                                        H1_A3=self._safe_get_float(results.H1_A3, i),

                                        F1_Pitch=self._safe_get_opt(results.F1_Pitch, i),
                                        F2_Pitch=self._safe_get_opt(results.F2_Pitch, i),
                                        F3_Pitch=self._safe_get_opt(results.F3_Pitch, i),

                                        size=self._safe_get_opt(results.size, i),

                                        spectrogram=latest_spec
                                    )

                                    self.new_data_point.emit(latest_point)
                                    self.last_emitted_time = point_abs_time

            except queue.Empty:
                continue

    def stop(self):
        self.is_running = False