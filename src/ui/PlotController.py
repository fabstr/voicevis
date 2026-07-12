import logging

import numpy as np
import pyqtgraph as pg
import qtawesome as qta
from PyQt6 import QtWidgets, QtGui, QtCore

from signal_processing.AudioFeatures import FeatureSnapshot
from signal_processing.TargetConfig import TargetConfig
from ui.AnnotationMarker import AnnotationMarker


class FrequencyAxisItem(pg.AxisItem):
    """Custom AxisItem to force exact X-tick positions and labels for frequency plots."""

    def __init__(self, *args, **kwargs):
        # Safely extract our custom variables before initializing the parent AxisItem
        self.x_ticks = kwargs.pop('x_ticks', None)
        self.is_log_x = kwargs.pop('is_log_x', False)

        super().__init__(*args, **kwargs)

        # Force the axis to allocate 35 pixels of vertical space.
        # This prevents the axis from collapsing to a height of 0 during initialization.
        self.setHeight(35)

    def tickValues(self, minVal, maxVal, size):
        # Fallback to default pyqtgraph behavior if no custom ticks are provided
        if not self.x_ticks:
            return super().tickValues(minVal, maxVal, size)

        # Map the configured tick frequencies to their plot positions
        positions = [np.log10(v) if self.is_log_x else v for v in self.x_ticks]

        # PyQtGraph expects a list of tuples: [(level, [positions]), ...]
        # Using Level 0 designates these as major ticks.
        return [(0, positions)]

    def tickStrings(self, values, scale, spacing):
        if not self.x_ticks:
            return super().tickStrings(values, scale, spacing)

        strings = []
        for v in values:
            # Reverse the log mapping to get the original raw frequency value
            val = (10 ** v) if self.is_log_x else v

            # Snap to the nearest predefined tick to prevent floating-point inaccuracies
            closest_tick = min(self.x_ticks, key=lambda x: abs(x - val))

            # Format nicely for a cleaner UI (e.g., 1000 -> 1k, 10000 -> 10k)
            if closest_tick >= 1000:
                strings.append(f"{closest_tick // 1000}k")
            else:
                strings.append(str(closest_tick))

        return strings

class DirectionalViewBox(pg.ViewBox):
    """
    A custom ViewBox that intercepts the RectMode scaling to force
    true 1D visual selection and 1D zooming. Also supports a measurement
    mode to calculate delta X and delta Y without Pythagorean distances.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.zoom_axis = None
        self.measure_mode = False
        self.measure_start_pos = None

        # Measurement Visuals
        self.measure_rect = QtWidgets.QGraphicsRectItem()
        pen = pg.mkPen('y', width=2, style=QtCore.Qt.PenStyle.DashLine)
        self.measure_rect.setPen(pen)
        self.addItem(self.measure_rect, ignoreBounds=True)
        self.measure_rect.setVisible(False)

        self.measure_text = pg.TextItem(color='y', anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 150))
        self.addItem(self.measure_text, ignoreBounds=True)
        self.measure_text.setVisible(False)

    def mouseDragEvent(self, ev, axis=None):
        if self.measure_mode:
            ev.accept()
            if ev.button() == QtCore.Qt.MouseButton.LeftButton:
                if ev.isStart():
                    self.measure_start_pos = self.mapSceneToView(ev.buttonDownScenePos())
                    self.measure_rect.setVisible(True)
                    self.measure_text.setVisible(True)
                elif ev.isFinish():
                    # Leave the measurement visuals on screen until tool is disabled or a new drag starts
                    pass
                else:
                    if self.measure_start_pos is None:
                        return

                    current_pos = self.mapSceneToView(ev.scenePos())
                    x1, y1 = self.measure_start_pos.x(), self.measure_start_pos.y()
                    x2, y2 = current_pos.x(), current_pos.y()

                    left, right = min(x1, x2), max(x1, x2)
                    bottom, top = min(y1, y2), max(y1, y2)

                    self.measure_rect.setRect(left, bottom, right - left, top - bottom)

                    dx = right - left
                    dy = top - bottom

                    # Format delta X as mm:ss or raw seconds
                    mins = int(dx // 60)
                    secs = dx % 60
                    time_str = f"{mins:02d}:{secs:06.2f}" if dx >= 60 else f"{dx:.3f}s"

                    self.measure_text.setText(f"Δt: {time_str}\nΔy: {dy:.3f}")
                    # Keep the text in the top-right corner of the drag box
                    self.measure_text.setPos(right, top)
            return

        super().mouseDragEvent(ev, axis)

    def updateScaleBox(self, p1, p2):
        """Visually stretch the yellow selection box to span the locked axis."""
        if self.zoom_axis == 'x':
            y_min, y_max = self.boundingRect().top(), self.boundingRect().bottom()
            p1 = QtCore.QPointF(p1.x(), y_min)
            p2 = QtCore.QPointF(p2.x(), y_max)
        elif self.zoom_axis == 'y':
            x_min, x_max = self.boundingRect().left(), self.boundingRect().right()
            p1 = QtCore.QPointF(x_min, p1.y())
            p2 = QtCore.QPointF(x_max, p2.y())
        super().updateScaleBox(p1, p2)

    def setRange(self, rect=None, xRange=None, yRange=None, *args, **kwds):
        """Intercept the zoom application to only apply to the selected axis."""
        if self.zoom_axis is not None:
            if rect is not None:
                current_rect = self.viewRect()

                if self.zoom_axis == 'x':
                    rect = QtCore.QRectF(
                        rect.left(), current_rect.top(),
                        rect.width(), current_rect.height()
                    )
                elif self.zoom_axis == 'y':
                    rect = QtCore.QRectF(
                        current_rect.left(), rect.top(),
                        current_rect.width(), rect.height()
                    )
            else:
                if self.zoom_axis == 'x':
                    yRange = self.viewRange()[1]
                elif self.zoom_axis == 'y':
                    xRange = self.viewRange()[0]

        super().setRange(rect=rect, xRange=xRange, yRange=yRange, *args, **kwds)


class TimeAxisItem(pg.AxisItem):
    """Custom AxisItem to format raw seconds into mm:ss.xxx string format."""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            val = max(0.0, float(v))
            minutes = int(val // 60)
            seconds = val % 60
            strings.append(f"{minutes:02d}:{seconds:06.2f}")
        return strings


class PlotController(QtCore.QObject):
    """Encapsulates the creation, configuration, structural layout, and
    dynamic updating of a single pyqtgraph plot, its target bounds, and its wrapper UI.
    """

    def __init__(self, plot_name, all_specs, click_callback, change_plot_callback, initial_size=2):
        super().__init__()

        self.plot_name = plot_name
        self.all_specs = all_specs
        self.spec = all_specs[plot_name]
        self.click_callback = click_callback
        self.change_plot_callback = change_plot_callback

        self.current_size = initial_size
        self.current_time = 0.0

        # 1. Initialize Core Plot Widget WITH our Custom ViewBox
        is_freq_plot = any(c.get('is_frequency_analysis', False) for c in self.spec.get('curves', {}).values())
        is_inst_plot = self.spec.get('is_instantaneous', False)

        # Select the appropriate custom axis class
        if is_freq_plot:
            bottom_axis = FrequencyAxisItem(
                x_ticks=self.spec.get('x_ticks'),
                is_log_x=self.spec.get('log_x', False),
                orientation='bottom'
            )
        elif is_inst_plot:
            # X axis evaluates arbitrary boundaries, not time formatting
            bottom_axis = pg.AxisItem(orientation='bottom')
        else:
            bottom_axis = TimeAxisItem(orientation='bottom')

        custom_vb = DirectionalViewBox()

        self.widget = pg.PlotWidget(
            viewBox=custom_vb,
            title=self.spec['title'],
            axisItems={'bottom': bottom_axis}
        )

        # --- Apply Axis Labels if defined in the spec ---
        if 'x_label' in self.spec:
            self.widget.setLabel('bottom', self.spec['x_label'])
        if 'y_label' in self.spec:
            self.widget.setLabel('left', self.spec['y_label'])

        self.playhead = pg.InfiniteLine(angle=90, movable=False)
        self.widget.addItem(self.playhead)

        # Explicitly hide playhead for non-time-series plots
        if is_freq_plot or is_inst_plot:
            self.playhead.setVisible(False)

        self.curves = {}
        self.target_bands = {}

        # 2. Build Plot Items
        self._apply_optimizations()
        self._configure_mouse_behavior()
        self._build_curves()
        self._build_target_bands()
        self._set_initial_bounds()

        # Intercept clicks using our internal handler to allow measurement suspension
        self.widget.scene().sigMouseClicked.connect(self._handle_scene_click)

        # 3. Build the Wrapper UI
        self._build_wrapper_ui(initial_size)

        # 4. Apply the theme safely ONCE during initialization
        self.apply_theme()

        if self.spec.get('hidden', False):
            self.container.setVisible(False)

    def _handle_scene_click(self, event):
        """Gatekeeper for click events. Drops them if measuring."""
        if self.widget.getViewBox().measure_mode:
            return
        self.click_callback(event, self.widget, self.spec['title'])

    def _build_wrapper_ui(self, initial_size):
        self.container = QtWidgets.QFrame()
        self.container.setObjectName("PlotContainer")
        self.container.setStyleSheet("#PlotContainer { border: 1px solid gray; margin: 2px; }")

        layout = QtWidgets.QVBoxLayout(self.container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        top_bar_layout = QtWidgets.QHBoxLayout()

        # --- Dropdown Selector ---
        self.selector = QtWidgets.QComboBox()
        self.selector.blockSignals(True)
        sorted_plot_names = sorted(list(self.all_specs.keys()))
        self.selector.addItems(sorted_plot_names)
        self.selector.setCurrentText(self.plot_name)
        self.selector.blockSignals(False)

        self.selector.currentTextChanged.connect(lambda new_name: self.change_plot_callback(self, new_name))
        top_bar_layout.addWidget(self.selector)

        top_bar_layout.addStretch()

        # --- Dynamic Checkboxes ---
        self.checkbox_layout = QtWidgets.QHBoxLayout()
        self.checkbox_layout.setSpacing(10)
        top_bar_layout.addLayout(self.checkbox_layout)
        top_bar_layout.addSpacing(15)

        # --- Trail Length Field (Left Side) ---
        is_inst_plot = self.spec.get('is_instantaneous', False)

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

        top_bar_layout.addWidget(self.trail_label)
        top_bar_layout.addWidget(self.trail_edit)
        top_bar_layout.addWidget(self.trail_apply_btn)

        self.trail_label.setVisible(is_inst_plot)
        self.trail_edit.setVisible(is_inst_plot)
        self.trail_apply_btn.setVisible(is_inst_plot)

        if is_inst_plot:
            top_bar_layout.addSpacing(15)

        # --- Local Point Size Slider (Right Side) ---
        local_size_label = QtWidgets.QLabel("Size:")
        self.local_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.local_slider.setMinimum(1)
        self.local_slider.setMaximum(5)
        self.local_slider.setValue(int(initial_size))
        self.local_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.local_slider.setTickInterval(1)
        self.local_slider.setFixedWidth(80)
        self.local_slider.valueChanged.connect(self.set_symbol_size)

        top_bar_layout.addWidget(local_size_label)
        top_bar_layout.addWidget(self.local_slider)

        layout.addLayout(top_bar_layout)

        # --- Embed Plot Widget ---
        self.widget.setStyleSheet("border: none;")
        layout.addWidget(self.widget, stretch=1)

    def set_tool_mode(self, mode: str):
        vb = self.widget.getViewBox()

        # Reset measuring state
        vb.measure_mode = False

        if mode == 'zoom_x':
            vb.zoom_axis = 'x'
            vb.setMouseMode(pg.ViewBox.RectMode)
            self.widget.setMouseEnabled(x=True, y=False)

        elif mode == 'zoom_y':
            vb.zoom_axis = 'y'
            vb.setMouseMode(pg.ViewBox.RectMode)
            self.widget.setMouseEnabled(x=False, y=True)

        elif mode == 'measure':
            vb.zoom_axis = None
            vb.measure_mode = True
            # Suspend standard panning functionality
            self.widget.setMouseEnabled(x=False, y=False)

        else:
            # Default state
            vb.zoom_axis = None
            vb.setMouseMode(pg.ViewBox.PanMode)
            # Hide the measurement visuals when deactivated
            vb.measure_rect.setVisible(False)
            vb.measure_text.setVisible(False)
            self._configure_mouse_behavior()

    def apply_theme(self):
        palette = QtWidgets.QApplication.palette()
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window)
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
        grid_color = palette.color(QtGui.QPalette.ColorRole.PlaceholderText)
        base_color = palette.color(QtGui.QPalette.ColorRole.Base)
        highlight_color = palette.color(QtGui.QPalette.ColorRole.Highlight)

        self.widget.setBackground(bg_color)

        if hasattr(self, 'container'):
            self.container.setStyleSheet(
                f"#PlotContainer {{ border: 1px solid gray; margin: 2px; background-color: {bg_color.name()}; }}")

        canvas = self.widget.getPlotItem()
        grid_pen = pg.mkPen(color=grid_color, width=1)

        for axis_name in ['bottom', 'left']:
            axis = canvas.getAxis(axis_name)
            axis.setPen(text_color)
            axis.setTextPen(text_color)
            axis._gridPen = grid_pen
            axis.picture = None
            axis.update()

        self.widget.showGrid(x=True, y=True, alpha=0.3)
        title_style = {'color': text_color.name(), 'size': '12pt'}
        canvas.setTitle(self.spec['title'], **title_style)
        self.playhead.setPen(pg.mkPen(text_color, width=2))

        if hasattr(self, 'selector'):
            self.selector.setStyleSheet(f"""
                QComboBox {{ 
                    border: 1px solid gray; 
                    padding: 2px; 
                    background-color: {bg_color.name()}; 
                    color: {text_color.name()}; 
                }}
                QComboBox QAbstractItemView {{ 
                    background-color: {base_color.name()}; 
                    color: {text_color.name()}; 
                    selection-background-color: {highlight_color.name()}; 
                }}
            """)

        # Style the new Trail Length fields
        if hasattr(self, 'trail_apply_btn'):
            self.trail_apply_btn.setIcon(qta.icon('fa5s.check', color=text_color.name()))
            self.trail_edit.setStyleSheet(f"""
                QLineEdit {{ 
                    border: 1px solid gray; 
                    background-color: {bg_color.name()}; 
                    color: {text_color.name()}; 
                }}
            """)

    def _apply_optimizations(self):
        self.widget.setClipToView(True)

        # Downsampling peak mode is fine to keep, though it relies on standard lines
        self.widget.setDownsampling(mode='peak', auto=True)

    def _configure_mouse_behavior(self):
        mouseX = self.spec.get('mouse_enabled_x', True)
        mouseY = self.spec.get('mouse_enabled_y', True)
        self.widget.setMouseEnabled(x=mouseX, y=mouseY)

    def _build_curves(self):
        for name, curve_spec in self.spec['curves'].items():
            self.curves[name] = {}
            if 'analysisResult' in curve_spec:
                self.curves[name]['analysisResult'] = curve_spec['analysisResult']

            if curve_spec.get('is_spectrogram'):
                img = pg.ImageItem()
                cmap = pg.colormap.get(curve_spec['colour'])
                img.setLookupTable(cmap.getLookupTable())
                self.widget.addItem(img)
                img.setZValue(-30)
                self.curves[name]['is_spectrogram'] = True
                self.curves[name]['image_item'] = img
                continue

            # --- Frequency Analysis Plot Support ---
            if curve_spec.get('is_frequency_analysis'):
                pen = pg.mkPen(color=curve_spec.get('colour', '#9370DB'), width=1.5)
                brush = pg.mkBrush(curve_spec.get('fill_colour', (147, 112, 219, 150)))
                fill_lvl = self.spec.get('y_min', -100)

                self.curves[name]['curve'] = self.widget.plot(
                    [], pen=pen, fillLevel=fill_lvl, fillBrush=brush
                )
                self.curves[name]['is_frequency_analysis'] = True
                continue

            # --- Instantaneous X/Y Plot Support ---
            if self.spec.get('is_instantaneous'):
                edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)
                # Use a pure ScatterPlotItem instead of PlotDataItem to avoid line-optimization bugs
                scatter_item = pg.ScatterPlotItem(
                    size=curve_spec.get('size', 6),
                    pen=edge_pen,
                    brush=curve_spec.get('colour', '#00FFFF')
                )
                self.widget.addItem(scatter_item)
                self.curves[name]['curve'] = scatter_item
                continue

            # --- Standard Time-Series Support ---
            edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)
            self.curves[name]['curve'] = self.widget.plot(
                [], symbol="o", pen=None,
                symbolBrush=curve_spec['colour'],
                symbolPen=edge_pen,
                symbolSize=curve_spec['size']
            )
            if 'colorSource' in curve_spec:
                self.curves[name]['colorSource'] = curve_spec['colorSource']

    def _build_target_bands(self):
        for target_name, target_spec in self.spec.get('targets', {}).items():
            region = pg.LinearRegionItem(orientation='horizontal', movable=False, brush=target_spec['colour'])
            for line in region.lines:
                line.setPen(pg.mkPen(None))
                line.setHoverPen(pg.mkPen(None))
            region.setZValue(-20)
            region.setVisible(False)
            self.widget.addItem(region)
            self.target_bands[target_name] = {'item': region, 'min': 0.0, 'max': 1.0, 'enabled': False}

    def _set_initial_bounds(self):
        if 'y_min' in self.spec and 'y_max' in self.spec:
            self.widget.setYRange(self.spec['y_min'], self.spec['y_max'], padding=0)

        if 'x_min' in self.spec and 'x_max' in self.spec:
            x_min, x_max = self.spec['x_min'], self.spec['x_max']

            # Convert limits to log10 if the axis is logarithmic
            if self.spec.get('log_x', False):
                x_min = np.log10(max(x_min, 1e-5))  # Prevent log(0)
                x_max = np.log10(max(x_max, 1e-5))

            self.widget.setXRange(x_min, x_max, padding=0)

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve:
            logging.error(f"No curve {curve_name}")
            return

        # Cache container for scrubbing
        curve['data_container'] = data_container

        # --- Handle Instantaneous Data Restores ---
        if self.spec.get('is_instantaneous'):
            x_key = self.spec.get('x_series')
            y_key = self.spec.get('y_series')
            if audio_features_ctx and hasattr(audio_features_ctx, x_key) and hasattr(audio_features_ctx, y_key):
                curve['x_container'] = getattr(audio_features_ctx, x_key)
                curve['y_container'] = getattr(audio_features_ctx, y_key)
                self._update_instantaneous_plot(curve, self.playhead.value())
            return

        if curve.get('is_spectrogram'):
            img = curve['image_item']
            if data_container is not None and hasattr(data_container,
                                                      'magnitude_db') and data_container.magnitude_db.size > 0:
                img.setImage(data_container.magnitude_db.T)
                t_max = data_container.x[-1] if len(data_container.x) > 0 else 1.0
                f_max = data_container.y[-1] if len(data_container.y) > 0 else 1.0
                img.setRect(QtCore.QRectF(0, 0, t_max, f_max))
            else:
                img.clear()
            return

        # --- Handle Complete Data Restores for Frequency Analysis ---
        if curve.get('is_frequency_analysis'):
            self._update_frequency_plot(curve, data_container, self.playhead.value())
            return

        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)

        if 'colorSource' in curve and audio_features_ctx:
            z_feature = curve['colorSource']
            if hasattr(audio_features_ctx, z_feature):
                z_data = getattr(audio_features_ctx, z_feature)
                if len(z_data.x) > 0 and len(x_arr) > 0:
                    z_interp = np.interp(x_arr, z_data.x, z_data.y)
                    cmap = pg.colormap.get('viridis')
                    colors = cmap.map(z_interp)
                    curve['curve'].setData(x=x_arr, y=y_arr, symbolBrush=colors,
                                           symbolPen=pg.mkPen(color=(128, 128, 128, 128), width=0.5))
            else:
                curve['curve'].setData(x=x_arr, y=y_arr)
        else:
            curve['curve'].setData(x=x_arr, y=y_arr)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)
        if not curve:
            logging.error(f"No curve {curve_name}")
            return

        # --- Handle Instantaneous Appends ---
        if self.spec.get('is_instantaneous'):
            x_key = self.spec.get('x_series')
            y_key = self.spec.get('y_series')

            if hasattr(snapshot, x_key) and hasattr(snapshot, y_key):
                x_val = getattr(snapshot, x_key)
                y_val = getattr(snapshot, y_key)

                # Cache full structures so that set_playhead_value can scrub this chart backwards
                if hasattr(audio_features_ctx, x_key) and hasattr(audio_features_ctx, y_key):
                    x_cont = getattr(audio_features_ctx, x_key)
                    y_cont = getattr(audio_features_ctx, y_key)
                    curve['x_container'] = x_cont
                    curve['y_container'] = y_cont

                    if hasattr(snapshot, 'time') and snapshot.time is not None:
                        # Append directly to underlying X/Y arrays if not already present.
                        # (This prevents a crash if the parent time-series plots are currently hidden)
                        if x_val is not None and not np.isnan(x_val):
                            if len(x_cont.x) == 0 or x_cont.x[-1] != snapshot.time:
                                x_cont.x = np.append(x_cont.x, snapshot.time)
                                x_cont.y = np.append(x_cont.y, x_val)

                        if y_val is not None and not np.isnan(y_val):
                            if len(y_cont.x) == 0 or y_cont.x[-1] != snapshot.time:
                                y_cont.x = np.append(y_cont.x, snapshot.time)
                                y_cont.y = np.append(y_cont.y, y_val)

                        self._update_instantaneous_plot(curve, snapshot.time)
                        return

                # Fallback if no valid arrays or time exist yet
                if x_val is not None and y_val is not None and not np.isnan(x_val) and not np.isnan(y_val):
                    curve['curve'].setData(x=[x_val], y=[y_val])
            return

        result_key = curve.get('analysisResult')
        if not result_key:
            return

        if not hasattr(audio_features_ctx, result_key) or not hasattr(snapshot, result_key):
            logging.error(f"Could not find analysis result {result_key} for curve {curve_name}")
            return

        data_container = getattr(audio_features_ctx, result_key)
        new_data = getattr(snapshot, result_key)

        if snapshot.time is None or new_data is None:
            return

        # Cache container for scrubbing
        curve['data_container'] = data_container

        # Unify Spectrogram and Frequency Analysis as they both use the same FFT output structures
        if curve.get('is_spectrogram') or curve.get('is_frequency_analysis'):
            if not hasattr(new_data, 'magnitude_db') or new_data.magnitude_db.size == 0: return

            if len(data_container.x) == 0:
                data_container.x = np.array([snapshot.time])
                data_container.y = new_data.y
                data_container.magnitude_db = new_data.magnitude_db.reshape(-1, 1)
            else:
                data_container.x = np.append(data_container.x, snapshot.time)
                new_col = new_data.magnitude_db.reshape(-1, 1)

                if new_col.shape[0] == data_container.magnitude_db.shape[0]:
                    data_container.magnitude_db = np.hstack((data_container.magnitude_db, new_col))

            if curve.get('is_spectrogram'):
                self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)
            else:
                # Update the Frequency Plot Instantly to the appended time
                self._update_frequency_plot(curve, data_container, snapshot.time)
            return

        else:
            if np.isnan(new_data):
                return

            data_container.x = np.append(data_container.x, snapshot.time)
            data_container.y = np.append(data_container.y, new_data)
            self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)

    def update_target_bands(self, config: TargetConfig):
        for target_name, band in self.target_bands.items():
            bounds = config.get_bounds(target_name)
            if bounds is not None:
                band_min, band_max, is_enabled = bounds
                band['min'] = band_min
                band['max'] = band_max
                band['enabled'] = is_enabled
                band['item'].setRegion([band_min, band_max])
                band['item'].setVisible(is_enabled)

    def set_plot_visible(self, visible: bool):
        self.container.setVisible(visible)

    def set_curve_visible(self, curve_name: str, visible: bool):
        if curve_name in self.curves and 'curve' in self.curves[curve_name]:
            self.curves[curve_name]['curve'].setVisible(visible)

    def set_symbol_size(self, size_value: int):
        self.current_size = size_value

        for name, curve in self.curves.items():
            if 'curve' not in curve: continue

            c_item = curve['curve']
            multiplier = 2 if self.spec.get('is_instantaneous') else 1
            final_size = size_value * multiplier

            if isinstance(c_item, pg.ScatterPlotItem):
                if type(c_item).__name__ == 'AnnotationMarker': continue
                c_item.setSize(final_size)

                # Also update the hover expansion size dynamically
                if self.spec.get('is_instantaneous'):
                    c_item.opts['hoverSize'] = final_size * 1.5

            elif isinstance(c_item, pg.PlotDataItem):
                c_item.opts['symbolSize'] = final_size
                if c_item.scatter is not None:
                    c_item.scatter.setSize(final_size)

        # Force a data redraw using explicit time
        if self.spec.get('is_instantaneous') or any(
                c.get('is_frequency_analysis') for c in self.spec.get('curves', {}).values()):
            self.set_playhead_value(self.current_time)

    def reset_zoom(self):
        y_min = self.spec.get('y_min')
        y_max = self.spec.get('y_max')

        if y_min is not None and y_max is not None:
            self.widget.setYRange(y_min, y_max, padding=0)

        x_min = self.spec.get('x_min')
        x_max = self.spec.get('x_max')

        if x_min is not None and x_max is not None:
            if self.spec.get('log_x', False):
                x_min = np.log10(max(x_min, 1e-5))
                x_max = np.log10(max(x_max, 1e-5))
            self.widget.setXRange(x_min, x_max, padding=0)
        elif 'x_min' not in self.spec:
            self.widget.enableAutoRange(axis=pg.ViewBox.XAxis)

    def set_playhead_value(self, value: float):
        self.current_time = value  # <-- Store the exact time here

        is_freq_plot = any(c.get('is_frequency_analysis', False) for c in self.spec.get('curves', {}).values())
        is_inst_plot = self.spec.get('is_instantaneous', False)

        # Enforce hidden state during playback updates
        if is_freq_plot or is_inst_plot:
            self.playhead.setVisible(False)
        else:
            self.playhead.setVisible(True)
            self.playhead.setValue(value)

        # When scrubbing, update any dynamic plots to show exactly what's happening at this time
        for curve in self.curves.values():
            if curve.get('is_frequency_analysis'):
                self._update_frequency_plot(curve, curve.get('data_container'), value)
            elif self.spec.get('is_instantaneous'):
                self._update_instantaneous_plot(curve, value)

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

    def _update_instantaneous_plot(self, curve: dict, target_time: float):
        x_cont = curve.get('x_container')
        y_cont = curve.get('y_container')

        if x_cont is None or y_cont is None:
            return

        # Ensure we have data
        if len(x_cont.x) == 0 or len(y_cont.x) == 0:
            return

        trail_time = self.spec.get('trail_time', 0.0)
        min_time = max(0.0, target_time - trail_time)

        # Slice the X array for points within the time window
        valid_x_mask = (x_cont.x >= min_time) & (x_cont.x <= target_time)
        x_times = x_cont.x[valid_x_mask]
        x_vals = x_cont.y[valid_x_mask]

        if len(x_times) == 0:
            curve['curve'].setData(x=[], y=[])
            return

        # Interpolate the Y array to precisely align with X's time axis.
        # This guarantees safety against varying sample rates or mismatched data lengths.
        y_vals = np.interp(x_times, y_cont.x, y_cont.y)

        # Filter out NaNs to prevent plotting glitches
        valid_points = ~(np.isnan(x_vals) | np.isnan(y_vals))
        final_x = x_vals[valid_points]
        final_y = y_vals[valid_points]
        final_times = x_times[valid_points]

        if len(final_x) == 0:
            curve['curve'].setData(x=[], y=[])
            return

        # --- Dynamic Alpha/Fading Logic ---

        # Grab the configured color for this plot
        curve_specs = list(self.spec.get('curves', {}).values())
        base_color = pg.mkColor(curve_specs[0].get('colour', '#00FFFF') if curve_specs else '#00FFFF')
        r, g, b = base_color.red(), base_color.green(), base_color.blue()

        if trail_time > 0:
            # Calculate how old each point is (0 is current, trail_time is oldest)
            ages = target_time - final_times

            # Normalize ages between 0.0 and 1.0
            normalized_ages = np.clip(ages / trail_time, 0.0, 1.0)

            # Map age to an alpha value (255 = fully visible, 0 = invisible)
            alphas = (255 * (1.0 - normalized_ages)).astype(int)
        else:
            alphas = np.full(len(final_x), 255)

        # Build an array of brushes and pens so both the fill and the outline fade
        brushes = [pg.mkBrush(r, g, b, a) for a in alphas]
        pens = [pg.mkPen(color=(128, 128, 128, int(a * 0.5)), width=0.5) for a in alphas]

        # Call setData using ScatterPlotItem's direct parameters
        curve['curve'].setData(x=final_x, y=final_y, brush=brushes, pen=pens)

    def apply_trail_length(self):
        val = float(self.trail_edit.text().replace(',', '.'))
        self.spec['trail_time'] = val
        self.trail_edit.clearFocus()

        # Force a redraw using the explicitly tracked time
        self.set_playhead_value(self.current_time)