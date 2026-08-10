"""Shaded bands marking the target range of each plotted series.

One band per series that has a target, all filled with the same neutral grey so
they stay in the background. Bands are keyed by series rather than by the plot,
so a plot showing F1, F2 and F3 gets three separate bands instead of three
identical ones stacked on top of each other.
"""

import pyqtgraph as pg

import SeriesRegistry as Registry

#: Behind the curves, but in front of the spectrogram image.
Z_VALUE = -20


class TargetBandLayer:
    """Owns the target regions of one plot."""

    def __init__(self, plot_item):
        self.plot_item = plot_item
        self._bands = {}   # (orientation, series key) -> LinearRegionItem
        self._config = None

    def set_series(self, y_specs, x_specs=None):
        """Rebuild the bands for a new axis selection.

        Horizontal bands come from the Y series. A vertical band is added for
        the X series too when both axes hold a single feature, which turns an
        XY trail plot's targets into a box.
        """
        wanted = {('horizontal', spec.key): spec for spec in y_specs if spec.target_key}

        x_specs = list(x_specs or [])
        if len(x_specs) == 1 and len(list(y_specs)) == 1 and x_specs[0].target_key:
            wanted[('vertical', x_specs[0].key)] = x_specs[0]

        for key in list(self._bands):
            if key not in wanted:
                self.plot_item.removeItem(self._bands.pop(key))

        for key in wanted:
            if key not in self._bands:
                self._bands[key] = self._make_band(key[0])

        if self._config is not None:
            self.update(self._config)

    def update(self, target_config):
        """Move the bands to the bounds in ``target_config``."""
        self._config = target_config
        if target_config is None:
            return

        for (_, series_key), band in self._bands.items():
            spec = Registry.get(series_key)
            bounds = target_config.get_bounds(spec.target_key) if spec else None
            if bounds is None:
                band.setVisible(False)
                continue
            low, high, enabled = bounds
            band.setRegion([low, high])
            band.setVisible(bool(enabled))

    def clear(self):
        for band in self._bands.values():
            self.plot_item.removeItem(band)
        self._bands.clear()

    def _make_band(self, orientation):
        band = pg.LinearRegionItem(
            orientation=orientation,
            movable=False,
            brush=pg.mkBrush(Registry.target_band),
        )
        for line in band.lines:
            line.setPen(pg.mkPen(None))
            line.setHoverPen(pg.mkPen(None))
        band.setZValue(Z_VALUE)
        band.setVisible(False)
        self.plot_item.addItem(band)
        return band
