"""Draggable reference lines at marked frequencies.

Orientation follows the plot: on a spectrogram or formant plot frequency is the
vertical axis, so markers are horizontal lines; on a spectrum slice frequency is
the horizontal axis, so they are vertical.

The spectrum slice also holds *log10* of the frequency on its axis, so the layer
converts through the renderer's transform rather than assuming axis coordinates
are Hz.
"""

import pyqtgraph as pg

from ui.plot.FrequencyMarkers import MARKERS

#: In front of the curves, behind the playhead.
Z_VALUE = 5

LINE_WIDTH = 1
HOVER_WIDTH = 3
#: Marker colour: a warm tone that reads against viridis and against the
#: series palette without being mistaken for data.
LINE_COLOUR = (255, 170, 60)

LABEL_OPTS = {'position': 0.92, 'color': (255, 170, 60), 'movable': False,
              'fill': (0, 0, 0, 140)}


def _identity(value):
    return value


class FrequencyMarkerLayer:
    """The marker lines of one plot."""

    def __init__(self, plot_item):
        self.plot_item = plot_item
        self._lines = []
        self._axis = None
        self._to_axis = _identity
        self._from_axis = _identity
        self._applying = False

    # --- Configuration ---------------------------------------------------

    def set_axis(self, axis, to_axis=None, from_axis=None):
        """Say which axis carries frequency, and how Hz maps onto it.

        ``axis`` is 'x', 'y' or None. The transforms handle the spectrum
        slice, whose axis holds log10(Hz).
        """
        self._axis = axis
        self._to_axis = to_axis or _identity
        self._from_axis = from_axis or _identity
        self._rebuild()

    @property
    def enabled(self) -> bool:
        return self._axis is not None

    def refresh(self):
        self._rebuild()

    def clear(self):
        for line in self._lines:
            self.plot_item.removeItem(line)
        self._lines = []

    # --- Hit testing, for the context menu -------------------------------

    def frequency_at(self, point):
        """The frequency under a point in view coordinates, or None."""
        if point is None or not self.enabled:
            return None
        value = point.x() if self._axis == 'x' else point.y()
        try:
            return float(self._from_axis(value))
        except (TypeError, ValueError):
            return None

    def marker_near(self, point, pixel_tolerance=8):
        """The marker within ``pixel_tolerance`` of a point, or None."""
        target = self.frequency_at(point)
        if target is None:
            return None

        view_box = self.plot_item.getViewBox()
        pixel = view_box.viewPixelSize()
        span = (pixel[0] if self._axis == 'x' else pixel[1]) * pixel_tolerance

        axis_value = point.x() if self._axis == 'x' else point.y()
        for value in MARKERS.values():
            if abs(self._to_axis(value) - axis_value) <= span:
                return value
        return None

    # --- Drawing ---------------------------------------------------------

    def _rebuild(self):
        values = MARKERS.values() if self.enabled else []

        while len(self._lines) > len(values):
            self.plot_item.removeItem(self._lines.pop())
        while len(self._lines) < len(values):
            self._lines.append(self._make_line())

        self._applying = True
        try:
            for line, hz in zip(self._lines, values):
                line.setAngle(90 if self._axis == 'x' else 0)
                line.setValue(float(self._to_axis(hz)))
                line.label.setFormat(format_hz(hz))
                line.marker_hz = hz
        finally:
            self._applying = False

    def _make_line(self):
        line = pg.InfiniteLine(
            angle=90 if self._axis == 'x' else 0,
            movable=True,
            pen=pg.mkPen(LINE_COLOUR, width=LINE_WIDTH),
            hoverPen=pg.mkPen(LINE_COLOUR, width=HOVER_WIDTH),
            label="",
            labelOpts=dict(LABEL_OPTS),
        )
        line.setZValue(Z_VALUE)
        line.marker_hz = None
        line.sigPositionChanged.connect(lambda ln=line: self._on_dragging(ln))
        line.sigPositionChangeFinished.connect(lambda ln=line: self._on_dragged(ln))
        self.plot_item.addItem(line)
        return line

    def _on_dragging(self, line):
        """Keep the label truthful while the line is under the cursor."""
        if self._applying:
            return
        line.label.setFormat(format_hz(self._from_axis(line.value())))

    def _on_dragged(self, line):
        if self._applying or line.marker_hz is None:
            return
        # The store fans the change back out to every plot, this one included.
        MARKERS.move(line.marker_hz, self._from_axis(line.value()))


def format_hz(hz) -> str:
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return ""
    return f"{hz:.0f} Hz" if hz >= 100 else f"{hz:.1f} Hz"
