"""Many short line segments, each with its own colour and opacity, in one item.

A radar plot marks a value with a stroke across its spoke rather than with a
dot, and a trail's worth of those strokes fades out with age -- so every segment
needs a pen of its own. ``PlotCurveItem`` with ``connect='pairs'`` draws
disconnected segments but takes a single pen for the lot, and one item per
segment would mean hundreds of graphics items per plot, rebuilt every frame.

Painting them directly is the cheap way: one item, one array, one pass. It also
keeps this out of ``PlotItem.curves`` -- a bare ``GraphicsObject`` does not
implement ``plotData``, so the plot-wide ``setClipToView`` and
``setDownsampling`` calls that catch out ``ScatterPlotItem`` never reach it.

The pen is **cosmetic**: the segments are positioned and sized in data space,
because they have to line up with the target box drawn around them, but their
thickness is a property of the drawing rather than of the data.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui

#: Segments thinner than this are hard to see at all; the point-size slider
#: scales up from here.
MIN_WIDTH = 1.0


class SegmentItem(pg.GraphicsObject):
    """A bundle of line segments drawn with per-segment pens."""

    def __init__(self, colour="#ffffff", width: float = 2.0):
        super().__init__()
        self._segments = np.empty((0, 4), dtype=float)
        self._alpha = np.empty(0, dtype=int)
        self._colours = None            # (N, 3) uint8, or None for one colour
        self._colour = pg.mkColor(colour)
        self._width = max(MIN_WIDTH, float(width))
        self._bounds = QtCore.QRectF()

    # --- Data ------------------------------------------------------------

    def set_segments(self, x0, y0, x1, y1, alpha, colours=None):
        """Replace every segment. Arrays are (start, end) pairs per segment.

        ``colours`` is an optional (N, 3) or (N, 4) uint8 array -- the colour
        dimension -- whose alpha channel, if any, is ignored in favour of
        ``alpha``, which carries the trail's fade.
        """
        segments = np.column_stack([np.asarray(a, dtype=float).ravel()
                                    for a in (x0, y0, x1, y1)]) \
            if len(np.asarray(x0).ravel()) else np.empty((0, 4), dtype=float)

        self.prepareGeometryChange()
        self._segments = segments
        self._alpha = np.asarray(alpha, dtype=int).ravel()
        self._colours = (np.asarray(colours, dtype=np.uint8)[:, :3]
                         if colours is not None and len(colours) else None)
        self._bounds = _bounds_of(segments)
        self.informViewBoundsChanged()
        self.update()

    def clear(self):
        self.set_segments([], [], [], [], [])

    # --- Appearance ------------------------------------------------------

    def set_colour(self, colour):
        self._colour = pg.mkColor(colour)
        self.update()

    def set_width(self, width: float):
        self._width = max(MIN_WIDTH, float(width))
        self.update()

    # --- QGraphicsItem ---------------------------------------------------

    def boundingRect(self) -> QtCore.QRectF:
        return self._bounds

    def paint(self, painter, *_args):
        if not len(self._alpha):
            return

        pen = QtGui.QPen()
        pen.setCosmetic(True)
        pen.setWidthF(self._width)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)

        red, green, blue = self._colour.red(), self._colour.green(), self._colour.blue()
        colour = QtGui.QColor()

        for index, alpha in enumerate(self._alpha):
            if alpha <= 0:
                continue
            if self._colours is not None and index < len(self._colours):
                red, green, blue = (int(v) for v in self._colours[index])
            colour.setRgb(red, green, blue, int(alpha))
            pen.setColor(colour)
            painter.setPen(pen)
            x0, y0, x1, y1 = self._segments[index]
            painter.drawLine(QtCore.QLineF(x0, y0, x1, y1))


def _bounds_of(segments: np.ndarray) -> QtCore.QRectF:
    if not len(segments):
        return QtCore.QRectF()
    xs = segments[:, (0, 2)]
    ys = segments[:, (1, 3)]
    left, right = float(np.min(xs)), float(np.max(xs))
    top, bottom = float(np.min(ys)), float(np.max(ys))
    return QtCore.QRectF(left, top, right - left, bottom - top)
