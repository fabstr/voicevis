import numpy as np
import pyqtgraph as pg
from PyQt6 import QtWidgets, QtGui, QtCore

from ui.plot.DirectionalViewBox import DirectionalViewBox
from ui.plot.TimeAxisItem import TimeAxisItem
from signal_processing.AudioFeatures import FeatureSnapshot
from signal_processing.TargetConfig import TargetConfig
import logging


class PlotController(QtCore.QObject):
    """Encapsulates the creation, configuration, structural layout, and
    dynamic updating of a single standard time-series pyqtgraph plot.
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
        bottom_axis = self._create_bottom_axis()
        custom_vb = DirectionalViewBox()

        self.widget = pg.PlotWidget(
            viewBox=custom_vb,
            title=self.spec['title'],
            axisItems={'bottom': bottom_axis}
        )

        if 'x_label' in self.spec:
            self.widget.setLabel('bottom', self.spec['x_label'])
        if 'y_label' in self.spec:
            self.widget.setLabel('left', self.spec['y_label'])

        self._init_playhead()

        self.curves = {}
        self.target_bands = {}

        # 2. Build Plot Items
        self._apply_optimizations()
        self._configure_mouse_behavior()
        self._build_curves()
        self._build_target_bands()
        self._set_initial_bounds()

        self.widget.scene().sigMouseClicked.connect(self._handle_scene_click)

        # 3. Build the Wrapper UI
        self._build_wrapper_ui(initial_size)

        # 4. Apply the theme safely ONCE during initialization
        self.apply_theme()

        if self.spec.get('hidden', False):
            self.container.setVisible(False)

    # --- Structural Hooks for Subclasses ---

    def _create_bottom_axis(self):
        return TimeAxisItem(orientation='bottom')

    def _init_playhead(self):
        self.playhead = pg.InfiniteLine(angle=90, movable=False)
        self.widget.addItem(self.playhead)
        self.playhead.setVisible(True)

    def _build_extra_top_bar_ui(self, layout):
        pass

    def _apply_extra_theme(self):
        pass

    # ---------------------------------------

    def _handle_scene_click(self, event):
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

        self.selector = QtWidgets.QComboBox()
        self.selector.blockSignals(True)
        self.selector.addItems(sorted(list(self.all_specs.keys())))
        self.selector.setCurrentText(self.plot_name)
        self.selector.blockSignals(False)

        self.selector.currentTextChanged.connect(lambda new_name: self.change_plot_callback(self, new_name))
        top_bar_layout.addWidget(self.selector)
        top_bar_layout.addStretch()

        self.checkbox_layout = QtWidgets.QHBoxLayout()
        self.checkbox_layout.setSpacing(10)
        top_bar_layout.addLayout(self.checkbox_layout)
        top_bar_layout.addSpacing(15)

        self._build_extra_top_bar_ui(top_bar_layout)

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
        self.widget.setStyleSheet("border: none;")
        layout.addWidget(self.widget, stretch=1)

    def set_tool_mode(self, mode: str):
        vb = self.widget.getViewBox()
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
            self.widget.setMouseEnabled(x=False, y=False)
        else:
            vb.zoom_axis = None
            vb.setMouseMode(pg.ViewBox.PanMode)
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
        canvas.setTitle(self.spec['title'], **{'color': text_color.name(), 'size': '12pt'})
        self.playhead.setPen(pg.mkPen(text_color, width=2))

        if hasattr(self, 'selector'):
            self.selector.setStyleSheet(f"""
                QComboBox {{ border: 1px solid gray; padding: 2px; background-color: {bg_color.name()}; color: {text_color.name()}; }}
                QComboBox QAbstractItemView {{ background-color: {base_color.name()}; color: {text_color.name()}; selection-background-color: {highlight_color.name()}; }}
            """)

        self._apply_extra_theme()

    def _apply_optimizations(self):
        self.widget.setClipToView(True)
        self.widget.setDownsampling(mode='peak', auto=True)

    def _configure_mouse_behavior(self):
        self.widget.setMouseEnabled(x=self.spec.get('mouse_enabled_x', True), y=self.spec.get('mouse_enabled_y', True))

    def _build_curves(self):
        for name, curve_spec in self.spec['curves'].items():
            self.curves[name] = {}
            if 'analysisResult' in curve_spec:
                self.curves[name]['analysisResult'] = curve_spec['analysisResult']

            edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)
            self.curves[name]['curve'] = self.widget.plot(
                [], symbol="o", pen=None,
                symbolBrush=curve_spec.get('colour', '#FFFFFF'),
                symbolPen=edge_pen,
                symbolSize=curve_spec.get('size', 2)
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
            if self.spec.get('log_x', False):
                x_min = np.log10(max(x_min, 1e-5))
                x_max = np.log10(max(x_max, 1e-5))
            self.widget.setXRange(x_min, x_max, padding=0)

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        curve['data_container'] = data_container

        # 1. Guard against null data
        if x is None or y is None:
            return

        # 2. Safely attempt to cast to float arrays
        try:
            x_arr = np.array(x, dtype=float)
            y_arr = np.array(y, dtype=float)
        except (ValueError, TypeError, SystemError) as e:
            # Drop the update instead of crashing the UI loop
            logging.debug(f"Skipping set_curve_data for {curve_name}: incompatible data types. {e}")
            return

        if 'colorSource' in curve and audio_features_ctx:
            z_feature = curve['colorSource']
            if hasattr(audio_features_ctx, z_feature):
                z_data = getattr(audio_features_ctx, z_feature)
                if len(z_data.x) > 0 and len(x_arr) > 0:
                    z_interp = np.interp(x_arr, z_data.x, z_data.y)
                    cmap = pg.colormap.get('viridis')
                    curve['curve'].setData(x=x_arr, y=y_arr, symbolBrush=cmap.map(z_interp),
                                           symbolPen=pg.mkPen(color=(128, 128, 128, 128), width=0.5))
            else:
                curve['curve'].setData(x=x_arr, y=y_arr)
        else:
            curve['curve'].setData(x=x_arr, y=y_arr)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)
        if not curve:
            return

        result_key = curve.get('analysisResult')
        if not result_key or not hasattr(audio_features_ctx, result_key) or not hasattr(snapshot, result_key):
            return

        data_container = getattr(audio_features_ctx, result_key)
        new_data = getattr(snapshot, result_key)

        # 1. Fast guard against empty data
        if snapshot.time is None or new_data is None:
            return

        # 2. Safely check for NaN by attempting to cast to float
        try:
            if np.isnan(float(new_data)):
                return
        except (ValueError, TypeError):
            # Silently skip this data point if it's a string, object, or other un-coercible type
            return

        curve['data_container'] = data_container

        data_container.x = np.append(data_container.x, snapshot.time)
        data_container.y = np.append(data_container.y, new_data)
        self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)

    def update_target_bands(self, config: TargetConfig):
        for target_name, band in self.target_bands.items():
            bounds = config.get_bounds(target_name)
            if bounds is not None:
                band['min'], band['max'], band['enabled'] = bounds
                band['item'].setRegion([bounds[0], bounds[1]])
                band['item'].setVisible(bounds[2])

    def set_plot_visible(self, visible: bool):
        self.container.setVisible(visible)

    def set_curve_visible(self, curve_name: str, visible: bool):
        if curve_name in self.curves and 'curve' in self.curves[curve_name]:
            self.curves[curve_name]['curve'].setVisible(visible)

    def set_symbol_size(self, size_value: int):
        self.current_size = size_value
        for name, curve in self.curves.items():
            if 'curve' not in curve:
                continue
            c_item = curve['curve']
            if isinstance(c_item, pg.PlotDataItem):
                c_item.opts['symbolSize'] = size_value
                if c_item.scatter is not None:
                    c_item.scatter.setSize(size_value)

    def reset_zoom(self):
        y_min, y_max = self.spec.get('y_min'), self.spec.get('y_max')
        if y_min is not None and y_max is not None:
            self.widget.setYRange(y_min, y_max, padding=0)

        x_min, x_max = self.spec.get('x_min'), self.spec.get('x_max')
        if x_min is not None and x_max is not None:
            if self.spec.get('log_x', False):
                x_min = np.log10(max(x_min, 1e-5))
                x_max = np.log10(max(x_max, 1e-5))
            self.widget.setXRange(x_min, x_max, padding=0)
        elif 'x_min' not in self.spec:
            self.widget.enableAutoRange(axis=pg.ViewBox.XAxis)

    def set_playhead_value(self, value: float):
        self.current_time = value
        self.playhead.setValue(value)