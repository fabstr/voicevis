from ui.plot.PlotController import PlotController

import pyqtgraph as pg
from PyQt6 import QtWidgets, QtGui, QtCore
import numpy as np
import qtawesome as qta

from signal_processing.AudioFeatures import FeatureSnapshot

class InstantaneousPlotController(PlotController):
    """
    Subclass controller dedicated to instantaneous X/Y scatter plots.
    Manages custom fading trail logic, UI elements, and non-time X-axes.
    """

    def __init__(self, plot_name, all_specs, click_callback, change_plot_callback, initial_size=2):
        super().__init__(plot_name, all_specs, click_callback, change_plot_callback, initial_size=initial_size)

        self.widget.setXLink(None)

        if not self.spec.get('x_series'):
            self.widget.getPlotItem().getAxis('bottom').showLabel(False)

        if not self.spec.get('y_series'):
            self.widget.getPlotItem().getAxis('left').showLabel(False)

    def _create_bottom_axis(self):
        # Override to use a raw axis instead of the formatted TimeAxisItem
        return pg.AxisItem(orientation='bottom')

    def _init_playhead(self):
        super()._init_playhead()
        self.playhead.setVisible(False)

    def _build_extra_top_bar_ui(self, layout):
        # Inject the trail length UI specific to instantaneous plots
        self.trail_label = QtWidgets.QLabel("Trail (s):")
        current_trail = self.spec.get('trail_time', 1.0)

        self.trail_edit = QtWidgets.QLineEdit(f"{current_trail:.2f}")
        self.trail_edit.setValidator(QtGui.QDoubleValidator(0.0, 60.0, 2))
        self.trail_edit.setFixedWidth(40)
        self.trail_edit.returnPressed.connect(self.apply_trail_length)

        self.trail_apply_btn = QtWidgets.QPushButton()
        self.trail_apply_btn.setFixedSize(24, 24)
        self.trail_apply_btn.setToolTip("Apply Trail Length")
        self.trail_apply_btn.clicked.connect(self.apply_trail_length)

        layout.addWidget(self.trail_label)
        layout.addWidget(self.trail_edit)
        layout.addWidget(self.trail_apply_btn)
        layout.addSpacing(15)

    def _apply_extra_theme(self):
        # Apply themes to the newly injected UI elements
        palette = QtWidgets.QApplication.palette()
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window).name()
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText).name()

        self.trail_apply_btn.setIcon(qta.icon('fa5s.check', color=text_color))
        self.trail_edit.setStyleSheet(f"""
            QLineEdit {{ 
                border: 1px solid gray; 
                background-color: {bg_color}; 
                color: {text_color}; 
            }}
        """)

        if hasattr(self, 'color_bar'):
            q_text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
            cb_axis = self.color_bar.getAxis('right')
            cb_axis.setPen(q_text_color)
            cb_axis.setTextPen(q_text_color)

    def _build_curves(self):
        # Override curve building to exclusively build scatter items
        has_color_source = False
        color_source_name = ""

        for name, curve_spec in self.spec['curves'].items():
            self.curves[name] = {}
            if 'analysisResult' in curve_spec:
                self.curves[name]['analysisResult'] = curve_spec['analysisResult']

            # Store the colorSource if specified
            if 'colorSource' in curve_spec:
                self.curves[name]['colorSource'] = curve_spec['colorSource']
                has_color_source = True
                color_source_name = curve_spec['colorSource']

            edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)
            scatter_item = pg.ScatterPlotItem(
                size=curve_spec.get('size', 6),
                pen=edge_pen,
                brush=curve_spec.get('colour', '#00FFFF')
            )
            self.widget.addItem(scatter_item)
            self.curves[name]['curve'] = scatter_item

        if has_color_source:
            # interactive=False prevents the user from accidentally zooming the color bar
            self.color_bar = pg.ColorBarItem(values=(0, 1), colorMap=pg.colormap.get('viridis'), width=15,
                                             interactive=False)
            self.color_bar.getAxis('right').setLabel(color_source_name)

            # Place the color bar in the plot's layout grid
            # Row 2 is the main viewbox; Col 4 is right of the right-axis
            self.widget.getPlotItem().layout.addItem(self.color_bar, 2, 4)

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        curve['data_container'] = data_container
        x_key = self.spec.get('x_series')
        y_key = self.spec.get('y_series')

        if audio_features_ctx:
            if x_key and hasattr(audio_features_ctx, x_key):
                curve['x_container'] = getattr(audio_features_ctx, x_key)
            if y_key and hasattr(audio_features_ctx, y_key):
                curve['y_container'] = getattr(audio_features_ctx, y_key)

            if 'colorSource' in curve:
                z_key = curve['colorSource']
                if hasattr(audio_features_ctx, z_key):
                    curve['z_container'] = getattr(audio_features_ctx, z_key)

            self._update_instantaneous_plot(curve, self.current_time)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        x_key = self.spec.get('x_series')
        y_key = self.spec.get('y_series')

        has_x = bool(x_key and hasattr(snapshot, x_key))
        has_y = bool(y_key and hasattr(snapshot, y_key))

        if not has_x and not has_y:
            return

        x_val = getattr(snapshot, x_key) if has_x else 0.0
        y_val = getattr(snapshot, y_key) if has_y else 0.0

        if audio_features_ctx:
            x_cont, y_cont = None, None

            if has_x and hasattr(audio_features_ctx, x_key):
                x_cont = getattr(audio_features_ctx, x_key)
                curve['x_container'] = x_cont

            if has_y and hasattr(audio_features_ctx, y_key):
                y_cont = getattr(audio_features_ctx, y_key)
                curve['y_container'] = y_cont

            z_cont, z_val = None, None
            if 'colorSource' in curve:
                z_key = curve['colorSource']
                if hasattr(audio_features_ctx, z_key) and hasattr(snapshot, z_key):
                    z_cont = getattr(audio_features_ctx, z_key)
                    curve['z_container'] = z_cont
                    z_val = getattr(snapshot, z_key)

            if hasattr(snapshot, 'time') and snapshot.time is not None:
                if has_x and x_val is not None and not np.isnan(x_val) and x_cont is not None:
                    if len(x_cont.x) == 0 or x_cont.x[-1] != snapshot.time:
                        x_cont.x = np.append(x_cont.x, snapshot.time)
                        x_cont.y = np.append(x_cont.y, x_val)

                if has_y and y_val is not None and not np.isnan(y_val) and y_cont is not None:
                    if len(y_cont.x) == 0 or y_cont.x[-1] != snapshot.time:
                        y_cont.x = np.append(y_cont.x, snapshot.time)
                        y_cont.y = np.append(y_cont.y, y_val)

                if z_cont is not None and z_val is not None and not np.isnan(z_val):
                    if len(z_cont.x) == 0 or z_cont.x[-1] != snapshot.time:
                        z_cont.x = np.append(z_cont.x, snapshot.time)
                        z_cont.y = np.append(z_cont.y, z_val)

                self._update_instantaneous_plot(curve, snapshot.time)
                return

        # Fallback (non-context)
        if (has_x and (x_val is None or np.isnan(x_val))) or (has_y and (y_val is None or np.isnan(y_val))):
            return

        curve['curve'].setData(x=[x_val], y=[y_val])

    def set_playhead_value(self, value: float):
        self.current_time = value
        self.playhead.setVisible(False)
        for curve in self.curves.values():
            self._update_instantaneous_plot(curve, value)

    def _update_instantaneous_plot(self, curve: dict, target_time: float):
        x_cont = curve.get('x_container')
        y_cont = curve.get('y_container')

        # We must have at least ONE container to track the time trail
        if x_cont is None and y_cont is None:
            return

        # Determine which container acts as our time-basis source
        primary_cont = x_cont if x_cont is not None else y_cont
        if len(primary_cont.x) == 0:
            return

        trail_time = self.spec.get('trail_time', 0.0)
        min_time = max(0.0, target_time - trail_time)

        valid_mask = (primary_cont.x >= min_time) & (primary_cont.x <= target_time)
        base_times = primary_cont.x[valid_mask]

        if len(base_times) == 0:
            curve['curve'].setData(x=[], y=[])
            return

        # Resolve X values (Default to 0 if missing)
        if x_cont is not None:
            if x_cont is primary_cont:  # CHANGED: '==' to 'is'
                x_vals = x_cont.y[valid_mask]
            else:
                x_vals = np.interp(base_times, x_cont.x, x_cont.y)
        else:
            x_vals = np.zeros_like(base_times)

        # Resolve Y values (Default to 0 if missing)
        if y_cont is not None:
            if y_cont is primary_cont:  # CHANGED: '==' to 'is'
                y_vals = y_cont.y[valid_mask]
            else:
                y_vals = np.interp(base_times, y_cont.x, y_cont.y)
        else:
            y_vals = np.zeros_like(base_times)

        valid_points = ~(np.isnan(x_vals) | np.isnan(y_vals))

        final_x = x_vals[valid_points]
        final_y = y_vals[valid_points]
        final_times = base_times[valid_points]

        if len(final_x) == 0:
            curve['curve'].setData(x=[], y=[])
            return

        curve_specs = list(self.spec.get('curves', {}).values())
        base_color = pg.mkColor(curve_specs[0].get('colour', '#00FFFF') if curve_specs else '#00FFFF')
        r, g, b = base_color.red(), base_color.green(), base_color.blue()

        if trail_time > 0:
            ages = target_time - final_times
            normalized_ages = np.clip(ages / trail_time, 0.0, 1.0)
            alphas = (255 * (1.0 - normalized_ages)).astype(int)
        else:
            alphas = np.full(len(final_x), 255)

        z_cont = curve.get('z_container')
        if z_cont is not None and len(z_cont.x) > 0:
            z_vals = np.interp(final_times, z_cont.x, z_cont.y)
            cmap = pg.colormap.get('viridis')

            valid_z = z_cont.y[~np.isnan(z_cont.y)]
            if len(valid_z) > 0:
                z_min, z_max = np.min(valid_z), np.max(valid_z)
                if z_max > z_min:
                    z_norm = (z_vals - z_min) / (z_max - z_min)
                else:
                    z_norm = np.zeros_like(z_vals)

                if hasattr(self, 'color_bar'):
                    self.color_bar.setLevels((z_min, z_max))
            else:
                z_norm = np.zeros_like(z_vals)

            mapped_colors = cmap.map(z_norm)
            brushes = [pg.mkBrush(c[0], c[1], c[2], a) for c, a in zip(mapped_colors, alphas)]
        else:
            brushes = [pg.mkBrush(r, g, b, a) for a in alphas]

        pens = [pg.mkPen(color=(128, 128, 128, int(a * 0.5)), width=0.5) for a in alphas]

        curve['curve'].setData(x=final_x, y=final_y, brush=brushes, pen=pens)

    def apply_trail_length(self):
        val = float(self.trail_edit.text().replace(',', '.'))
        self.spec['trail_time'] = val
        self.trail_edit.clearFocus()
        self.set_playhead_value(self.current_time)

    def set_symbol_size(self, size_value: int):
        self.current_size = size_value
        for name, curve in self.curves.items():
            if 'curve' not in curve: continue

            c_item = curve['curve']
            final_size = size_value * 2  # Instantaneous size multiplier

            if isinstance(c_item, pg.ScatterPlotItem):
                if type(c_item).__name__ == 'AnnotationMarker': continue
                c_item.setSize(final_size)
                c_item.opts['hoverSize'] = final_size * 1.5

        self.set_playhead_value(self.current_time)