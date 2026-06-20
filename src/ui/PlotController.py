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
            # Handle potential negative values safely by treating them as 0
            val = max(0.0, float(v))
            minutes = int(val // 60)
            seconds = val % 60

            # 06.3f ensures a total length of 6 characters:
            # 2 for seconds, 1 for the decimal, 2 for hundreds (e.g., 05.12)
            strings.append(f"{minutes:02d}:{seconds:06.2f}")
        return strings


class PlotController(QtCore.QObject):
    """Encapsulates the creation, configuration, structural layout, and
    dynamic updating of a single pyqtgraph plot and its target bounds.
    """

    def __init__(self, plot_name, plot_spec, click_callback):
        # Initialize the QObject parent
        super().__init__()

        self.plot_name = plot_name
        self.spec = plot_spec

        # 1. Initialize Core Widget with Custom Time Axis
        time_axis = TimeAxisItem(orientation='bottom')
        self.widget = pg.PlotWidget(
            title=self.spec['title'],
            axisItems={'bottom': time_axis}
        )

        # Create the playhead early so apply_theme can configure it
        self.playhead = pg.InfiniteLine(angle=90, movable=False)
        self.widget.addItem(self.playhead)

        self.curves = {}
        self.target_bands = {}

        # 2. Apply dynamic colors
        self.apply_theme()

        # 3. Install event filter to listen for theme changes
        self.widget.installEventFilter(self)

        # Run Internal Build Pipelines
        self._apply_optimizations()
        self._configure_mouse_behavior()
        self._build_curves()
        self._build_target_bands()
        self._set_initial_bounds()

        # Event Routing
        self.widget.scene().sigMouseClicked.connect(
            lambda event: click_callback(event, self.widget, self.spec['title'])
        )

        if self.spec.get('hidden', False):
            self.widget.setVisible(False)

    def eventFilter(self, obj, event):
        """Intercepts palette changes triggered by the OS or the View menu."""
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.ApplicationPaletteChange):
            self.apply_theme()
        return super().eventFilter(obj, event)

    def apply_theme(self):
        """Fetches the current application palette and updates plot colors dynamically."""
        palette = QtWidgets.QApplication.palette()
        bg_color = palette.color(QtGui.QPalette.ColorRole.Window)
        text_color = palette.color(QtGui.QPalette.ColorRole.WindowText)
        grid_color = palette.color(QtGui.QPalette.ColorRole.PlaceholderText)

        # Update Background
        self.widget.setBackground(bg_color)

        # Configure canvas items & styling
        canvas = self.widget.getPlotItem()
        grid_pen = pg.mkPen(color=grid_color, width=1)

        for axis_name in ['bottom', 'left']:
            axis = canvas.getAxis(axis_name)
            axis.setPen(text_color)
            axis.setTextPen(text_color)  # Ensures tick labels update
            axis._gridPen = grid_pen

            # Clear the axis's cached drawing picture so it is forced to redraw
            axis.picture = None
            axis.update()

        # Turn on the grid
        self.widget.showGrid(x=True, y=True, alpha=0.3)

        # Apply System Text Color to the Title
        title_style = {'color': text_color.name(), 'size': '12pt'}
        canvas.setTitle(self.spec['title'], **title_style)

        # Update Playhead Color
        self.playhead.setPen(pg.mkPen(text_color, width=2))

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
                # A semi-transparent medium-grey pen (RGBA) to define boundaries on ANY background
                edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)

                self.curves[name]['curve'] = self.widget.plot(
                    [], symbol="o", pen=None,
                    symbolBrush=curve_spec['colour'],
                    symbolPen=edge_pen,  # <-- Applied globally here
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

            # Encapsulated state storage
            self.target_bands[target_name] = {
                'item': region,
                'min': 0.0,
                'max': 1.0,
                'enabled': False
            }

    def _set_initial_bounds(self):
        if 'y_min' in self.spec and 'y_max' in self.spec:
            self.widget.setYRange(self.spec['y_min'], self.spec['y_max'], padding=0)

    def set_curve_data(self, curve_name: str, x: np.ndarray, y: np.ndarray, data_container=None,
                       audio_features_ctx=None):
        curve = self.curves.get(curve_name)
        if not curve:
            return

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

                    # 1. Standard normalization (0.0 to 1.0)

                    z_norm = (z_clipped - 0.0) / (6e-7 - 0.0)

                    # 2. THE RESTRICTED RANGE TECHNIQUE
                    z_restricted = 0.1 + (z_norm * 0.90)

                    cmap = pg.colormap.get('viridis')
                    # Map using the restricted values so we never hit absolute ends of the colormap
                    colors = cmap.map(z_restricted)
                    brushes = [pg.mkBrush(tuple(c)) for c in colors]

                    # 3. THE MARKER EDGE HACK
                    # A semi-transparent medium-grey pen to define boundaries on ANY background
                    edge_pen = pg.mkPen(color=(128, 128, 128, 128), width=0.5)

                    # Apply both the restricted brushes and the edge pen
                    curve['curve'].setData(
                        x=x_arr,
                        y=y_arr,
                        symbolBrush=brushes,
                        symbolPen=edge_pen
                    )
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
        new_y_val = getattr(snapshot, result_key)
        if snapshot.time is None or new_y_val is None:
            return

        data_container.x = np.append(data_container.x, snapshot.time)
        data_container.y = np.append(data_container.y, new_y_val)

        self.set_curve_data(curve_name, data_container.x, data_container.y, data_container, audio_features_ctx)

    def update_target_bands(self, config: TargetConfig):
        """Maps specific properties from a TargetConfig instance to the
        internal LinearRegionItems registered on this plot canvas.
        """
        for target_name, band in self.target_bands.items():
            # Query the target data unpacking min, max, and enabled state values
            bounds = config.get_bounds(target_name)

            if bounds is not None:
                band_min, band_max, is_enabled = bounds

                band['min'] = band_min
                band['max'] = band_max
                band['enabled'] = is_enabled

                # Update visual coordinates on the viewport canvas
                band['item'].setRegion([band_min, band_max])

                # Manage visual visibility layout criteria based on configuration parameters
                if is_enabled:
                    band['item'].setVisible(True)
                else:
                    band['item'].setVisible(False)

    def set_plot_visible(self, visible: bool):
        """Shows or hides the entire plot panel widget."""
        self.widget.setVisible(visible)

    def set_curve_visible(self, curve_name: str, visible: bool):
        """Shows or hides a standard scatter/line curve item."""
        if curve_name in self.curves and 'curve' in self.curves[curve_name]:
            self.curves[curve_name]['curve'].setVisible(visible)

    def set_bandwidth_visible(self, curve_name: str, visible: bool):
        """Shows or hides the transparent bounding curves and the fill band."""
        if curve_name in self.curves and self.curves[curve_name].get('has_bw'):
            c = self.curves[curve_name]
            c['bw_curve_min'].setVisible(visible)
            c['bw_curve_max'].setVisible(visible)
            c['fill_band'].setVisible(visible)

    def set_symbol_size(self, size_value: int):
        """Updates the rendering size of all valid ScatterPlotItems and

        PlotDataItems drawn on this canvas viewport.
        """
        # Determine the contextual offset size for special plots like Weight
        target_size = size_value + 1
        if self.plot_name in ["Weight", "Fullness"]:
            target_size = target_size + 1

        for item in self.widget.getPlotItem().items:
            # 1. Handle standard ScatterPlotItems
            if isinstance(item, pg.ScatterPlotItem):
                # Safeguard annotation markers using the class type passed down
                if isinstance(item, AnnotationMarker):
                    continue

                item.setSize(target_size)

            # 2. Handle PlotDataItems
            elif isinstance(item, pg.PlotDataItem):
                item.opts['symbolSize'] = size_value
                if item.scatter is not None:
                    item.scatter.setSize(target_size)

    def reset_zoom(self):
        """Resets the viewport zoom, applying fixed min/max spec boundaries where defined,

        and falling back to autoRange elsewhere.
        """
        y_min = self.spec.get('y_min')
        y_max = self.spec.get('y_max')

        # Safely check if limits are explicitly provided (even if they are 0)
        if y_min is not None and y_max is not None:
            # Explicitly lock the Y-axis to your specs
            self.widget.setYRange(y_min, y_max, padding=0)

            # If X-axis should still auto-fit data while Y is locked:
            self.widget.enableAutoRange(axis=pg.ViewBox.XAxis)
        else:
            # Fallback to pure auto-scaling for both axes if no specs exist
            self.widget.autoRange()

    def set_playhead_value(self, value: float):
        """Updates the vertical playhead line's X position on the canvas.

        Args:
            value (float): The target playback time in seconds.
        """
        self.playhead.setValue(value)