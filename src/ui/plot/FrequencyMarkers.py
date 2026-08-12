"""User-placed reference lines at particular frequencies.

Markers are application-wide, like the series palette: 220 Hz is 220 Hz on every
plot that has a frequency axis, so a marker added on the spectrogram also shows
up on the spectrum slice, and in every open window.

The store is deliberately just a sorted list of frequencies plus a signal. Which
way round a marker is drawn is a property of the plot, not of the marker: see
``PlotConfig.frequency_axis``.
"""

from PyQt6 import QtCore

#: Two markers closer together than this are treated as the same one.
MERGE_TOLERANCE_HZ = 0.5

MIN_HZ = 1.0
MAX_HZ = 100000.0


class FrequencyMarkerStore(QtCore.QObject):
    """The set of marked frequencies, shared by every plot."""

    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = []

    def values(self):
        return list(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, hz):
        return self.nearest(hz, MERGE_TOLERANCE_HZ) is not None

    # --- Editing ---------------------------------------------------------

    def add(self, hz) -> bool:
        """Add a marker. Returns False if it was out of range or a duplicate."""
        hz = _clean(hz)
        if hz is None or self.nearest(hz, MERGE_TOLERANCE_HZ) is not None:
            return False
        self._values.append(hz)
        self._values.sort()
        self.changed.emit()
        return True

    def remove(self, hz) -> bool:
        existing = self.nearest(hz, MERGE_TOLERANCE_HZ)
        if existing is None:
            return False
        self._values.remove(existing)
        self.changed.emit()
        return True

    def move(self, hz_from, hz_to) -> bool:
        """Move a marker. Used both by dragging and by typing an exact value."""
        existing = self.nearest(hz_from, MERGE_TOLERANCE_HZ)
        target = _clean(hz_to)
        if existing is None or target is None:
            return False
        if existing == target:
            return False

        self._values.remove(existing)
        # Dropping one marker onto another leaves a single marker there.
        if self.nearest(target, MERGE_TOLERANCE_HZ) is None:
            self._values.append(target)
        self._values.sort()
        self.changed.emit()
        return True

    def clear(self):
        if not self._values:
            return
        self._values.clear()
        self.changed.emit()

    # --- Lookup ----------------------------------------------------------

    def nearest(self, hz, tolerance=None):
        """The marker closest to ``hz``, or None if none is within tolerance."""
        try:
            hz = float(hz)
        except (TypeError, ValueError):
            return None
        if not self._values:
            return None

        closest = min(self._values, key=lambda v: abs(v - hz))
        if tolerance is not None and abs(closest - hz) > tolerance:
            return None
        return closest

    # --- Persistence -----------------------------------------------------

    def to_list(self):
        return list(self._values)

    def restore(self, values):
        """Replace everything, skipping anything unusable."""
        cleaned = []
        for value in values or []:
            hz = _clean(value)
            if hz is not None and all(abs(hz - v) > MERGE_TOLERANCE_HZ for v in cleaned):
                cleaned.append(hz)
        cleaned.sort()

        if cleaned == self._values:
            return
        self._values = cleaned
        self.changed.emit()


def _clean(hz):
    """A usable frequency, or None."""
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return None
    if not (MIN_HZ <= hz <= MAX_HZ):
        return None
    return hz


#: The one store every plot reads from.
MARKERS = FrequencyMarkerStore()
