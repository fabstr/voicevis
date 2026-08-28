"""The single owner of the analysed data and the current playback time.

Every plot reads through this object instead of holding its own reference to a
``SignalTimeSeries``. That matters because a re-analysis replaces those objects
wholesale -- the old controllers cached them and quietly kept drawing stale
arrays afterwards.

It is also the only place that appends live samples. Previously every visible
curve in every cell appended the same snapshot to the same shared series, so a
feature shown in two plots was recorded twice.
"""

import logging

import numpy as np
from PyQt6 import QtCore

from signal_processing.AudioFeatures import (AudioFeatures, FeatureSnapshot,
                                             SignalTimeSeries, SpectrogramData)
from ui.plot.TimeSelection import TimeSelection

#: Initial capacity of a growable live buffer, and its growth factor.
_INITIAL_CAPACITY = 1024
_GROWTH = 2

#: How far past its bound a bounded live buffer is allowed to run before it is
#: trimmed back. Trimming a batch at a time keeps the cost amortised: each pass
#: would otherwise shift the whole buffer along by a few frames.
_TRIM_SLACK_SECONDS = 10.0


class _GrowableSeries:
    """An append-friendly view of a SignalTimeSeries.

    Live recording appends one sample at a time. ``np.append`` reallocates on
    every call, which makes a long recording quadratic; doubling a capacity
    buffer keeps it linear.
    """

    __slots__ = ("_x", "_y", "_n")

    def __init__(self, series: SignalTimeSeries = None):
        x = np.asarray(series.x, dtype=float) if series is not None else np.empty(0)
        y = np.asarray(series.y, dtype=float) if series is not None else np.empty(0)
        self._n = min(len(x), len(y))

        capacity = max(_INITIAL_CAPACITY, self._n * _GROWTH)
        self._x = np.empty(capacity, dtype=float)
        self._y = np.empty(capacity, dtype=float)
        self._x[:self._n] = x[:self._n]
        self._y[:self._n] = y[:self._n]

    def append(self, x_value: float, y_value: float):
        if self._n == len(self._x):
            self._grow()
        self._x[self._n] = x_value
        self._y[self._n] = y_value
        self._n += 1

    def _grow(self):
        capacity = max(_INITIAL_CAPACITY, len(self._x) * _GROWTH)
        x, y = np.empty(capacity, dtype=float), np.empty(capacity, dtype=float)
        x[:self._n] = self._x[:self._n]
        y[:self._n] = self._y[:self._n]
        self._x, self._y = x, y

    @property
    def last_time(self):
        return self._x[self._n - 1] if self._n else None

    def trim_before(self, time_value: float):
        """Drop the samples older than ``time_value``."""
        keep_from = int(np.searchsorted(self._x[:self._n], time_value, side="left"))
        if keep_from <= 0:
            return
        remaining = self._n - keep_from
        self._x[:remaining] = self._x[keep_from:self._n]
        self._y[:remaining] = self._y[keep_from:self._n]
        self._n = remaining

    def views(self):
        return self._x[:self._n], self._y[:self._n]

    def to_series(self) -> SignalTimeSeries:
        x, y = self.views()
        return SignalTimeSeries(x=x.copy(), y=y.copy())


class _GrowableSpectrogram:
    """An append-friendly view of a SpectrogramData.

    Columns arrive one at a time while recording. ``np.hstack`` copies the
    whole matrix on every one, and at 4097 bins by ~43 columns a second that
    turns a couple of minutes of audio into hundreds of megabytes of copying
    per column. A doubling capacity buffer keeps it linear.

    Columns are stored as rows -- one row per time bin -- so appending writes
    into a contiguous slice, and ``magnitude_db`` is that block transposed.
    """

    __slots__ = ("_y", "_x", "_magnitude", "_n")

    def __init__(self, spectrogram: SpectrogramData = None):
        x = np.asarray(spectrogram.x, dtype=float) if spectrogram is not None else np.empty(0)
        magnitude = (np.asarray(spectrogram.magnitude_db, dtype=float)
                     if spectrogram is not None else np.empty((0, 0)))
        self._y = (np.asarray(spectrogram.y, dtype=float)
                   if spectrogram is not None else np.empty(0))

        rows = magnitude.shape[0] if magnitude.ndim == 2 and magnitude.shape[1] else 0
        self._n = min(len(x), magnitude.shape[1]) if rows else 0

        capacity = max(_INITIAL_CAPACITY, self._n * _GROWTH)
        self._x = np.empty(capacity, dtype=float)
        self._magnitude = np.empty((capacity, rows), dtype=float)
        self._x[:self._n] = x[:self._n]
        self._magnitude[:self._n] = magnitude[:, :self._n].T

    @property
    def bins(self) -> int:
        return self._magnitude.shape[1]

    def append(self, time: float, column: np.ndarray, frequencies=None) -> bool:
        """Add one column, or return False when it does not fit the bins."""
        column = np.asarray(column, dtype=float).reshape(-1)

        if self._n == 0:
            # Nothing to line up with yet, so this column sets the bins.
            self._magnitude = np.empty((len(self._x), len(column)), dtype=float)
            if frequencies is not None:
                self._y = np.asarray(frequencies, dtype=float)
        elif len(column) != self.bins:
            return False

        if self._n == len(self._x):
            self._grow()
        self._x[self._n] = time
        self._magnitude[self._n] = column
        self._n += 1
        return True

    def _grow(self):
        capacity = max(_INITIAL_CAPACITY, len(self._x) * _GROWTH)
        x = np.empty(capacity, dtype=float)
        magnitude = np.empty((capacity, self.bins), dtype=float)
        x[:self._n] = self._x[:self._n]
        magnitude[:self._n] = self._magnitude[:self._n]
        self._x, self._magnitude = x, magnitude

    def trim_before(self, time_value: float):
        """Drop the columns older than ``time_value``."""
        keep_from = int(np.searchsorted(self._x[:self._n], time_value, side="left"))
        if keep_from <= 0:
            return
        remaining = self._n - keep_from
        self._x[:remaining] = self._x[keep_from:self._n]
        self._magnitude[:remaining] = self._magnitude[keep_from:self._n]
        self._n = remaining

    def view(self) -> SpectrogramData:
        """The columns so far, as views rather than copies."""
        return SpectrogramData(x=self._x[:self._n], y=self._y,
                               magnitude_db=self._magnitude[:self._n].T)

    def to_data(self) -> SpectrogramData:
        view = self.view()
        return SpectrogramData(x=view.x.copy(), y=self._y,
                               magnitude_db=np.ascontiguousarray(view.magnitude_db))


class PlotDataHub(QtCore.QObject):
    """Owns the analysed features, the live buffers and the display time."""

    features_replaced = QtCore.pyqtSignal()
    time_changed = QtCore.pyqtSignal(float)

    def __init__(self, features: AudioFeatures = None, parent=None):
        super().__init__(parent)
        self._features = features or AudioFeatures()
        self._revision = 1
        self._dirty = False
        self._cache = {}
        self._live = {}
        self._live_spectrogram = None
        self._recording = False
        self._history_seconds = None
        self._next_trim_time = None
        self._current_time = 0.0
        #: The stretch of audio picked out for editing.
        self.selection = TimeSelection(self)

    # --- Features --------------------------------------------------------

    @property
    def features(self) -> AudioFeatures:
        return self._features

    def set_features(self, features: AudioFeatures):
        """Install a fresh analysis result, discarding any live buffers."""
        self._features = features or AudioFeatures()
        self._reset_live()
        self._bump()
        self.features_replaced.emit()

    def clear(self):
        self.set_features(AudioFeatures())
        self.set_time(0.0)

    @property
    def length_seconds(self) -> float:
        return float(getattr(self._features, "length_seconds", 0.0) or 0.0)

    # --- Change tracking -------------------------------------------------

    @property
    def revision(self) -> int:
        return self._revision

    def _bump(self):
        self._revision += 1
        self._cache.clear()
        self._dirty = True

    def take_dirty(self) -> bool:
        """True once after any data change; used to skip redundant redraws."""
        was_dirty, self._dirty = self._dirty, False
        return was_dirty

    # --- Reading ---------------------------------------------------------

    def _series(self, key: str):
        """The live buffer for ``key`` while recording, else its stored series."""
        if key in self._live:
            return self._live[key].views()
        series = getattr(self._features, key, None)
        if series is None or not hasattr(series, "x"):
            return None
        return np.asarray(series.x, dtype=float), np.asarray(series.y, dtype=float)

    def get_raw(self, key: str):
        """The series for ``key`` with NaNs intact, as an (x, y) pair."""
        pair = self._series(key)
        if pair is None:
            return np.empty(0), np.empty(0)
        x, y = pair
        n = min(len(x), len(y))
        return x[:n], y[:n]

    def get_xy(self, key: str):
        """The series for ``key`` with invalid frames dropped from both arrays.

        The mask is computed once over both arrays, unlike
        ``get_x_without_NaN``/``get_y_without_NaN`` which each recompute it.
        """
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        x, y = self.get_raw(key)
        if len(x) == 0:
            result = (x, y)
        else:
            valid = np.isfinite(x) & np.isfinite(y)
            result = (x[valid], y[valid]) if not valid.all() else (x, y)

        self._cache[key] = result
        return result

    def has_series(self, key: str) -> bool:
        return key in self._live or hasattr(self._features, key)

    def spectrogram(self):
        """The spectrogram, or None when there is nothing to draw."""
        if self._live_spectrogram is not None:
            spec = self._live_spectrogram.view()
        else:
            spec = getattr(self._features, "spectrogram", None)
        if spec is None or getattr(spec, "magnitude_db", None) is None:
            return None
        return spec if np.size(spec.magnitude_db) else None

    # --- Time ------------------------------------------------------------

    @property
    def current_time(self) -> float:
        return self._current_time

    def set_time(self, value: float):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        if value != self._current_time:
            self._current_time = value
            self.time_changed.emit(value)

    # --- Live recording --------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._recording

    def begin_recording(self, history_seconds: float = None):
        """Switch every signal series over to an append-friendly buffer.

        :param history_seconds: Keep only this much of the live data, dropping
            what falls behind it. Monitoring the microphone has no end and
            nothing to write the result to, so it bounds what it keeps;
            recording passes nothing and keeps the lot.
        """
        self._live = {
            field: _GrowableSeries(getattr(self._features, field))
            for field in _signal_fields(self._features)
        }
        self._live_spectrogram = _GrowableSpectrogram(
            getattr(self._features, "spectrogram", None))
        self._history_seconds = float(history_seconds) if history_seconds else None
        self._next_trim_time = None
        self._recording = True
        self._bump()

    def end_recording(self):
        """Materialise the live buffers back into the feature record."""
        for key, buffer in self._live.items():
            setattr(self._features, key, buffer.to_series())
        if self._live_spectrogram is not None:
            self._features.spectrogram = self._live_spectrogram.to_data()
        self._reset_live()
        self._bump()

    def discard_live(self):
        """Throw the live buffers away, leaving the feature record untouched.

        What monitoring the microphone produces is never kept: the session's
        own analysis has to come back exactly as monitoring found it.
        """
        self._reset_live()
        self._bump()

    def _reset_live(self):
        self._live.clear()
        self._live_spectrogram = None
        self._history_seconds = None
        self._next_trim_time = None
        self._recording = False

    def append_snapshot(self, snapshot: FeatureSnapshot):
        """Record one live analysis frame."""
        self.append_snapshots((snapshot,))

    def append_snapshots(self, snapshots):
        """Record a pass' worth of live analysis frames, oldest first.

        The only append path in the app. Taking the whole pass at once keeps
        the bookkeeping -- cache, revision, dirty flag -- to one round per
        pass rather than one per frame, which matters now that a pass carries
        every frame it analysed rather than only its newest.
        """
        if not snapshots:
            return
        if not self._recording:
            # Recording was never announced; fall back rather than lose data.
            self.begin_recording()

        newest = None
        for snapshot in snapshots:
            time = getattr(snapshot, "time", None)
            if time is None:
                continue

            for key, buffer in self._live.items():
                value = getattr(snapshot, key, None)
                if value is None:
                    continue
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if np.isnan(value):
                    continue
                if buffer.last_time == time:
                    continue
                buffer.append(time, value)

            self._append_spectrogram_column(snapshot, time)
            newest = time

        if newest is not None:
            if self._history_seconds is not None:
                self._trim_live(float(newest))
            self._cache.clear()
            self._dirty = True
            self._revision += 1

    def _trim_live(self, newest_time: float):
        """Drop live data that has fallen out of the history bound."""
        if self._next_trim_time is None:
            self._next_trim_time = newest_time + _TRIM_SLACK_SECONDS
            return
        if newest_time < self._next_trim_time:
            return

        limit = newest_time - self._history_seconds
        for buffer in self._live.values():
            buffer.trim_before(limit)
        if self._live_spectrogram is not None:
            self._live_spectrogram.trim_before(limit)
        self._next_trim_time = newest_time + _TRIM_SLACK_SECONDS

    def _append_spectrogram_column(self, snapshot: FeatureSnapshot, time: float):
        incoming = getattr(snapshot, "spectrogram", None)
        if incoming is None or getattr(incoming, "magnitude_db", None) is None:
            return
        if np.size(incoming.magnitude_db) == 0:
            return
        if self._live_spectrogram is None:
            return

        # A column sits on the spectrogram's own hop, not on the frame grid, so
        # it is filed at the time it came with rather than at the frame's.
        column_time = float(incoming.x[0]) if np.size(incoming.x) else time
        column = np.asarray(incoming.magnitude_db).reshape(-1)
        if not self._live_spectrogram.append(column_time, column, frequencies=incoming.y):
            logging.debug("Dropping live spectrogram column: %d rows, expected %d",
                          len(column), self._live_spectrogram.bins)


def _signal_fields(features: AudioFeatures):
    """Every AudioFeatures attribute that is a plain time series."""
    return [name for name, value in vars(features).items()
            if isinstance(value, SignalTimeSeries)]
