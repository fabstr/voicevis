import queue

import numpy as np
from PyQt6 import QtCore

from signal_processing.AudioFeatures import FeatureSnapshot


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
        self.total_samples_processed = 0

    def run(self):
        # [NEW] Keep running if is_running is True OR if there is still data in the queue
        while self.is_running or not self.audio_queue.empty():
            try:
                # [NEW] Lower the timeout to 0.1 so the thread can exit quickly when done
                pcm_bytes = self.audio_queue.get(timeout=0.1)

                new_samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                if len(new_samples) == 0:
                    continue

                # Shift buffer and append new samples
                self.sliding_buffer = np.roll(self.sliding_buffer, -len(new_samples))
                self.sliding_buffer[-len(new_samples):] = new_samples

                # Track time based on samples processed
                self.total_samples_processed += len(new_samples)
                current_time = self.total_samples_processed / self.sample_rate

                # Wait until buffer is at least half full to avoid early noise
                if self.total_samples_processed > (self.window_size_samples / 2):
                    results = self.extractor.analyzePCM(self.sliding_buffer, self.sample_rate)

                    if results and hasattr(results, 'pitch') and len(results.pitch.x) > 0:
                        latest_point = FeatureSnapshot(
                            time=current_time,

                            # Independent Plots
                            loudness=results.loudness.y[-1],
                            pitch=results.pitch.y[-1],

                            # Individual Formants
                            F1=results.F1.y[-1],
                            F2=results.F2.y[-1],
                            F3=results.F3.y[-1],

                            # Spectral Slopes
                            slopes=results.slopes.y[-1],

                            F1_Pitch = results.F1_Pitch.y[-1] if len(results.F1_Pitch.y) > 0 else None,
                            F2_Pitch = results.F2_Pitch.y[-1] if len(results.F2_Pitch.y) > 0 else None,
                            F3_Pitch = results.F3_Pitch.y[-1] if len(results.F3_Pitch.y) > 0 else None,

                            F1_Pitch_BW = results.F1_Pitch_BW.y[-1] if len(results.F1_Pitch_BW.y) > 0 else None,
                            F2_Pitch_BW = results.F2_Pitch_BW.y[-1] if len(results.F2_Pitch_BW.y) > 0 else None,
                            F3_Pitch_BW = results.F3_Pitch_BW.y[-1] if len(results.F3_Pitch_BW.y) > 0 else None,

                            F1_IBW=results.F1_IBW.y[-1] if len(results.F1_IBW.y) > 0 else None,
                            F2_IBW=results.F2_IBW.y[-1] if len(results.F2_IBW.y) > 0 else None,
                            F3_IBW=results.F3_IBW.y[-1] if len(results.F3_IBW.y) > 0 else None,
                            size=results.size.y[-1] if len(results.size.y) > 0 else None,
                        )
                        self.new_data_point.emit(latest_point)

            except queue.Empty:
                continue
            # except Exception as e:
            #     pass
                # print(f"Real-Time Worker Error: {e}")

    def stop(self):
        self.is_running = False