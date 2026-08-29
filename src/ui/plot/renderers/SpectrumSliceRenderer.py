"""Magnitude against frequency: one column of the spectrogram at the playhead.

X holds log10 of the frequency rather than using ``PlotItem.setLogMode``.
``FrequencyAxisItem`` overrides ``tickValues``/``tickStrings`` to force a curated
tick list; log mode routes through ``logTickValues``/``logTickStrings`` instead
and calls back into ``tickValues`` with already-log-scaled bounds, so the two
mechanisms fight. Keeping the transform explicit confines log-awareness to
``x_transform`` and its inverse.
"""

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtGui

import SeriesRegistry as Registry
from ui.plot.ColourMapping import colour_map
from ui.plot.DirectionalViewBox import log_x_measure_formatter
from ui.plot.FrequencyAxisItem import FrequencyAxisItem
from ui.plot.renderers.PlotRenderer import PlotRenderer

FREQUENCY_TICKS = [10, 110, 220, 1000, 5000, 10000]
LINE_WIDTH = 1.5
#: How translucent the area under the curve is, relative to its outline.
FILL_ALPHA = 150
#: Colour stops used to approximate the colour map along the frequency axis.
GRADIENT_STOPS = 32


class SpectrumSliceRenderer(PlotRenderer):

    measure_formatter = staticmethod(log_x_measure_formatter)

    #: The one thing this plot draws, and so the key its colouring is filed
    #: under -- the same key ``PlotConfig.drawn_keys`` reports for this kind.
    KEY = Registry.MAGNITUDE_KEY

    def axis_items(self):
        return {'bottom': FrequencyAxisItem(x_ticks=FREQUENCY_TICKS, is_log_x=True,
                                            orientation='bottom'),
                'left': pg.AxisItem(orientation='left')}

    @staticmethod
    def x_transform(values):
        return np.log10(np.clip(np.asarray(values, dtype=float), 1e-5, None))

    @staticmethod
    def x_inverse(values):
        return np.power(10.0, np.asarray(values, dtype=float))

    def _build_items(self):
        spec = Registry.SERIES[Registry.MAGNITUDE_KEY]
        y_range = self.config.effective_y_range() or (spec.default_min, spec.default_max)

        self._add(pg.PlotDataItem([], [], fillLevel=y_range[0]))
        self._apply_colour(Registry.colour_of(spec))

    def _apply_colour(self, colour):
        """Colour the outline and the area under it together."""
        if not self.items:
            return
        line = pg.mkColor(colour)
        fill = pg.mkColor(line)
        fill.setAlpha(FILL_ALPHA)

        self.items[0].setPen(pg.mkPen(color=line, width=LINE_WIDTH))
        self.items[0].setFillBrush(pg.mkBrush(fill))

    def _refresh(self, current_time: float):
        self._draw(current_time)

    def on_time_changed(self, current_time: float):
        self._draw(current_time)

    def _draw(self, current_time: float):
        item = self.items[0] if self.items else None
        if item is None:
            return

        spectrogram = self.hub.spectrogram()
        if spectrogram is None:
            item.setData(x=[], y=[])
            self._recolour(current_time)
            return

        times = np.asarray(spectrogram.x, dtype=float)
        index = int(np.abs(times - current_time).argmin()) if len(times) else -1
        magnitudes = spectrogram.magnitude_db[:, index]

        frequencies = np.asarray(spectrogram.y, dtype=float)
        audible = frequencies > 0
        x_values = self.x_transform(frequencies[audible])

        item.setData(x=x_values, y=magnitudes[audible])
        self._recolour(current_time, x_values)

    def _recolour(self, current_time: float, x_values=None):
        """Apply the colour dimension, if this plot has one.

        Colouring by ``frequency`` -- the X axis -- runs the colour map along
        the curve, so the shape is read against the spectrum it sits on. Colouring
        by an ordinary series instead tints the whole curve, because a slice is
        a single instant and a time series has just one value there; that tint
        then changes as playback moves.
        """
        colour_bar = self.colour_bars.get(self.KEY)
        by_frequency = self.config.colour_source(self.KEY) == Registry.FREQUENCY_KEY
        if colour_bar is not None and not by_frequency:
            colour_bar.getAxis('right').setTicks(None)

        if by_frequency:
            self._apply_frequency_gradient(x_values)
            return

        colours = self._colour_values(np.array([current_time], dtype=float), self.KEY)
        if colours is None or len(colours) == 0:
            self._apply_colour(Registry.colour_of(Registry.SERIES[Registry.MAGNITUDE_KEY]))
            return

        red, green, blue = (int(v) for v in colours[0][:3])
        self._apply_colour(pg.mkColor(red, green, blue))

    def _apply_frequency_gradient(self, x_values):
        """The colour map across the frequency axis, painted into the fill.

        The outline is dropped rather than given the same gradient: a pen whose
        brush is a gradient corrupts the curve's bounding rect, which rescales
        the axes and mangles the shape. The filled area defines the curve
        perfectly well on its own.
        """
        if x_values is None or len(x_values) < 2 or not self.items:
            return

        low, high = float(x_values[0]), float(x_values[-1])
        # Logical mode puts the gradient in the item's own coordinates, which
        # for a curve are the data coordinates -- here log10(Hz).
        fill = QtGui.QLinearGradient(low, 0.0, high, 0.0)
        fill.setCoordinateMode(QtGui.QGradient.CoordinateMode.LogicalMode)

        gradient_map = colour_map(self.config.colour_map_of(self.KEY))
        for stop in np.linspace(0.0, 1.0, GRADIENT_STOPS):
            red, green, blue = (int(v) for v in gradient_map.map(float(stop), mode='byte')[:3])
            fill.setColorAt(float(stop), QtGui.QColor(red, green, blue, FILL_ALPHA))

        self.items[0].setPen(None)
        self.items[0].setFillBrush(QtGui.QBrush(fill))

        colour_bar = self.colour_bars.get(self.KEY)
        if colour_bar is not None:
            # Levels are in the same log space as the gradient, so the legend
            # gets explicit Hz labels at the axis's own tick frequencies rather
            # than a linear scale that would disagree with what is drawn.
            colour_bar.setLevels((low, high))
            colour_bar.getAxis('right').setTicks([self._frequency_ticks(low, high), []])

    @staticmethod
    def _frequency_ticks(low: float, high: float):
        """(log-position, label) for each standard tick inside the range."""
        return [(np.log10(hz), f"{hz // 1000}k" if hz >= 1000 else str(hz))
                for hz in FREQUENCY_TICKS if low <= np.log10(hz) <= high]
