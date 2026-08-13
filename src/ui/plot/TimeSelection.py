"""The stretch of time the user has selected for editing.

One selection per session, shared by every plot that has a time axis, so
dragging one out on the pitch plot shows up on the spectrogram too.
"""

from PyQt6 import QtCore

#: A drag shorter than this is treated as a click, and clears the selection.
MIN_SPAN_SECONDS = 0.01


class TimeSelection(QtCore.QObject):
    """A start and an end, in seconds, or nothing."""

    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start = None
        self._end = None

    @property
    def active(self) -> bool:
        return self._start is not None

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def span(self) -> float:
        return (self._end - self._start) if self.active else 0.0

    def as_tuple(self):
        return (self._start, self._end) if self.active else None

    # --- Editing ---------------------------------------------------------

    def set_range(self, start, end):
        """Select from ``start`` to ``end``; a negligible span clears it."""
        try:
            low, high = sorted((float(start), float(end)))
        except (TypeError, ValueError):
            return

        low = max(0.0, low)
        if high - low < MIN_SPAN_SECONDS:
            self.clear()
            return

        if (low, high) == (self._start, self._end):
            return
        self._start, self._end = low, high
        self.changed.emit()

    def shift(self, delta: float):
        """Slide the selection along, keeping its length."""
        if not self.active:
            return
        self.set_range(max(0.0, self._start + delta), self._end + delta)

    def clear(self):
        if not self.active:
            return
        self._start = self._end = None
        self.changed.emit()
