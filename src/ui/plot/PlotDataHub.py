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

from signal_processing.AudioFeatures import AudioFeatures, FeatureSnapshot, SignalTimeSeries
from ui.plot.TimeSelection import TimeSelection

#: Initial capacity of a growable live buffer, and its growth factor.
_INITIAL_CAPACITY = 1024
_GROWTH = 2


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

    def views(self):
        return self._x[:self._n], self._y[:self._n]

    def to_series(self) -> SignalTimeSeries:
        x, y = self.views()
        return SignalTimeSeries(x=x.copy(), y=y.copy())


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
        self._recording = False
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
        self._live.clear()
        self._recording = False
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

    def begin_recording(self):
        """Switch every signal series over to an append-friendly buffer."""
        self._live = {
            field: _GrowableSeries(getattr(self._features, field))
            for field in _signal_fields(self._features)
        }
        self._recording = True
        self._bump()

    def end_recording(self):
        """Materialise the live buffers back into the feature record."""
        for key, buffer in self._live.items():
            setattr(self._features, key, buffer.to_series())
        self._live.clear()
        self._recording = False
        self._bump()

    def append_snapshot(self, snapshot: FeatureSnapshot):
        """Record one live analysis frame. The only append path in the app."""
        time = getattr(snapshot, "time", None)
        if time is None:
            return
        if not self._recording:
            # Recording was never announced; fall back rather than lose data.
            self.begin_recording()

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
        self._cache.clear()
        self._dirty = True
        self._revision += 1

    def _append_spectrogram_column(self, snapshot: FeatureSnapshot, time: float):
        incoming = getattr(snapshot, "spectrogram", None)
        if incoming is None or getattr(incoming, "magnitude_db", None) is None:
            return
        if np.size(incoming.magnitude_db) == 0:
            return

        target = getattr(self._features, "spectrogram", None)
        if target is None:
            return

        column = np.asarray(incoming.magnitude_db).reshape(-1, 1)

        if np.size(target.magnitude_db) == 0 or len(target.x) == 0:
            target.x = np.array([time], dtype=float)
            target.y = np.asarray(incoming.y, dtype=float)
            target.magnitude_db = column
            return

        if column.shape[0] != target.magnitude_db.shape[0]:
            logging.debug("Dropping live spectrogram column: %d rows, expected %d",
                          column.shape[0], target.magnitude_db.shape[0])
            return

        target.x = np.append(target.x, time)
        target.magnitude_db = np.hstack((target.magnitude_db, column))


def _signal_fields(features: AudioFeatures):
    """Every AudioFeatures attribute that is a plain time series."""
    return [name for name, value in vars(features).items()
            if isinstance(value, SignalTimeSeries)]
