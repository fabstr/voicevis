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

import SeriesRegistry as Registry
from ui.plot.DirectionalViewBox import log_x_measure_formatter
from ui.plot.FrequencyAxisItem import FrequencyAxisItem
from ui.plot.renderers.PlotRenderer import PlotRenderer

FREQUENCY_TICKS = [10, 110, 220, 1000, 5000, 10000]
FILL_COLOUR = (147, 112, 219, 150)
LINE_WIDTH = 1.5


class SpectrumSliceRenderer(PlotRenderer):

    measure_formatter = staticmethod(log_x_measure_formatter)

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

        self._add(pg.PlotDataItem(
            [], [],
            pen=pg.mkPen(color=spec.colour, width=LINE_WIDTH),
            fillLevel=y_range[0],
            fillBrush=pg.mkBrush(FILL_COLOUR),
        ))

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
            return

        times = np.asarray(spectrogram.x, dtype=float)
        index = int(np.abs(times - current_time).argmin()) if len(times) else -1
        magnitudes = spectrogram.magnitude_db[:, index]

        frequencies = np.asarray(spectrogram.y, dtype=float)
        audible = frequencies > 0
        item.setData(x=self.x_transform(frequencies[audible]), y=magnitudes[audible])
