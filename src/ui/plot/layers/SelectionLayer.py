"""The highlighted stretch of audio the user has selected.

Shown on every plot with a time axis, running across whichever axis that is. The
band itself is draggable: letting go of it asks for the audio to be *moved* by
however far it travelled, which is the gesture the editing feature is built on.
Dragging its edges only adjusts the selection.
"""

import pyqtgraph as pg
from PyQt6 import QtCore

#: Above the curves so the tint reads, below the playhead and the markers.
Z_VALUE = 3

FILL = (90, 160, 255, 60)
EDGE = (120, 180, 255, 200)
HOVER_EDGE = (170, 210, 255, 255)

#: Spans within this fraction of each other count as unchanged, so a drag that
#: only moved the band is told apart from one that resized it.
SPAN_EPSILON = 1e-6


class SelectionLayer(QtCore.QObject):
    """Draws one plot's selection band and reports what the user does to it."""

    #: The band was dragged bodily; the audio should move by this many seconds.
    move_requested = QtCore.pyqtSignal(float)
    #: An edge was dragged; the selection is now this range.
    range_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, plot_item, selection, parent=None):
        super().__init__(parent)
        self.plot_item = plot_item
        self.selection = selection
        self._axis = None
        self._applying = False
        self.region = None

        self._build_region('vertical')
        selection.changed.connect(self.refresh)

    def _build_region(self, orientation):
        """(Re)create the band. Orientation is fixed at construction in pyqtgraph."""
        if self.region is not None:
            self.plot_item.removeItem(self.region)

        self.region = pg.LinearRegionItem(
            values=(0, 0), movable=True, orientation=orientation,
            brush=pg.mkBrush(FILL),
            pen=pg.mkPen(EDGE, width=1),
            hoverPen=pg.mkPen(HOVER_EDGE, width=2),
        )
        self.region.setZValue(Z_VALUE)
        self.region.setVisible(False)
        self.plot_item.addItem(self.region)
        self.region.sigRegionChangeFinished.connect(self._on_dragged)

    # --- Configuration ---------------------------------------------------

    def set_axis(self, axis):
        """'x', 'y' or None -- which axis carries time on this plot."""
        self._axis = axis
        # A LinearRegionItem spans the axis it is *not* oriented along, so a
        # time range on X needs the vertical orientation.
        wanted = 'vertical' if axis == 'x' else 'horizontal'
        if self.region.orientation != wanted:
            self._build_region(wanted)
        self.refresh()

    @property
    def enabled(self) -> bool:
        return self._axis is not None

    def refresh(self):
        visible = self.enabled and self.selection.active
        self.region.setVisible(visible)
        if not visible:
            return

        self._applying = True
        try:
            self.region.setRegion((self.selection.start, self.selection.end))
        finally:
            self._applying = False

    def clear(self):
        self.plot_item.removeItem(self.region)

    # --- Interaction -----------------------------------------------------

    def _on_dragged(self):
        if self._applying or not self.selection.active:
            return

        low, high = sorted(self.region.getRegion())
        was_low, was_high = self.selection.start, self.selection.end
        moved_by = low - was_low

        if abs((high - low) - (was_high - was_low)) <= SPAN_EPSILON * max(1.0, was_high):
            # Same length, different place: the band was dragged bodily.
            if moved_by:
                self.move_requested.emit(moved_by)
        else:
            self.range_changed.emit(low, high)
