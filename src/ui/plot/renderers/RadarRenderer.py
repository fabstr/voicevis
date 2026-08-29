"""Several series at once, each on its own spoke around a common centre.

A trail plot compares two quantities against each other; a radar compares any
number of them against their *targets*. Every series on Y gets a spoke, evenly
spaced around the circle, and its value is drawn as a stroke across that spoke
at the right distance out. The frame -- the ring, the spokes, their scales and
the target boxes -- belongs to
:class:`~ui.plot.layers.RadarLayer.RadarLayer`; this renderer draws only the
values.

Like a trail plot it shows the last ``trail_time`` seconds fading out with age,
so the recent history of each quantity reads as a ladder running along its
spoke.
"""

import numpy as np

import SeriesRegistry as Registry

from ui.plot import RadarGeometry
from ui.plot.SegmentItem import SegmentItem
from ui.plot.renderers.PlotRenderer import PlotRenderer

#: Point size 1..5 is a marker diameter elsewhere; here it is a line thickness.
#: A stroke reads at half the weight a dot needs -- it is already as long as the
#: target box is wide -- and a thin one keeps a dense trail legible as separate
#: values rather than filling in as a block.
WIDTH_SCALE = 0.5
WIDTH_OFFSET = 0.5


class RadarRenderer(PlotRenderer):
    """One :class:`~ui.plot.SegmentItem.SegmentItem` per spoke."""

    #: Neither axis is a quantity, so their ticks would read as the polar
    #: coordinates of the drawing rather than as anything measured. Each spoke
    #: carries a scale of its own instead.
    shows_axes = False
    #: The ring has to stay circular whatever shape the cell is.
    locks_aspect = True
    #: Targets are drawn along their own spoke, not as bands across the plot.
    supports_target_bands = False

    def _build_items(self):
        for spec in self.config.radar_specs():
            self._add(SegmentItem(colour=Registry.colour_of(spec),
                                  width=self._width()))

    def _width(self) -> float:
        return _width_for(self.config.point_size)

    def _refresh(self, current_time: float):
        self._draw(current_time)

    def on_time_changed(self, current_time: float):
        self._draw(current_time)

    def _draw(self, current_time: float):
        specs = self.config.radar_specs()
        trail_time = self.config.trail_time
        angles = RadarGeometry.angles(len(specs))

        for item, spec, angle in zip(self.items, specs, angles):
            times, values = self._window(spec.key, current_time, trail_time)

            if len(times) == 0:
                item.clear()
                continue

            radii = RadarGeometry.radius(values, spec)
            x0, y0, x1, y1 = RadarGeometry.value_ticks(radii, angle)
            item.set_segments(x0, y0, x1, y1,
                              self.trail_alpha(times, current_time, trail_time),
                              self._colour_values(times))

    def _window(self, key: str, current_time: float, trail_time: float):
        """One series' samples inside the trail window, NaNs dropped.

        Read raw rather than through ``get_xy`` so that the timestamps kept
        here are the ones the fade is computed from, without a second mask
        having already been applied to them.
        """
        times, values = self.hub.get_raw(key)
        if len(times) == 0:
            return np.empty(0), np.empty(0)

        low = max(0.0, current_time - trail_time)
        inside = (times >= low) & (times <= current_time)
        times, values = times[inside], values[inside]

        valid = np.isfinite(times) & np.isfinite(values)
        return times[valid], values[valid]

    def _apply_point_size(self, item, size: int):
        item.set_width(_width_for(size))


def _width_for(point_size: int) -> float:
    return point_size * WIDTH_SCALE + WIDTH_OFFSET
