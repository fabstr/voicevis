"""Value-against-time scatter -- the common case.

One item per Y series. ``PlotDataItem`` rather than ``ScatterPlotItem`` because
clipping and downsampling only apply to the former, and these plots routinely
hold tens of thousands of frames.
"""

import numpy as np
import pyqtgraph as pg

from ui.plot.DirectionalViewBox import time_measure_formatter
from ui.plot.PlotTheme import PlotTheme
from ui.plot.TimeAxisItem import TimeAxisItem
from ui.plot.renderers.PlotRenderer import PlotRenderer


class TimeScatterRenderer(PlotRenderer):

    follows_time_axis = True
    shows_playhead = True
    supports_seek = True
    supports_spectrogram = True

    measure_formatter = staticmethod(time_measure_formatter)

    def bottom_axis(self):
        return TimeAxisItem(orientation='bottom')

    def _build_items(self):
        edge_pen = PlotTheme.marker_edge_pen()
        size = self.config.point_size

        for spec in self.config.y_specs():
            self._add(pg.PlotDataItem(
                [], [],
                pen=None,
                symbol='o',
                symbolBrush=spec.colour,
                symbolPen=edge_pen,
                symbolSize=size,
                clipToView=True,
                autoDownsample=True,
                downsampleMethod='peak',
            ))

    def _refresh(self, current_time: float):
        edge_pen = PlotTheme.marker_edge_pen()
        colour_series = self.config.colour_spec() is not None

        for item, spec in zip(self.items, self.config.y_specs()):
            x, y = self.hub.get_xy(spec.key)

            if not colour_series:
                item.setData(x=x, y=y)
                continue

            colours = self._colour_values(x)
            if colours is None:
                # No colour data yet -- fall back to the series' own colour
                # rather than leaving the previous frame's points on screen.
                item.setData(x=x, y=y, symbolBrush=spec.colour, symbolPen=edge_pen)
            else:
                item.setData(x=x, y=y,
                             symbolBrush=[pg.mkBrush(*c) for c in colours],
                             symbolPen=edge_pen)

    def _apply_point_size(self, item, size: int):
        item.setSymbolSize(size)

    def y_range_of_data(self):
        """The span actually covered by the data, used to crop the spectrogram."""
        lows, highs = [], []
        for spec in self.config.y_specs():
            _, y = self.hub.get_xy(spec.key)
            if len(y):
                lows.append(float(np.min(y)))
                highs.append(float(np.max(y)))
        return (min(lows), max(highs)) if lows else None
