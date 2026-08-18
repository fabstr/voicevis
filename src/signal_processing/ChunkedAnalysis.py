"""Feature analysis that only re-runs on the audio that actually changed.

Re-analysing the whole buffer after every take or edit is the slow path: most
of that work reproduces results that are still valid. This module cuts the PCM
buffer into fixed-length chunks, keeps the features extracted from each one,
and calls the extractor again only for chunks whose audio differs from the last
run. Recording a few seconds onto the end of a five-minute buffer then costs
one chunk instead of thirty.

A chunk is analysed together with a little of the audio either side of it, so
the windowed algorithms -- openSMILE's frames, the STFTs, the LPC inverse
filter -- see the context they would have seen in a whole-buffer analysis. The
extra frames are trimmed off afterwards. That context is part of a chunk's
identity, so an edit invalidates the chunks either side of the one it lands in.

Features that depend on the whole timeline -- the rolling means -- are left out
of the per-chunk results and computed once on the assembled record. That is
both cheaper and the only way to get them right across a chunk boundary.

Nothing here knows about plots: :meth:`ChunkedAudioAnalysis.analyse` hands back
an ordinary :class:`AudioFeatures`, indistinguishable from a whole-buffer one.
"""

import hashlib
import logging
import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from signal_processing.AudioFeatures import (AudioFeatures, SignalTimeSeries,
                                             SpectrogramData)

#: Mono signed 16-bit, the format the recording buffer is in.
BYTES_PER_SAMPLE = 2

#: How much audio one chunk covers, before being snapped to the analysis grids
#: by :func:`aligned_chunk_samples`.
CHUNK_SECONDS = 10.0

#: The extractor's spectrogram hop, ``nperseg - noverlap`` in
#: :func:`AudioFeatureExtractor.calculate_spectrogram`.
SPECTROGRAM_HOP_SAMPLES = 1024

#: openSMILE's low-level descriptor step.
FRAME_MILLISECONDS = 10

#: How much neighbouring audio a chunk is analysed with, per side.
#:
#: A tenth of this covers the windowed transforms -- openSMILE's frames, the
#: 4096-sample STFT, the 50 ms LPC window. It is this wide because openSMILE's
#: jitter and shimmer track glottal periods across frames and take longer than
#: that to settle: measured against a whole-buffer analysis, half a second of
#: context left them differing over the first ~500 ms of each chunk, a second
#: brings that down to a few frames. Everything else -- pitch, the formants,
#: loudness, the harmonic ratios, the spectrogram -- comes out identical either
#: way. Widening it further does not converge any further; the two measures
#: depend on where the analysed segment begins.
CONTEXT_SECONDS = 1.0

#: Frame times sit on a 10 ms grid, so this only guards against float noise when
#: the context frames are trimmed away.
_TIME_TOLERANCE = 1e-6


class AnalysisCancelled(Exception):
    """Raised out of :meth:`ChunkedAudioAnalysis.analyse` when it is abandoned.

    The chunks already analysed stay in the cache. Each one still carries the
    digest of the audio it was made from, so a later run reuses whichever of
    them are still valid and redoes the rest.
    """


@dataclass
class _Chunk:
    """One chunk's audio identity and the features extracted from it.

    ``features`` are chunk-local: times start at zero regardless of where the
    chunk sits, and the offset is applied when the record is assembled.
    """

    start_sample: int
    n_samples: int
    digest: bytes
    features: AudioFeatures


class ChunkedAudioAnalysis:
    """A per-chunk cache of analysis results for one recording buffer.

    The cache is positional: chunk *i* covers the same byte range every run, and
    is reused when the audio in that range (plus its context) hashes the same as
    it did last time. Cutting audio out shifts everything after the cut, so the
    tail is re-analysed; silencing or overwriting a selection only invalidates
    what it touches.
    """

    def __init__(self, chunk_seconds: float = CHUNK_SECONDS,
                 context_seconds: float = CONTEXT_SECONDS):
        self.chunk_seconds = float(chunk_seconds)
        self.context_seconds = float(context_seconds)
        self._chunks: list[_Chunk] = []
        self._sample_rate = 0
        #: How the most recent run split its work, for logging and tests.
        self.last_analysed = 0
        self.last_reused = 0

    # --- State -----------------------------------------------------------

    def reset(self):
        """Forget everything, e.g. when a different recording is loaded."""
        self._chunks = []
        self._sample_rate = 0
        self.last_analysed = 0
        self.last_reused = 0

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def chunk_samples(self, sample_rate: int) -> int:
        """How long a chunk actually is at this sample rate, in samples."""
        return aligned_chunk_samples(self.chunk_seconds, sample_rate)

    # --- Analysis --------------------------------------------------------

    def analyse(self, audio_bytes, sample_rate: int,
                analyse_chunk: Callable[[np.ndarray, int], AudioFeatures],
                is_cancelled: Optional[Callable[[], bool]] = None) -> AudioFeatures:
        """Bring the cache up to date with ``audio_bytes`` and assemble a record.

        :param audio_bytes: The whole buffer, mono signed 16-bit PCM.
        :param sample_rate: Its sample rate. A change resets the cache.
        :param analyse_chunk: Called as ``(samples, sample_rate)`` for every
            chunk that has to be redone, with float samples in -1..1. It leaves
            out the timeline-wide features; the caller applies those to the
            assembled record.
        :param is_cancelled: Polled between chunks; raises
            :class:`AnalysisCancelled` when it returns True.
        """
        if sample_rate != self._sample_rate:
            self.reset()
            self._sample_rate = sample_rate

        view = memoryview(audio_bytes).cast('B')
        total_samples = len(view) // BYTES_PER_SAMPLE
        chunk_samples = self.chunk_samples(sample_rate)
        context_samples = max(0, int(round(self.context_seconds * sample_rate)))

        wanted = -(-total_samples // chunk_samples)  # ceil, without the float
        del self._chunks[wanted:]

        analysed = reused = 0
        for index in range(wanted):
            start = index * chunk_samples
            length = min(chunk_samples, total_samples - start)
            lead = min(context_samples, start)
            trail = min(context_samples, total_samples - start - length)
            digest = _digest(view, start - lead, lead + length + trail)

            cached = self._chunks[index] if index < len(self._chunks) else None
            if cached is not None and cached.digest == digest:
                reused += 1
                continue

            if is_cancelled is not None and is_cancelled():
                raise AnalysisCancelled()

            samples = _float_samples(view, start - lead, lead + length + trail)
            features = _trim(analyse_chunk(samples, sample_rate),
                             lead / float(sample_rate), length / float(sample_rate))
            chunk = _Chunk(start_sample=start, n_samples=length,
                           digest=digest, features=features)
            if cached is None:
                self._chunks.append(chunk)
            else:
                self._chunks[index] = chunk
            analysed += 1

        self.last_analysed, self.last_reused = analysed, reused
        logging.info("Chunked analysis: %d chunk(s) analysed, %d reused", analysed, reused)

        return self._assemble(sample_rate, total_samples / float(sample_rate))

    def _assemble(self, sample_rate: int, length_seconds: float) -> AudioFeatures:
        """Stitch the cached chunks back into one whole-recording record."""
        result = AudioFeatures(sample_rate=sample_rate, length_seconds=length_seconds)
        if not self._chunks:
            return result

        for name in _signal_field_names(self._chunks[0].features):
            xs, ys = [], []
            for chunk in self._chunks:
                series = getattr(chunk.features, name, None)
                if series is None:
                    continue
                x = np.asarray(series.x, dtype=float)
                y = np.asarray(series.y, dtype=float)
                count = min(len(x), len(y))
                if count == 0:
                    continue
                xs.append(x[:count] + chunk.start_sample / float(sample_rate))
                ys.append(y[:count])
            if xs:
                setattr(result, name,
                        SignalTimeSeries(x=np.concatenate(xs), y=np.concatenate(ys)))

        result.spectrogram = _concatenate_spectrograms(self._chunks, sample_rate)
        return result


# --- Helpers -------------------------------------------------------------

def aligned_chunk_samples(chunk_seconds: float, sample_rate: int) -> int:
    """``chunk_seconds`` in samples, snapped to the extractor's analysis grids.

    A chunk has to be a whole number of analysis steps, or the chunks do not
    tile the timeline. openSMILE's frames would drift off the 10 ms grid, and --
    far more visibly -- consecutive chunks would place their spectrogram bins at
    different phases, so a column is dropped or repeated at every boundary. The
    plot draws the spectrogram as an evenly spaced image, so those missing
    columns stretch it away from the curves it sits behind, and the error adds
    up over a long recording.

    At 44.1 kHz the two steps are 441 and 1024 samples and share no factors, so
    the grid is coarse: a requested 10 s becomes 10.24 s. Anything shorter than
    one step is rounded up to it rather than to nothing.
    """
    wanted = max(1, int(round(chunk_seconds * sample_rate)))

    step = SPECTROGRAM_HOP_SAMPLES
    frame, remainder = divmod(sample_rate * FRAME_MILLISECONDS, 1000)
    if remainder == 0 and frame > 0:
        step = math.lcm(step, frame)

    return max(step, int(round(wanted / step)) * step)


def _digest(view: memoryview, start_sample: int, n_samples: int) -> bytes:
    """A short hash of a byte range, used to tell whether a chunk changed."""
    low = start_sample * BYTES_PER_SAMPLE
    high = low + n_samples * BYTES_PER_SAMPLE
    return hashlib.blake2b(view[low:high], digest_size=16).digest()


def _float_samples(view: memoryview, start_sample: int, n_samples: int) -> np.ndarray:
    """A byte range as the float samples the extractor expects."""
    low = start_sample * BYTES_PER_SAMPLE
    high = low + n_samples * BYTES_PER_SAMPLE
    samples = np.frombuffer(view[low:high], dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def _signal_field_names(features: AudioFeatures):
    """Every AudioFeatures attribute that is a plain time series."""
    return [name for name, value in vars(features).items()
            if isinstance(value, SignalTimeSeries)]


def _trim(features: AudioFeatures, lead_seconds: float,
          duration_seconds: float) -> AudioFeatures:
    """Drop the context frames, leaving times relative to the chunk's start.

    The window is half-open so that a frame sitting exactly on a boundary
    belongs to one chunk only and does not come out duplicated.
    """
    low = lead_seconds - _TIME_TOLERANCE
    high = lead_seconds + duration_seconds - _TIME_TOLERANCE

    for name in _signal_field_names(features):
        series = getattr(features, name)
        x = np.asarray(series.x, dtype=float)
        y = np.asarray(series.y, dtype=float)
        count = min(len(x), len(y))
        x, y = x[:count], y[:count]
        keep = (x >= low) & (x < high)
        setattr(features, name, SignalTimeSeries(x=x[keep] - lead_seconds, y=y[keep]))

    features.spectrogram = _trim_spectrogram(getattr(features, 'spectrogram', None),
                                             low, high, lead_seconds)
    features.length_seconds = duration_seconds
    return features


def _trim_spectrogram(spectrogram, low: float, high: float,
                      lead_seconds: float) -> SpectrogramData:
    if spectrogram is None or np.size(spectrogram.magnitude_db) == 0:
        return SpectrogramData()

    x = np.asarray(spectrogram.x, dtype=float)
    magnitude = np.asarray(spectrogram.magnitude_db)
    columns = min(len(x), magnitude.shape[1])
    x, magnitude = x[:columns], magnitude[:, :columns]

    keep = (x >= low) & (x < high)
    # Held as float32: one chunk of 4097 bins is 14 MB in float64 and the cache
    # keeps every chunk alongside the assembled copy. The image is drawn in
    # float32 regardless.
    return SpectrogramData(
        x=x[keep] - lead_seconds,
        y=np.asarray(spectrogram.y, dtype=float),
        magnitude_db=np.ascontiguousarray(magnitude[:, keep], dtype=np.float32),
    )


def _concatenate_spectrograms(chunks, sample_rate: int) -> SpectrogramData:
    """Lay the chunks' spectrogram columns end to end on one time axis."""
    times, columns, frequencies = [], [], None

    for chunk in chunks:
        spectrogram = getattr(chunk.features, 'spectrogram', None)
        if spectrogram is None or np.size(spectrogram.magnitude_db) == 0:
            continue

        bins = np.asarray(spectrogram.y, dtype=float)
        if frequencies is None:
            frequencies = bins
        elif len(bins) != len(frequencies):
            # Only possible if the extractor changed its FFT size mid-cache.
            logging.warning("Skipping a spectrogram chunk: %d bins, expected %d",
                            len(bins), len(frequencies))
            continue

        times.append(np.asarray(spectrogram.x, dtype=float)
                     + chunk.start_sample / float(sample_rate))
        columns.append(spectrogram.magnitude_db)

    if frequencies is None:
        return SpectrogramData()

    return SpectrogramData(x=np.concatenate(times), y=frequencies,
                           magnitude_db=np.hstack(columns))
