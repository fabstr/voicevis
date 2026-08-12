"""Keeps every time-domain plot showing the same stretch of time.

The group owns one canonical X range and pushes it to its members, rather than
designating one plot as a master and calling ``setXLink`` on the rest. A master
has to be re-elected whenever plots are added, removed or reconfigured, and it
makes zooming asymmetric -- only the master's own range really counts. A group
is order-independent and lets a zoom on any member propagate to all the others.
"""

import logging

from PyQt6 import QtCore

MODE_IDLE = "idle"
MODE_PLAYING = "playing"
MODE_RECORDING = "recording"

#: Seconds of history shown while recording.
RECORD_WINDOW = 10.0
#: Seconds of empty space kept ahead of the playhead while recording.
RECORD_LOOKAHEAD = 1.0
#: Fraction of the view width at which playback pages forward.
PAGE_TRIGGER = 0.50


class TimeAxisSyncGroup(QtCore.QObject):
    """A set of view boxes sharing one X range."""

    range_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        #: view box -> which of its axes carries time ('x' or 'y')
        self._members = {}
        self._range = (0.0, RECORD_WINDOW)
        self._applying = False

    # --- Membership ------------------------------------------------------

    def register(self, view_box, axis: str = 'x'):
        """Join ``view_box`` to the group, syncing the named axis.

        A transposed plot has time running up its Y axis, so the group drives
        whichever axis actually carries time.
        """
        if self._members.get(view_box) == axis:
            return
        if view_box in self._members:
            self.unregister(view_box)

        self._members[view_box] = axis
        self._signal(view_box, axis).connect(self._on_member_changed)
        self._apply_to(view_box)

    def unregister(self, view_box):
        axis = self._members.pop(view_box, None)
        if axis is None:
            return
        try:
            self._signal(view_box, axis).disconnect(self._on_member_changed)
        except TypeError:
            logging.debug("View box was already disconnected from the time sync group")

    def clear(self):
        for view_box in list(self._members):
            self.unregister(view_box)

    def __len__(self):
        return len(self._members)

    @staticmethod
    def _signal(view_box, axis: str):
        return view_box.sigYRangeChanged if axis == 'y' else view_box.sigXRangeChanged

    # --- Range -----------------------------------------------------------

    @property
    def range(self):
        return self._range

    @property
    def width(self) -> float:
        return self._range[1] - self._range[0]

    def set_range(self, lo: float, hi: float):
        if hi <= lo:
            return
        if self._range == (lo, hi):
            return

        self._range = (lo, hi)
        self._applying = True
        try:
            for view_box in self._members:
                self._apply_to(view_box)
        finally:
            self._applying = False
        self.range_changed.emit(lo, hi)

    def reset(self, length_seconds: float = 0.0):
        """Show the whole recording, or a default window when there is none."""
        length = float(length_seconds or 0.0)
        self.set_range(0.0, length if length > 0 else RECORD_WINDOW)

    def _apply_to(self, view_box):
        low, high = self._range
        if self._members.get(view_box) == 'y':
            view_box.setYRange(low, high, padding=0)
        else:
            view_box.setXRange(low, high, padding=0)

    def _on_member_changed(self, view_box, new_range):
        """A user pan or zoom on one member becomes the group's range."""
        if self._applying:
            return
        lo, hi = float(new_range[0]), float(new_range[1])
        if hi > lo:
            self.set_range(lo, hi)

    # --- Following the playhead -----------------------------------------

    def follow(self, current_time: float, mode: str, length_seconds: float = 0.0):
        """Scroll the view so the playhead stays visible."""
        if mode == MODE_RECORDING:
            lo = max(0.0, current_time - RECORD_WINDOW + RECORD_LOOKAHEAD)
            self.set_range(lo, max(RECORD_WINDOW, current_time + RECORD_LOOKAHEAD))
            return

        if mode != MODE_PLAYING:
            return

        lo, hi = self._range
        width = hi - lo
        if width <= 0 or width >= (length_seconds - 0.01):
            # The whole recording already fits; nothing to scroll.
            return

        buffer_seconds = PAGE_TRIGGER * width
        if current_time > (hi - buffer_seconds):
            new_hi = current_time + buffer_seconds
            self.set_range(new_hi - width, new_hi)
        elif current_time < lo:
            new_lo = max(0.0, current_time - buffer_seconds)
            self.set_range(new_lo, new_lo + width)
