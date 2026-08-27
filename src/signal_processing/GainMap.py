"""Level changes everything downstream sees, but the buffer never gets.

A gain is a number of decibels over a stretch of the recording. Unlike
:mod:`AudioEdit`, nothing here touches the buffer the user recorded: the map is
applied to a *copy* on its way to the analysis, to playback and to an export.
Keeping the buffer itself at the recorded level is what makes a gain adjustable
rather than accumulating -- every application multiplies the original samples,
never the last result -- and it is why the file the audio was loaded from is
never written.

The map holds non-overlapping segments, in seconds, sorted by start. A segment
may run to ``inf`` -- that is what "the whole recording" means, so audio
recorded onto the end later is covered too. Applying a gain over a range that
already carries one replaces it there, and only there.

Cutting and moving audio take the gains with them, so a segment goes on
describing the same audio after an edit as it did before.
"""

import logging
from dataclasses import dataclass

import numpy as np

#: Mono signed 16-bit, the format the recording buffer is in.
DTYPE = '<i2'
FULL_SCALE = 32767

#: Below this a gain is not worth keeping: 0.05 dB is neither audible nor
#: measurable, and keeping it would leave a segment that does nothing.
NEGLIGIBLE_DB = 0.05

#: Segment edges are only ever compared, never accumulated, so this is small
#: enough to sit well inside one sample at any sample rate.
_EPSILON = 1e-9

INFINITY = float('inf')


def to_factor(db: float) -> float:
    """The amplitude factor a decibel figure asks for."""
    return float(10.0 ** (db / 20.0))


@dataclass(frozen=True)
class GainSegment:
    """``db`` decibels, applied from ``start`` up to (but not including) ``end``."""

    start: float
    end: float
    db: float

    @property
    def covers_everything(self) -> bool:
        return self.start <= 0.0 and self.end == INFINITY


class GainMap:
    """The gains in force in one session."""

    def __init__(self, segments=None):
        self._segments: list[GainSegment] = list(segments or [])

    # --- State -----------------------------------------------------------

    def __bool__(self) -> bool:
        return bool(self._segments)

    @property
    def is_empty(self) -> bool:
        return not self._segments

    def segments(self) -> list[GainSegment]:
        return list(self._segments)

    def copy(self) -> "GainMap":
        return GainMap(self._segments)

    def clear(self) -> bool:
        """Forget every gain. Returns False if there was nothing to forget."""
        if not self._segments:
            return False
        self._segments = []
        return True

    def gain_at(self, when: float) -> float:
        for segment in self._segments:
            if segment.start <= when < segment.end:
                return segment.db
        return 0.0

    def uniform_gain(self, start: float, end: float):
        """The one gain in force over ``start``..``end``, or None if it varies."""
        found = None
        for point in self._probes(start, end):
            db = self.gain_at(point)
            if found is None:
                found = db
            elif db != found:
                return None
        return found if found is not None else 0.0

    def _probes(self, start, end):
        """Points that between them meet every gain over ``start``..``end``."""
        points = [start]
        for segment in self._segments:
            for edge in (segment.start, segment.end):
                if start < edge < end:
                    points.append(edge)
                    points.append(edge - _EPSILON)
        return points

    # --- Editing ---------------------------------------------------------

    def set_gain(self, start: float, end: float, db: float) -> bool:
        """Apply ``db`` over ``start``..``end``. Returns False if nothing changed.

        A gain of 0 dB removes whatever was in force over the range: that is the
        way back, since a gain is not part of the undo history.
        """
        start = max(0.0, float(start))
        end = float(end)
        if end <= start:
            return False

        kept = _without(self._segments, start, end)
        if abs(db) >= NEGLIGIBLE_DB:
            kept.append(GainSegment(start, end, float(db)))

        after = _tidied(kept)
        if after == self._segments:
            return False

        self._segments = after
        logging.debug("Gain %+.1f dB over %.3fs..%.3fs", db, start, end)
        return True

    def cut(self, start: float, end: float):
        """Follow a cut of ``start``..``end``.

        The gains over the cut range go with the audio that carried them, and
        everything after the cut shifts earlier by as much as the audio does.
        """
        start, end = float(start), float(end)
        span = end - start
        if span <= 0:
            return

        remaining = []
        for segment in self._segments:
            head_end = min(segment.end, start)
            if head_end > segment.start:
                remaining.append(GainSegment(segment.start, head_end, segment.db))
            if segment.end > end:
                tail_start = max(0.0, max(segment.start, end) - span)
                tail_end = segment.end - span if segment.end != INFINITY else INFINITY
                remaining.append(GainSegment(tail_start, tail_end, segment.db))

        self._segments = _tidied(remaining)

    def move(self, start: float, end: float, delta: float):
        """Follow a move of ``start``..``end`` by ``delta``.

        The gains travel with the audio, leaving the source range -- which is
        left silent -- without them, and overwriting whatever gain was in force
        where the audio lands.
        """
        start, end = float(start), float(end)
        if not delta or end <= start:
            return

        travelling = []
        for segment in self._segments:
            low = max(segment.start, start)
            high = min(segment.end, end)
            if high > low:
                # Dragging past the start clips the front, as the audio is clipped.
                travelling.append(
                    GainSegment(max(0.0, low + delta), high + delta, segment.db))

        destination = (max(0.0, start + delta), end + delta)
        staying = _without(_without(self._segments, start, end), *destination)
        self._segments = _tidied(staying + travelling)

    # --- Application -----------------------------------------------------

    def apply(self, audio_bytes, sample_rate: int, offset_seconds: float = 0.0):
        """``audio_bytes`` with the gains applied, and whether it had to clamp.

        ``offset_seconds`` says where this run of samples sits in the recording,
        so a chunk read while recording can be gained on its way past. An empty
        map hands the audio straight back rather than copying it.
        """
        if self.is_empty or not audio_bytes:
            return audio_bytes, False

        samples = np.frombuffer(audio_bytes, dtype=DTYPE).astype(np.float32)
        for low, high, factor in self._slices(len(samples), sample_rate, offset_seconds):
            samples[low:high] *= factor

        clipped = bool(np.any(np.abs(samples) > FULL_SCALE))
        if clipped:
            np.clip(samples, -FULL_SCALE, FULL_SCALE, out=samples)

        return np.round(samples).astype(DTYPE).tobytes(), clipped

    def clips(self, audio_bytes, sample_rate: int) -> bool:
        """Whether applying the gains would drive any sample past full scale."""
        if self.is_empty or not audio_bytes:
            return False

        samples = np.frombuffer(audio_bytes, dtype=DTYPE)
        for low, high, factor in self._slices(len(samples), sample_rate):
            span = samples[low:high]
            if span.size and float(np.abs(span.astype(np.float32)).max()) * factor > FULL_SCALE:
                return True
        return False

    def _slices(self, sample_count: int, sample_rate: int, offset_seconds: float = 0.0):
        """(low, high, factor) per segment, clipped to the samples in hand."""
        for segment in self._segments:
            low = _sample_index(segment.start - offset_seconds, sample_rate, sample_count)
            high = _sample_index(segment.end - offset_seconds, sample_rate, sample_count)
            if high > low:
                yield low, high, to_factor(segment.db)


def _sample_index(seconds: float, sample_rate: int, sample_count: int) -> int:
    if seconds == INFINITY:
        return sample_count
    return int(min(max(0, round(seconds * sample_rate)), sample_count))


def _without(segments, start, end) -> list[GainSegment]:
    """Every segment with ``start``..``end`` taken out of it."""
    kept = []
    for segment in segments:
        if segment.end <= start or segment.start >= end:
            kept.append(segment)
            continue
        if segment.start < start:
            kept.append(GainSegment(segment.start, start, segment.db))
        if segment.end > end:
            kept.append(GainSegment(end, segment.end, segment.db))
    return kept


def _tidied(segments) -> list[GainSegment]:
    """Sorted, with empty segments dropped and equal neighbours joined up."""
    ordered = sorted((s for s in segments if s.end > s.start), key=lambda s: s.start)
    joined: list[GainSegment] = []
    for segment in ordered:
        last = joined[-1] if joined else None
        if last is not None and last.db == segment.db and last.end >= segment.start:
            joined[-1] = GainSegment(last.start, max(last.end, segment.end), last.db)
        else:
            joined.append(segment)
    return joined
