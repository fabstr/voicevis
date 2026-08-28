"""Scatter of one feature against another, with a fading trail.

Neither axis is time here, so the plot instead shows the last ``trail_time``
seconds of history, each point fading out with age. ``ScatterPlotItem`` is the
right choice: the point count is bounded by the trail window, and every point
needs its own brush.
"""

import numpy as np
import pyqtgraph as pg

import SeriesRegistry as Registry

from ui.plot.ColourMapping import brushes, solid_brushes
from ui.plot.PlotTheme import PlotTheme
from ui.plot.ScatterItem import ScatterItem
from ui.plot.renderers.PlotRenderer import PlotRenderer

#: Markers here are sparser than on a time plot, so they can afford to be bigger.
SIZE_MULTIPLIER = 1


class TrailRenderer(PlotRenderer):

    def _build_items(self):
        size = self.config.point_size * SIZE_MULTIPLIER
        for spec in self._pair_specs():
            item = ScatterItem(size=size,
                               pen=PlotTheme.marker_edge_pen(),
                               brush=pg.mkBrush(Registry.colour_of(spec)))
            item.opts['hoverSize'] = size * 1.5
            self._add(item)

    def _pair_specs(self):
        """The series whose colour identifies each drawn pair.

        Exactly one axis may hold several series, so the multi-valued axis is
        the one that names the pairs.
        """
        x_specs, y_specs = self.config.x_specs(), self.config.y_specs()
        return x_specs if len(x_specs) > len(y_specs) else y_specs

    def _pairs(self):
        """(x_key, y_key) for each item, in item order."""
        x_keys, y_keys = self.config.x, self.config.y
        if len(x_keys) > len(y_keys):
            return [(xk, y_keys[0]) for xk in x_keys]
        return [(x_keys[0], yk) for yk in y_keys]

    def _refresh(self, current_time: float):
        self._draw(current_time)

    def on_time_changed(self, current_time: float):
        self._draw(current_time)

    def _draw(self, current_time: float):
        trail_time = self.config.trail_time

        for item, (x_key, y_key), spec in zip(self.items, self._pairs(), self._pair_specs()):
            times, x_values, y_values = self._window(x_key, y_key, current_time, trail_time)

            if len(times) == 0:
                item.setData(x=[], y=[])
                continue

            alpha = self._alpha(times, current_time, trail_time)
            colours = self._colour_values(times)

            point_brushes = (brushes(colours, alpha) if colours is not None
                             else solid_brushes(Registry.colour_of(spec), alpha))
            pens = [pg.mkPen(color=(128, 128, 128, int(a * 0.5)), width=0.5) for a in alpha]

            item.setData(x=x_values, y=y_values, brush=point_brushes, pen=pens)

    def _window(self, x_key: str, y_key: str, current_time: float, trail_time: float):
        """The points of one pair falling inside the trail window."""
        base_x, base_y = self.hub.get_raw(x_key)
        if len(base_x) == 0:
            return np.empty(0), np.empty(0), np.empty(0)

        low = max(0.0, current_time - trail_time)
        inside = (base_x >= low) & (base_x <= current_time)
        times = base_x[inside]
        if len(times) == 0:
            return np.empty(0), np.empty(0), np.empty(0)

        x_values = base_y[inside]

        # All features share one frame timebase, but interpolate anyway so a
        # mismatched length can never misalign the two axes.
        other_x, other_y = self.hub.get_raw(y_key)
        if len(other_x) == 0:
            return np.empty(0), np.empty(0), np.empty(0)
        y_values = (other_y[inside] if np.array_equal(other_x, base_x)
                    else np.interp(times, other_x, other_y))

        valid = np.isfinite(x_values) & np.isfinite(y_values)
        return times[valid], x_values[valid], y_values[valid]

    @staticmethod
    def _alpha(times: np.ndarray, current_time: float, trail_time: float):
        if trail_time <= 0:
            return np.full(len(times), 255, dtype=int)
        age = np.clip((current_time - times) / trail_time, 0.0, 1.0)
        return (255 * (1.0 - age)).astype(int)

    def _apply_point_size(self, item, size: int):
        scaled = size * SIZE_MULTIPLIER
        item.setSize(scaled)
        item.opts['hoverSize'] = scaled * 1.5
