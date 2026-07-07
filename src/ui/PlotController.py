import numpy as np
import pyqtgraph as pg
import qtawesome as qta
from PyQt6 import QtWidgets, QtGui, QtCore

from signal_processing.AudioFeatures import FeatureSnapshot
from signal_processing.TargetConfig import TargetConfig
from ui import AnnotationMarker


class DirectionalViewBox(pg.ViewBox):
    """
    A custom ViewBox that intercepts the RectMode scaling to force
    true 1D visual selection and 1D zooming. Also supports a measurement
    mode to calculate delta X and delta Y without Pythagorean distances.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.zoom_axis = None  # Can be 'x', 'y', or None
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

        # 1. Initialize Core Plot Widget WITH our Custom ViewBox
        time_axis = TimeAxisItem(orientation='bottom')
        custom_vb = DirectionalViewBox()
        self.widget = pg.PlotWidget(
            viewBox=custom_vb,
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
        if self.btn_measure.isChecked():
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

        # --- Interactive Tools (Zoom X / Zoom Y / Measure) ---
        self.btn_zoom_x = QtWidgets.QPushButton()
        self.btn_zoom_y = QtWidgets.QPushButton()
        self.btn_measure = QtWidgets.QPushButton()

        self.btn_zoom_x.setCheckable(True)
        self.btn_zoom_y.setCheckable(True)
        self.btn_measure.setCheckable(True)

        self.btn_zoom_x.setToolTip("Drag to zoom X-axis")
        self.btn_zoom_y.setToolTip("Drag to zoom Y-axis")
        self.btn_measure.setToolTip("Measure Delta Time and Value")

        self.btn_zoom_x.toggled.connect(self._toggle_zoom_x)
        self.btn_zoom_y.toggled.connect(self._toggle_zoom_y)
        self.btn_measure.toggled.connect(self._toggle_measure)

        top_bar_layout.addWidget(self.btn_zoom_x)
        top_bar_layout.addWidget(self.btn_zoom_y)
        top_bar_layout.addWidget(self.btn_measure)

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

    # --- Tool Mutually Exclusive Logic ---

    def _uncheck_others(self, active_btn):
        for btn in [self.btn_zoom_x, self.btn_zoom_y, self.btn_measure]:
            if btn != active_btn and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)

    def _toggle_zoom_x(self, checked):
        if checked:
            self._uncheck_others(self.btn_zoom_x)
        self._update_mouse_mode()

    def _toggle_zoom_y(self, checked):
        if checked:
            self._uncheck_others(self.btn_zoom_y)
        self._update_mouse_mode()

    def _toggle_measure(self, checked):
        if checked:
            self._uncheck_others(self.btn_measure)
        self._update_mouse_mode()

    def _update_mouse_mode(self):
        vb = self.widget.getViewBox()

        # Reset measuring state
        vb.measure_mode = False

        if self.btn_zoom_x.isChecked():
            vb.zoom_axis = 'x'
            vb.setMouseMode(pg.ViewBox.RectMode)
            self.widget.setMouseEnabled(x=True, y=False)

        elif self.btn_zoom_y.isChecked():
            vb.zoom_axis = 'y'
            vb.setMouseMode(pg.ViewBox.RectMode)
            self.widget.setMouseEnabled(x=False, y=True)

        elif self.btn_measure.isChecked():
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

        # Update icons to match the new toggle state
        self._update_icons()

    def _update_icons(self):
        """Forces the correct icon color based on selection state and Qt palette."""
        if not hasattr(self, 'btn_zoom_x'):
            return

        palette = QtWidgets.QApplication.palette()
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText).name()
        highlight_text = palette.color(QtGui.QPalette.ColorRole.HighlightedText).name()

        color_x = highlight_text if self.btn_zoom_x.isChecked() else text_color
        color_y = highlight_text if self.btn_zoom_y.isChecked() else text_color
        color_m = highlight_text if self.btn_measure.isChecked() else text_color

        self.btn_zoom_x.setIcon(qta.icon('fa5s.arrows-alt-h', color=color_x))
        self.btn_zoom_y.setIcon(qta.icon('fa5s.arrows-alt-v', color=color_y))
        self.btn_measure.setIcon(qta.icon('fa5s.ruler-combined', color=color_m))

    # -----------------------

    def _populate_checkboxes(self):
        self.toggles = []
        for curve_key, curve_spec in self.spec.get('curves', {}).items():
            if curve_spec.get('is_spectrogram'):
                continue

            cb = QtWidgets.QCheckBox(curve_key)
            cb.setChecked(True)
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

        # Button stylesheet mapping directly to standard QPalette roles
        if hasattr(self, 'btn_zoom_x'):
            btn_style = f"""
                QPushButton {{
                    background-color: {base_color.name()};
                    border: 1px solid gray;
                    padding: 4px 8px;
                    border-radius: 3px;
                }}
                QPushButton:checked {{
                    background-color: {highlight_color.name()};
                    border: 1px solid {highlight_color.name()};
                }}
                QPushButton:hover:!checked {{
                    background-color: {bg_color.name()};
                }}
            """
            self.btn_zoom_x.setStyleSheet(btn_style)
            self.btn_zoom_y.setStyleSheet(btn_style)
            self.btn_measure.setStyleSheet(btn_style)

            # Immediately force the icon colors to match the new theme
            self._update_icons()

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
            if data_container is not None and hasattr(data_container,
                                                      'magnitude_db') and data_container.magnitude_db.size > 0:
                img.setImage(data_container.magnitude_db.T, autoLevels=True)
                t_max = data_container.x[-1] if len(data_container.x) > 0 else 1.0
                f_max = data_container.y[-1] if len(data_container.y) > 0 else 1.0
                img.setRect(QtCore.QRectF(0, 0, t_max, f_max))
            else:
                img.clear()
            return

        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)

        if 'colorSource' in curve and audio_features_ctx:
            z_feature = curve['colorSource']
            if hasattr(audio_features_ctx, z_feature):
                z_data = getattr(audio_features_ctx, z_feature)
                if len(z_data.x) > 0 and len(x_arr) > 0:
                    z_interp = np.interp(x_arr, z_data.x, z_data.y)
                    z_clipped = np.clip(z_interp, 0.0, 4e-7)
                    z_norm = (z_clipped - 0.0) / (40 - 0.0)
                    z_restricted = 0.1 + (z_norm * 0.90)

                    cmap = pg.colormap.get('viridis')
                    colors = cmap.map(z_interp)
                    brushes = [pg.mkBrush(tuple(c)) for c in colors]
                    edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)

                    curve['curve'].setData(x=x_arr, y=y_arr, symbolBrush=brushes, symbolPen=edge_pen)
            else:
                curve['curve'].setData(x=x_arr, y=y_arr)
        else:
            curve['curve'].setData(x=x_arr, y=y_arr)

    def append_curve_point(self, curve_name: str, snapshot: FeatureSnapshot, audio_features_ctx):
        curve = self.curves.get(curve_name)
        if not curve: return

        result_key = curve['analysisResult']
        if not hasattr(audio_features_ctx, result_key) or not hasattr(snapshot, result_key): return

        data_container = getattr(audio_features_ctx, result_key)
        new_data = getattr(snapshot, result_key)

        if snapshot.time is None or new_data is None: return

        if curve.get('is_spectrogram'):
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

            self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)
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
        # Deselect tools so auto-range isn't immediately fought by mouse modes
        if hasattr(self, 'btn_zoom_x'):
            self.btn_zoom_x.setChecked(False)
            self.btn_zoom_y.setChecked(False)
            self.btn_measure.setChecked(False)

        y_min = self.spec.get('y_min')
        y_max = self.spec.get('y_max')
        if y_min is not None and y_max is not None:
            self.widget.setYRange(y_min, y_max, padding=0)
            self.widget.enableAutoRange(axis=pg.ViewBox.XAxis)
        else:
            self.widget.autoRange()

    def set_playhead_value(self, value: float):
        self.playhead.setValue(value)