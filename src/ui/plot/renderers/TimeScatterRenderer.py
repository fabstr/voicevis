"""Value-against-time scatter -- the common case.

One item per plotted series. ``PlotDataItem`` rather than ``ScatterPlotItem``
because clipping and downsampling only apply to the former, and these plots
routinely hold tens of thousands of frames.

Time may sit on either axis. When it is on Y the plot is transposed: the value
series run horizontally and time runs up the vertical axis.

While recording, only the stretch of time on screen is pushed into the items.
Clipping and downsampling would otherwise be the only thing keeping a redraw
affordable, and a series with a colour dimension has neither -- it is drawn
point by point, with a brush each.
"""

import numpy as np
import pyqtgraph as pg

import SeriesRegistry as Registry

from ui.plot.ColourMapping import brushes
from ui.plot.DirectionalViewBox import time_measure_formatter, transposed_time_measure_formatter
from ui.plot.PlotTheme import PlotTheme
from ui.plot.ScatterItem import ScatterItem
from ui.plot.TimeAxisItem import TimeAxisItem
from ui.plot.TimeAxisSyncGroup import RECORD_LOOKAHEAD, RECORD_WINDOW
from ui.plot.renderers.PlotRenderer import PlotRenderer

#: Kept either side of the window shown while recording, so that a point never
#: goes missing from the edge of the view between one redraw and the next.
WINDOW_MARGIN = 1.0


class TimeScatterRenderer(PlotRenderer):

    follows_time_axis = True
    shows_playhead = True
    supports_seek = True
    supports_spectrogram = True

    @property
    def time_on_y(self) -> bool:
        return self.config.time_on_y

    @property
    def measure_formatter(self):
        return transposed_time_measure_formatter if self.time_on_y else time_measure_formatter

    def axis_items(self):
        time_side = 'left' if self.time_on_y else 'bottom'
        value_side = 'bottom' if self.time_on_y else 'left'
        return {time_side: TimeAxisItem(orientation=time_side),
                value_side: pg.AxisItem(orientation=value_side)}

    def _build_items(self):
        edge_pen = PlotTheme.marker_edge_pen()
        size = self.config.point_size

        for spec in self.config.value_specs():
            if self.config.is_coloured(spec.key):
                # A colour dimension needs one brush per point. PlotDataItem
                # subsets x/y for clipping and downsampling but passes the brush
                # list through whole, so the scatter underneath then rejects the
                # mismatched lengths. ScatterPlotItem is never subsetted, so per
                # point brushes belong on one.
                item = ScatterItem(size=size, pen=edge_pen,
                                   brush=pg.mkBrush(Registry.colour_of(spec)))
                item.opts['hoverSize'] = size * 1.5
                self._add(item)
                continue

            item = self._add(pg.PlotDataItem(
                [], [],
                pen=None,
                symbol='o',
                symbolBrush=Registry.colour_of(spec),
                symbolPen=edge_pen,
                symbolSize=size,
            ))
            # PlotItem.addItem overwrites both of these from the plot-wide
            # settings, so they only stick if applied after the item is added.
            item.setClipToView(True)
            item.setDownsampling(ds=1, auto=True, method='peak')

    def _refresh(self, current_time: float):
        edge_pen = PlotTheme.marker_edge_pen()
        transposed = self.time_on_y
        window = self._live_window(current_time)

        for item, spec in zip(self.items, self.config.value_specs()):
            times, values = _inside(window, *self.hub.get_xy(spec.key))
            x, y = (values, times) if transposed else (times, values)

            # Which item was built for this series follows the same test, so a
            # plain PlotDataItem is never handed a brush list it cannot take.
            if not self.config.is_coloured(spec.key):
                item.setData(x=x, y=y)
                continue

            colours = self._colour_values(times, spec.key)
            if colours is None:
                # No colour data yet -- fall back to the series' own colour
                # rather than leaving the previous frame's points on screen.
                item.setData(x=x, y=y, brush=pg.mkBrush(Registry.colour_of(spec)), pen=edge_pen)
            else:
                item.setData(x=x, y=y, brush=brushes(colours), pen=edge_pen)

    def _live_window(self, current_time: float):
        """The stretch of time worth drawing, or None for all of it.

        While recording the sync group scrolls a fixed window along with the
        playhead and puts it back every frame, so nothing outside it can be
        looked at. Drawing it anyway costs the whole recording on every redraw
        -- and a coloured series is drawn point by point, with no clipping or
        downsampling to fall back on -- so a long take spent the frame it had
        on data nobody could see.
        """
        if not self.hub.is_recording:
            return None
        return (current_time - RECORD_WINDOW - WINDOW_MARGIN,
                current_time + RECORD_LOOKAHEAD + WINDOW_MARGIN)

    def _apply_point_size(self, item, size: int):
        if isinstance(item, pg.ScatterPlotItem):
            item.setSize(size)
            item.opts['hoverSize'] = size * 1.5
        else:
            item.setSymbolSize(size)

    def value_range_of_data(self):
        """The span the data actually covers, used to crop the spectrogram."""
        lows, highs = [], []
        for spec in self.config.value_specs():
            _, values = self.hub.get_xy(spec.key)
            if len(values):
                lows.append(float(np.min(values)))
                highs.append(float(np.max(values)))
        return (min(lows), max(highs)) if lows else None


def _inside(window, times, values):
    """``times`` and ``values`` cropped to ``window``, or whole when it is None.

    Frame times run in order, so the ends of the window are found by search
    rather than by testing every point.
    """
    if window is None or len(times) == 0:
        return times, values
    low, high = np.searchsorted(times, window)
    return times[low:high], values[low:high]
