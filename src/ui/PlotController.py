import numpy as np
import pyqtgraph as pg
from PyQt6 import QtWidgets, QtGui, QtCore

from signal_processing.AudioFeatures import FeatureSnapshot
from signal_processing.TargetConfig import TargetConfig
from ui import AnnotationMarker


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

        # 1. Initialize Core Plot Widget
        time_axis = TimeAxisItem(orientation='bottom')
        self.widget = pg.PlotWidget(
            title=self.spec['title'],
            axisItems={'bottom': time_axis}
        )

        self.playhead = pg.InfiniteLine(angle=90, movable=False)
        self.widget.addItem(self.playhead)

        self.curves = {}
        self.target_bands = {}

        # 2. Build Plot Items
        self._apply_optimizations()
        self._configure_mouse_behavior()
        self._build_curves()
        self._build_target_bands()
        self._set_initial_bounds()

        self.widget.scene().sigMouseClicked.connect(
            lambda event: self.click_callback(event, self.widget, self.spec['title'])
        )

        # 3. Build the Wrapper UI (Frame, ComboBox, Checkboxes, Slider)
        self._build_wrapper_ui(initial_size)

        # 4. Apply the theme safely ONCE during initialization
        self.apply_theme()

        if self.spec.get('hidden', False):
            self.container.setVisible(False)

    def _build_wrapper_ui(self, initial_size):
        """Constructs the outer QFrame, top control bar, and embeds the plot widget."""
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

        # NOTE: Removed self.selector.setStyleSheet(...) from here!

        self.selector.currentTextChanged.connect(lambda new_name: self.change_plot_callback(self, new_name))
        top_bar_layout.addWidget(self.selector)
        top_bar_layout.addStretch()

        # --- Dynamic Checkboxes ---
        self.checkbox_layout = QtWidgets.QHBoxLayout()
        self.checkbox_layout.setSpacing(10)
        self._populate_checkboxes()
        top_bar_layout.addLayout(self.checkbox_layout)
        top_bar_layout.addSpacing(15)

        # --- Local Point Size Slider ---
        local_size_label = QtWidgets.QLabel("Size:")
        self.local_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.local_slider.setMinimum(1)
        self.local_slider.setMaximum(5)
        self.local_slider.setValue(initial_size)
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

    def _populate_checkboxes(self):
        """Generates checkboxes based on the curves configured in the spec."""
        self.toggles = []
        for curve_key, curve_spec in self.spec.get('curves', {}).items():
            if curve_spec.get('is_spectrogram'):
                continue

            # Format label cleanly
            if curve_spec.get("BW", False):
                label_text = curve_key.replace('_IBW', ' BW').replace('_BW', ' BW')
            else:
                label_text = curve_key

            cb = QtWidgets.QCheckBox(label_text)
            cb.setChecked(True)

            # Bind the toggle directly to this controller's visibility methods
            if curve_spec.get("BW", False):
                cb.toggled.connect(lambda checked, ck=curve_key: self.set_bandwidth_visible(ck, checked))
            else:
                cb.toggled.connect(lambda checked, ck=curve_key: self.set_curve_visible(ck, checked))

            self.checkbox_layout.addWidget(cb)
            self.toggles.append(cb)


    def apply_theme(self):
        palette = QtWidgets.QApplication.palette()
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window)
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
        grid_color = palette.color(QtGui.QPalette.ColorRole.PlaceholderText)

        base_color = palette.color(QtGui.QPalette.ColorRole.Base)
        highlight_color = palette.color(QtGui.QPalette.ColorRole.Highlight)

        # 1. Update pyqtgraph plot background
        self.widget.setBackground(bg_color)

        # 2. Update the surrounding QFrame container background to match
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

        # 3. Update the dropdown list dynamically
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

        # 4. Update the checkboxes text color
        if hasattr(self, 'toggles'):
            for cb in self.toggles:
                cb.setStyleSheet(f"color: {text_color.name()};")

    def _apply_optimizations(self):
        has_dynamic_colors = any('colorSource' in curve for curve in self.spec['curves'].values())
        if has_dynamic_colors:
            self.widget.setClipToView(False)
            self.widget.setDownsampling(auto=False)
        else:
            self.widget.setClipToView(True)
            self.widget.setDownsampling(mode='peak', auto=True)

    def _configure_mouse_behavior(self):
        mouseX = self.spec.get('mouse_enabled_x', True)
        mouseY = self.spec.get('mouse_enabled_y', True)
        self.widget.setMouseEnabled(x=mouseX, y=mouseY)

    def _build_curves(self):
        for name, curve_spec in self.spec['curves'].items():
            self.curves[name] = {'analysisResult': curve_spec['analysisResult']}

            if curve_spec.get('is_spectrogram'):
                img = pg.ImageItem()
                cmap = pg.colormap.get(curve_spec['colour'])
                img.setLookupTable(cmap.getLookupTable())
                self.widget.addItem(img)
                img.setZValue(-30)
                self.curves[name]['is_spectrogram'] = True
                self.curves[name]['image_item'] = img
                continue

            if "BW" in curve_spec and curve_spec["BW"]:
                self.curves[name]['has_bw'] = True
                transparent_pen = pg.mkPen(color=(0, 0, 0, 0), width=1)
                min_curve = pg.PlotCurveItem([], pen=transparent_pen)
                max_curve = pg.PlotCurveItem([], pen=transparent_pen)

                self.curves[name]['bw_curve_min'] = min_curve
                self.curves[name]['bw_curve_max'] = max_curve

                fill_item = pg.FillBetweenItem(min_curve, max_curve, brush=pg.mkBrush(curve_spec['colour']))
                self.curves[name]['fill_band'] = fill_item

                self.widget.addItem(min_curve)
                self.widget.addItem(max_curve)
                self.widget.addItem(fill_item)
                fill_item.setZValue(-10)
            else:
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

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve: return

        if curve.get('is_spectrogram'):
            img = curve['image_item']
            # Draw if data exists, clear if it doesn't
            if data_container is not None and hasattr(data_container, 'magnitude_db') and data_container.magnitude_db.size > 0:
                img.setImage(data_container.magnitude_db.T, autoLevels=True)
                t_max = data_container.x[-1] if len(data_container.x) > 0 else 1.0
                f_max = data_container.y[-1] if len(data_container.y) > 0 else 1.0
                img.setRect(QtCore.QRectF(0, 0, t_max, f_max))
            else:
                img.clear()
            return

        # ... [keep the rest of your existing set_curve_data code] ...

        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)

        if curve.get('has_bw'):
            if data_container and hasattr(data_container, 'BW') and len(data_container.BW) == len(y_arr):
                bw_arr = np.array(data_container.BW, dtype=float)
            else:
                bw_arr = np.zeros_like(y_arr)

            new_upper = y_arr + (bw_arr / 2)
            new_lower = y_arr - (bw_arr / 2)

            gap_threshold = 0.15
            if len(x_arr) > 1:
                gaps = np.where(np.diff(x_arr) > gap_threshold)[0] + 1
                if len(gaps) > 0:
                    x_arr = np.insert(x_arr, gaps, np.nan)
                    new_upper = np.insert(new_upper, gaps, np.nan)
                    new_lower = np.insert(new_lower, gaps, np.nan)

            curve['bw_curve_min'].setData(x=x_arr, y=new_lower)
            curve['bw_curve_max'].setData(x=x_arr, y=new_upper)

        elif 'colorSource' in curve and audio_features_ctx:
            z_feature = curve['colorSource']
            if hasattr(audio_features_ctx, z_feature):
                z_data = getattr(audio_features_ctx, z_feature)
                if len(z_data.x) > 0 and len(x_arr) > 0:
                    z_interp = np.interp(x_arr, z_data.x, z_data.y)
                    z_clipped = np.clip(z_interp, 0.0, 4e-7)
                    z_norm = (z_clipped - 0.0) / (6e-7 - 0.0)
                    z_restricted = 0.1 + (z_norm * 0.90)

                    cmap = pg.colormap.get('viridis')
                    colors = cmap.map(z_restricted)
                    brushes = [pg.mkBrush(tuple(c)) for c in colors]
                    edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)

                    curve['curve'].setData(x=x_arr, y=y_arr, symbolBrush=brushes, symbolPen=edge_pen)
            else:
                curve['curve'].setData(x=x_arr, y=y_arr)
        else:
            curve['curve'].setData(x=x_arr, y=y_arr)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)

        if not curve:
            return

        result_key = curve['analysisResult']
        if not hasattr(audio_features_ctx, result_key) or not hasattr(snapshot, result_key):
            return

        data_container = getattr(audio_features_ctx, result_key)
        new_data = getattr(snapshot, result_key)

        if snapshot.time is None or new_data is None:
            return

        # --- LIVE SPECTROGRAM HANDLING ---
            # --- LIVE SPECTROGRAM HANDLING ---
        if curve.get('is_spectrogram'):
            if not hasattr(new_data, 'magnitude_db') or new_data.magnitude_db.size == 0:
                return

            # First slice initialization
            if len(data_container.x) == 0:
                data_container.x = np.array([snapshot.time])
                data_container.y = new_data.y  # Frequency bins
                data_container.magnitude_db = new_data.magnitude_db.reshape(-1, 1)
            # Append new time column
            else:
                data_container.x = np.append(data_container.x, snapshot.time)
                new_col = new_data.magnitude_db.reshape(-1, 1)

                # Guard rail to ensure frequency resolution hasn't changed mid-recording
                if new_col.shape[0] == data_container.magnitude_db.shape[0]:
                    data_container.magnitude_db = np.hstack((data_container.magnitude_db, new_col))

            self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)
            return

        # --- EXISTING 1D HANDLING ---
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

    def set_bandwidth_visible(self, curve_name: str, visible: bool):
        if curve_name in self.curves and self.curves[curve_name].get('has_bw'):
            c = self.curves[curve_name]
            c['bw_curve_min'].setVisible(visible)
            c['bw_curve_max'].setVisible(visible)
            c['fill_band'].setVisible(visible)

    def set_symbol_size(self, size_value: int):
        target_size = size_value
        for item in self.widget.getPlotItem().items:
            if isinstance(item, pg.ScatterPlotItem):
                if isinstance(item, AnnotationMarker): continue
                item.setSize(target_size)
            elif isinstance(item, pg.PlotDataItem):
                item.opts['symbolSize'] = size_value
                if item.scatter is not None:
                    item.scatter.setSize(target_size)

    def reset_zoom(self):
        y_min = self.spec.get('y_min')
        y_max = self.spec.get('y_max')
        if y_min is not None and y_max is not None:
            self.widget.setYRange(y_min, y_max, padding=0)
            self.widget.enableAutoRange(axis=pg.ViewBox.XAxis)
        else:
            self.widget.autoRange()

    def set_playhead_value(self, value: float):
        self.playhead.setValue(value)