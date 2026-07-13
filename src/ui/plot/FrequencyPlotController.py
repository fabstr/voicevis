import numpy as np
import pyqtgraph as pg

from plot.FrequencyAxisItem import FrequencyAxisItem
from plot.PlotController import PlotController
from signal_processing.AudioFeatures import FeatureSnapshot


class FrequencyPlotController(PlotController):
    """
    Subclass controller dedicated to Frequency-Magnitude plots.
    Manages custom logarithmic X-axes, playhead visibility, and slicing
    2D spectrogram data to show a 1D frequency curve at a specific point in time.
    """

    def _create_bottom_axis(self):
        return FrequencyAxisItem(
            x_ticks=self.spec.get('x_ticks'),
            is_log_x=self.spec.get('log_x', False),
            orientation='bottom'
        )

    def _init_playhead(self):
        super()._init_playhead()
        # Hide the playhead because the X-axis is Frequency, not Time
        self.playhead.setVisible(False)

    def _build_curves(self):
        for name, curve_spec in self.spec['curves'].items():
            self.curves[name] = {}
            if 'analysisResult' in curve_spec:
                self.curves[name]['analysisResult'] = curve_spec['analysisResult']

            pen = pg.mkPen(color=curve_spec.get('colour', '#9370DB'), width=1.5)
            brush = pg.mkBrush(curve_spec.get('fill_colour', (147, 112, 219, 150)))
            self.curves[name]['curve'] = self.widget.plot(
                [], pen=pen, fillLevel=self.spec.get('y_min', -100), fillBrush=brush
            )

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        curve['data_container'] = data_container
        self._update_frequency_plot(curve, data_container, self.current_time)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        result_key = curve.get('analysisResult')
        if not result_key or not hasattr(audio_features_ctx, result_key) or not hasattr(snapshot, result_key):
            return

        data_container = getattr(audio_features_ctx, result_key)
        new_data = getattr(snapshot, result_key)

        if snapshot.time is None or new_data is None:
            return

        curve['data_container'] = data_container

        if not hasattr(new_data, 'magnitude_db') or new_data.magnitude_db.size == 0:
            return

        if len(data_container.x) == 0:
            data_container.x = np.array([snapshot.time])
            data_container.y = new_data.y
            data_container.magnitude_db = new_data.magnitude_db.reshape(-1, 1)
        else:
            data_container.x = np.append(data_container.x, snapshot.time)
            new_col = new_data.magnitude_db.reshape(-1, 1)
            if new_col.shape[0] == data_container.magnitude_db.shape[0]:
                data_container.magnitude_db = np.hstack((data_container.magnitude_db, new_col))

        # Update the plot instantly to the appended time
        self._update_frequency_plot(curve, data_container, snapshot.time)

    def set_playhead_value(self, value: float):
        self.current_time = value
        self.playhead.setVisible(False)

        # When time scrubs, update the 1D frequency slice
        for curve in self.curves.values():
            self._update_frequency_plot(curve, curve.get('data_container'), value)

    def _update_frequency_plot(self, curve: dict, data_container, target_time: float):
        if data_container is None or not hasattr(data_container,
                                                 'magnitude_db') or data_container.magnitude_db.size == 0:
            return

        freqs = data_container.y
        if len(data_container.x) > 0:
            # Find the time index closest to the target_time
            idx = (np.abs(data_container.x - target_time)).argmin()
            mags = data_container.magnitude_db[:, idx]
        else:
            mags = data_container.magnitude_db[:, -1]

        valid_idx = freqs > 0
        x_data = freqs[valid_idx]
        y_data = mags[valid_idx]

        # Manually convert X to log10 if configured
        if self.spec.get('log_x', False):
            x_data = np.log10(x_data)

        curve['curve'].setData(x=x_data, y=y_data)