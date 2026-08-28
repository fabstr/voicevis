"""Live analysis of the microphone stream while recording.

The extractor produces a frame every 10 ms, the same rate as the batch
analysis that runs once recording stops. This worker used to keep only the
newest frame of each pass and throw the rest away, so the live plots ran at
whatever rate the passes happened to complete at -- roughly 30 points a second
against the batch analysis' 100, which is why the finished recording always
looked so much more detailed than the live one.

It now emits every frame that covers audio not reported yet, so the live
timeline has the same resolution as the batch one. That costs nothing extra:
those frames were already computed and discarded. The pass rate now only sets
how soon a frame appears, not how many of them there are.
"""

import math
import queue

import numpy as np
from PyQt6 import QtCore

from signal_processing.AudioFeatureExtractor import calculate_spectrogram
from signal_processing.AudioFeatures import FeatureSnapshot, SpectrogramData
from signal_processing.ChunkedAnalysis import FRAME_MILLISECONDS, SPECTROGRAM_HOP_SAMPLES

#: Sliding window handed to the extractor, giving openSMILE enough context.
WINDOW_SECONDS = 0.5

#: Least audio that must arrive before another pass is worth running. Below
#: the caller's poll interval, so every batch of samples is analysed as it
#: lands rather than waiting for a second one.
ANALYSIS_STEP_SECONDS = 0.01

#: Frames within this of the last emitted one count as already reported.
#: Guards against float drift only.
_TIME_EPSILON = 1e-9

#: Snapshot fields that must always carry a value.
_REQUIRED_FIELDS = ("pitch", "loudness", "weight", "jitter", "shimmer",
                    "F1", "F2", "F3", "H1_H2", "H1_H3", "H1_H4", "H1_A3")

#: Snapshot fields that may be missing from a pass, left as None when they are.
_OPTIONAL_FIELDS = ("F1_Pitch", "F2_Pitch", "F3_Pitch", "size")


class RealTimeAnalysisWorker(QtCore.QThread):
    #: Every frame of one analysis pass, oldest first, as a list of
    #: :class:`FeatureSnapshot`. A list rather than one signal per frame, so a
    #: pass costs a single queued cross-thread call.
    new_data_points = QtCore.pyqtSignal(list)

    def __init__(self, extractor, audio_queue, sample_rate=44100):
        super().__init__()
        self.extractor = extractor
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.is_running = True

        self.window_size_samples = int(self.sample_rate * WINDOW_SECONDS)
        self.sliding_buffer = np.zeros(self.window_size_samples, dtype=np.float32)

        # The two analysis grids the batch run puts its results on. A pass
        # analyses a slice starting on each grid, so its frames and its
        # spectrogram columns land where the batch analysis would put them
        # rather than at whatever phase this pass happens to begin at.
        frame_samples, remainder = divmod(self.sample_rate * FRAME_MILLISECONDS, 1000)
        self.frame_hop_samples = frame_samples if remainder == 0 and frame_samples else 0
        self.spectrogram_hop_samples = SPECTROGRAM_HOP_SAMPLES

        self.analysis_step_samples = int(self.sample_rate * ANALYSIS_STEP_SECONDS)
        self.samples_since_last_analysis = 0
        self.total_samples_processed = 0

        #: Time of the newest frame handed out, so a frame the next pass sees
        #: again is not reported twice.
        self._last_emitted_time = None
        self._last_spectrogram_time = None

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
                self.total_samples_processed += num_new
                self.samples_since_last_analysis += num_new

                # Wait until buffer is at least half full to avoid early noise
                if self.total_samples_processed <= (self.window_size_samples / 2):
                    continue

                # Throttling: Only run the heavy analysis if our step threshold is met
                if self.samples_since_last_analysis < self.analysis_step_samples:
                    continue
                self.samples_since_last_analysis = 0

                # The buffer's last sample sits at this point in the recording,
                # so its first one sits a whole window earlier.
                window_start_samples = self.total_samples_processed - self.window_size_samples

                frame_start = self._align(window_start_samples, self.frame_hop_samples)
                results = self.extractor.analyzePCM(
                    self.sliding_buffer[frame_start - window_start_samples:],
                    self.sample_rate, with_spectrogram=False)

                spectrogram_start = self._align(window_start_samples,
                                                self.spectrogram_hop_samples)
                spectrogram = calculate_spectrogram(
                    self.sliding_buffer[spectrogram_start - window_start_samples:],
                    self.sample_rate)

                snapshots = self._build_snapshots(
                    results, frame_start / float(self.sample_rate),
                    spectrogram, spectrogram_start / float(self.sample_rate))
                if snapshots:
                    self.new_data_points.emit(snapshots)

            except queue.Empty:
                continue

    @staticmethod
    def _align(start_sample: int, hop_samples: int) -> int:
        """The first whole ``hop_samples`` step at or after ``start_sample``.

        A pass begins wherever the microphone's samples happened to fall, which
        is off both analysis grids. Skipping up to one step of audio puts the
        pass' results back on the grid the batch analysis uses, so the times do
        not drift between passes and the spectrogram's columns keep an even
        spacing -- the plot draws them evenly whatever their times say, so an
        uneven one stretches the image away from the curves behind it.
        """
        if hop_samples <= 0:
            return start_sample
        return start_sample + (-start_sample % hop_samples)

    def _build_snapshots(self, results, window_start: float,
                         spectrogram, spectrogram_start: float):
        """Every frame of ``results`` that covers audio not reported yet."""
        if results is None or not hasattr(results, 'pitch'):
            return []

        times = np.asarray(results.pitch.x, dtype=float)
        if times.size == 0:
            return []
        times = times + window_start

        if self._last_emitted_time is None:
            # The window starts out padded with silence; those frames sit
            # before the recording began and are not part of it.
            fresh = times >= 0.0
        else:
            fresh = times > self._last_emitted_time + _TIME_EPSILON

        indices = np.flatnonzero(fresh)
        if indices.size == 0:
            return []

        columns = self._spectrogram_columns(spectrogram, spectrogram_start)
        column_position = 0

        snapshots = []
        for index in indices:
            frame_time = float(times[index])

            column_data = None
            if column_position < len(columns) and columns[column_position][0] <= frame_time:
                column_time, column = columns[column_position]
                column_position += 1
                self._last_spectrogram_time = column_time
                column_data = SpectrogramData(
                    x=np.array([column_time]),
                    y=spectrogram.y,
                    magnitude_db=column,
                )

            snapshots.append(self._snapshot(results, int(index), frame_time, column_data))

        self._last_emitted_time = float(times[indices[-1]])
        return snapshots

    @staticmethod
    def _snapshot(results, index: int, frame_time: float, spectrogram):
        values = {name: _value_at(getattr(results, name, None), index)
                  for name in _REQUIRED_FIELDS + _OPTIONAL_FIELDS}
        # The consumer drops NaN values field by field; a required one the pass
        # did not produce at all is the same thing as far as it is concerned.
        for name in _REQUIRED_FIELDS:
            if values[name] is None:
                values[name] = math.nan
        return FeatureSnapshot(time=frame_time, spectrogram=spectrogram, **values)

    def _spectrogram_columns(self, spectrogram, window_start: float):
        """This pass's spectrogram columns that have not been reported yet.

        The spectrogram's hop is coarser than the feature frame rate, so each
        column goes out with the first frame at or after it and none is
        dropped -- the old code kept only the newest one per pass.
        """
        if spectrogram is None or np.size(spectrogram.magnitude_db) == 0:
            return []

        times = np.asarray(spectrogram.x, dtype=float) + window_start
        if times.size == 0:
            return []

        if self._last_spectrogram_time is None:
            fresh = times >= 0.0
        else:
            fresh = times > self._last_spectrogram_time + _TIME_EPSILON

        magnitude = spectrogram.magnitude_db
        # Copied out so that a one-column snapshot does not pin the whole matrix.
        return [(float(times[index]), magnitude[:, index:index + 1].copy())
                for index in np.flatnonzero(fresh)]

    def stop(self):
        self.is_running = False


def _value_at(series, index: int):
    """One frame's value, or None when the series does not reach that far."""
    if series is None:
        return None
    y = getattr(series, 'y', None)
    if y is None or index >= len(y):
        return None
    return float(y[index])
