import queue

import numpy as np
from PyQt6 import QtCore

from signal_processing.AudioFeatures import FeatureSnapshot, SpectrogramData


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

                num_new = len(new_samples)

                if num_new >= self.window_size_samples:
                    # If incoming data exceeds or equals the buffer size,
                    # just overwrite the whole buffer with the newest samples.
                    self.sliding_buffer[:] = new_samples[-self.window_size_samples:]
                else:
                    # Normal operation: shift left and append to the end
                    self.sliding_buffer = np.roll(self.sliding_buffer, -num_new)
                    self.sliding_buffer[-num_new:] = new_samples

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

                            # --- LIVE SPECTROGRAM SLICING ---
                            # Extract only the latest column (time bin) of the spectrogram matrix
                            latest_spec = None
                            if hasattr(results, 'spectrogram') and results.spectrogram.magnitude_db.size > 0:
                                latest_spec = SpectrogramData(
                                    x=np.array([current_time]),  # Sync to the current snapshot time
                                    y=results.spectrogram.y,  # Keep the frequency bins intact
                                    magnitude_db=results.spectrogram.magnitude_db[:, -1:]  # Slice the last column
                                )
                            # --------------------------------

                            latest_point = FeatureSnapshot(
                                time=current_time,
                                pitch=results.pitch.get_last_y(),
                                loudness=results.loudness.get_last_y(),
                                weight=results.weight.get_last_y(),
                                jitter=results.jitter.get_last_y(),
                                shimmer=results.shimmer.get_last_y(),

                                # Individual Formants
                                F1=results.F1.get_last_y(),
                                F2=results.F2.get_last_y(),
                                F3=results.F3.get_last_y(),

                                # Weight
                                H1_H2=results.H1_H2.get_last_y(),
                                H1_H3=results.H1_H3.get_last_y(),
                                H1_H4=results.H1_H4.get_last_y(),
                                H1_A3=results.H1_A3.get_last_y(),

                                F1_Pitch=results.F1_Pitch.get_last_y() if len(results.F1_Pitch.y) > 0 else None,
                                F2_Pitch=results.F2_Pitch.get_last_y() if len(results.F2_Pitch.y) > 0 else None,
                                F3_Pitch=results.F3_Pitch.get_last_y() if len(results.F3_Pitch.y) > 0 else None,

                                size=results.size.get_last_y() if len(results.size.y) > 0 else None,

                                spectrogram=latest_spec
                            )
                            self.new_data_point.emit(latest_point)

            except queue.Empty:
                continue

    def stop(self):
        self.is_running = False