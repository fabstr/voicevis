"""The frame a radar plot's values are read against.

A radar plot has no axes in the ordinary sense, so everything that would
normally be an axis is drawn here: the ring a series reaches at the top of its
range, the spoke it runs along, the scale marked up that spoke, its name, and
the box marking its target range. The values themselves come from
:class:`~ui.plot.renderers.RadarRenderer.RadarRenderer`, and the two agree on
where things go by way of :mod:`ui.plot.RadarGeometry`.

The target box replaces the shaded band a Cartesian plot gets from
:class:`~ui.plot.layers.TargetBandLayer.TargetBandLayer`: a band across the
whole plot would mark nothing here, because the axes are not the quantities.

The frame is drawn with plain ``QGraphicsItem``s and cosmetic pens rather than
with ``PlotCurveItem``. ``PlotItem`` files anything implementing ``plotData``
under ``self.curves`` and then calls ``setClipToView`` on the lot -- which a
curve item does not have -- and a cosmetic pen keeps the ring one pixel wide
however far the plot is zoomed. It is the same trap ``ScatterItem`` documents,
avoided by not joining that list at all.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

import SeriesRegistry as Registry
from ui.plot import RadarGeometry
from ui.plot.SegmentItem import SegmentItem

#: Behind the target boxes, so the ring and the scales do not draw over them.
FRAME_Z = -25

#: The same depth the shaded bands use on a Cartesian plot.
TARGET_Z = -20

#: How visible a spoke, and its scale, are next to the values drawn on them.
SPOKE_ALPHA = 90
SCALE_ALPHA = 170

#: How visible the ring and the target outlines are.
FRAME_ALPHA = 160

RING_WIDTH = 1.5
SPOKE_WIDTH = 1.0
SCALE_WIDTH = 1.0

#: Big enough to read at a glance while practising, which is the whole point of
#: the plot -- the room for them comes from the narrow axes, not from small type.
SERIES_FONT_POINTS = 11
SCALE_FONT_POINTS = 9


class RadarLayer:
    """Owns the ring, spokes, scales, labels and target boxes of one plot."""

    def __init__(self, plot_item):
        self.plot_item = plot_item
        self._items = []
        self._boxes = []          # (series spec, polygon item, angle)
        self._specs = []
        self._target_config = None
        self._theme = None

    # --- Configuration ---------------------------------------------------

    def set_series(self, specs):
        """Draw a frame for ``specs``, or nothing at all when it is empty."""
        self._specs = list(specs)
        self.refresh()

    def refresh(self):
        """Rebuild the frame, e.g. after the series palette or theme changed."""
        self.clear()
        if not self._specs:
            return

        self._build_ring()
        for spec, angle in zip(self._specs, RadarGeometry.angles(len(self._specs))):
            self._build_spoke(spec, angle)
        self.update(self._target_config)

    def update(self, target_config):
        """Move each target box to the bounds in ``target_config``."""
        self._target_config = target_config

        for spec, box, angle in self._boxes:
            bounds = (target_config.get_bounds(spec.target_key)
                      if target_config is not None else None)
            if bounds is None:
                box.setVisible(False)
                continue

            low, high, enabled = bounds
            radii = RadarGeometry.radius([low, high], spec)
            box.setPolygon(_polygon(
                *RadarGeometry.target_box(radii[0], radii[1], angle)))
            box.setVisible(bool(enabled))

    def clear(self):
        for item in self._items:
            self.plot_item.removeItem(item)
        self._items = []
        self._boxes = []

    # --- Appearance ------------------------------------------------------

    def apply_theme(self, theme):
        self._theme = theme
        self.refresh()

    def _frame_colour(self) -> QtGui.QColor:
        colour = (QtGui.QColor(self._theme.text) if self._theme is not None
                  else QtGui.QColor(128, 128, 128))
        colour.setAlpha(FRAME_ALPHA)
        return colour

    # --- Building --------------------------------------------------------

    def _build_ring(self):
        """The circle every spoke reaches at the top of its series' range."""
        radius = RadarGeometry.OUTER_RADIUS
        path = QtGui.QPainterPath()
        path.addEllipse(QtCore.QRectF(-radius, -radius, 2 * radius, 2 * radius))

        ring = QtWidgets.QGraphicsPathItem(path)
        ring.setPen(_pen(self._frame_colour(), RING_WIDTH))
        ring.setBrush(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush))
        self._add(ring, FRAME_Z)

    def _build_spoke(self, spec, angle: float):
        """One series' axis line, its scale, its name, and its target box."""
        colour = QtGui.QColor(pg.mkColor(Registry.colour_of(spec)))

        line_colour = QtGui.QColor(colour)
        line_colour.setAlpha(SPOKE_ALPHA)
        x_values, y_values = RadarGeometry.spoke(angle)
        path = QtGui.QPainterPath(QtCore.QPointF(x_values[0], y_values[0]))
        path.lineTo(QtCore.QPointF(x_values[1], y_values[1]))
        line = QtWidgets.QGraphicsPathItem(path)
        line.setPen(_pen(line_colour, SPOKE_WIDTH))
        self._add(line, FRAME_Z)

        self._build_scale(spec, angle, colour)

        label = pg.TextItem(spec.label, color=colour, anchor=_anchor(angle))
        label.setFont(_font(SERIES_FONT_POINTS))
        label.setPos(*RadarGeometry.label_point(angle))
        self._add(label, TARGET_Z)

        if spec.target_key:
            box = QtWidgets.QGraphicsPolygonItem()
            box.setBrush(pg.mkBrush(Registry.target_band))
            box.setPen(_pen(self._frame_colour(), SPOKE_WIDTH))
            box.setVisible(False)
            self._add(box, TARGET_Z)
            self._boxes.append((spec, box, angle))

    def _build_scale(self, spec, angle: float, colour: QtGui.QColor):
        """The numbered divisions up one spoke, marked on both sides of it.

        Both sides, because a spoke is read from either -- the values sit
        between them, so a scale on one side only would be the far one for half
        the plot. The strokes start where the target box ends, so the scale
        frames the box instead of running through the values inside it.
        """
        values, step = RadarGeometry.scale_ticks(spec)
        if not values:
            return

        scale_colour = QtGui.QColor(colour)
        scale_colour.setAlpha(SCALE_ALPHA)

        marks = SegmentItem(colour=scale_colour, width=SCALE_WIDTH)
        starts_x, starts_y, ends_x, ends_y = [], [], [], []
        font = _font(SCALE_FONT_POINTS)

        for value in values:
            radius = float(RadarGeometry.radius([value], spec)[0])
            x0, y0, x1, y1 = RadarGeometry.scale_tick_marks(radius, angle)
            starts_x.extend(x0), starts_y.extend(y0)
            ends_x.extend(x1), ends_y.extend(y1)

            text = RadarGeometry.format_tick(value, step)
            for point, side in zip(RadarGeometry.scale_label_points(radius, angle),
                                   (angle + np.pi / 2, angle - np.pi / 2)):
                label = pg.TextItem(text, color=scale_colour, anchor=_anchor(side))
                label.setFont(font)
                label.setPos(float(point[0]), float(point[1]))
                self._add(label, FRAME_Z)

        marks.set_segments(starts_x, starts_y, ends_x, ends_y,
                           np.full(len(starts_x), scale_colour.alpha()))
        self._add(marks, FRAME_Z)

    def _add(self, item, z_value):
        item.setZValue(z_value)
        self.plot_item.addItem(item)
        self._items.append(item)
        return item


def _font(points: int) -> QtGui.QFont:
    font = QtGui.QFont()
    font.setPointSize(points)
    return font


def _pen(colour: QtGui.QColor, width: float,
         style=QtCore.Qt.PenStyle.SolidLine) -> QtGui.QPen:
    """A pen that keeps its width in pixels however the plot is zoomed."""
    pen = QtGui.QPen(colour)
    pen.setWidthF(width)
    pen.setStyle(style)
    pen.setCosmetic(True)
    return pen


def _polygon(x_values, y_values) -> QtGui.QPolygonF:
    return QtGui.QPolygonF([QtCore.QPointF(float(x), float(y))
                            for x, y in zip(x_values, y_values)])


def _anchor(angle: float):
    """Place text clear of the point it marks: away from the centre it points from."""
    return (0.5 - 0.5 * float(np.cos(angle)), 0.5 + 0.5 * float(np.sin(angle)))
