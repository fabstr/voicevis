"""One plot in the grid: a selector bar, a plot, and whatever draws into it.

The cell outlives every change to what it shows. Previously each kind of plot
was a different controller class, so changing a cell's contents meant building
a replacement widget and swapping it into the splitter -- which discarded the
zoom state and orphaned any annotation markers attached to the old plot.
"""

import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

from ui.plot.DirectionalViewBox import DirectionalViewBox
from ui.plot.FrequencyMarkers import MARKERS, MAX_HZ, MIN_HZ
from ui.plot.PlotConfig import PlotConfig, PlotKind
from ui.plot.PlotTheme import PlotTheme
from ui.plot.PlotControls import PlotControls
from ui.plot.layers.FrequencyMarkerLayer import FrequencyMarkerLayer, format_hz
from ui.plot.layers.MultiAxisLayer import MultiAxisLayer
from ui.plot.layers.SelectionLayer import SelectionLayer
from ui.plot.layers.SpectrogramBackground import SpectrogramBackground
from ui.plot.layers.TargetBandLayer import TargetBandLayer
from ui.plot.renderers.SpectrumSliceRenderer import SpectrumSliceRenderer
from ui.plot.renderers.TimeScatterRenderer import TimeScatterRenderer
from ui.plot.renderers.TrailRenderer import TrailRenderer

RENDERERS = {
    PlotKind.TIME_SCATTER: TimeScatterRenderer,
    PlotKind.TRAIL: TrailRenderer,
    PlotKind.SPECTRUM_SLICE: SpectrumSliceRenderer,
}

#: How close a click must land, in pixels, to count as hitting an annotation.
ANNOTATION_HIT_RADIUS = 15

#: Decimal places offered when typing an exact marker frequency.
MARKER_DECIMALS = 1

CONTAINER_NAME = "PlotContainer"


class PlotCell(QtWidgets.QFrame):
    """A single configurable plot."""

    config_changed = QtCore.pyqtSignal(object)          # (PlotCell)
    seek_requested = QtCore.pyqtSignal(float)
    annotation_requested = QtCore.pyqtSignal(object, float, float)   # (cell, x, y)
    annotation_clicked = QtCore.pyqtSignal(object, object)           # (cell, marker)
    #: The selection band was dragged; move the audio by this many seconds.
    audio_move_requested = QtCore.pyqtSignal(float)

    def __init__(self, config: PlotConfig, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.config = config.normalised()
        self.annotation_markers = []
        self._target_config = None

        self.setObjectName(CONTAINER_NAME)

        self.plot_widget = pg.PlotWidget(viewBox=DirectionalViewBox())
        self.plot_widget.setStyleSheet("border: none;")
        self.plot_widget.setDownsampling(mode='peak', auto=True)

        # Drop pyqtgraph's own "Plot Options" menu, keeping the view box one.
        # It applies Downsample and Clip to View to everything the plot tracks
        # as a curve, including ScatterPlotItems, which have no such methods --
        # so opening it and ticking a box raises AttributeError on any trail
        # plot. Its other entries (log mode, FFT, subtract mean) would also
        # silently fight the transforms this module applies itself.
        self.plot_item.setMenuEnabled(False, None)

        self.playhead = pg.InfiniteLine(angle=90, movable=False)
        self.plot_widget.addItem(self.playhead)

        self.spectrogram = SpectrogramBackground(self.plot_item)
        self.targets = TargetBandLayer(self.plot_item)
        self.markers = FrequencyMarkerLayer(self.plot_item)
        self.axes = MultiAxisLayer(self.plot_item)
        self.selection = SelectionLayer(self.plot_item, hub.selection, parent=self)
        self.selection.move_requested.connect(self.audio_move_requested)
        self.selection.range_changed.connect(hub.selection.set_range)
        self.view_box.sigSelectionDragged.connect(self._on_selection_dragged)
        MARKERS.changed.connect(self.markers.refresh)

        self.renderer = None

        self.controls = PlotControls(self.config, parent=self)
        self.controls.config_changed.connect(self._on_controls_changed)

        self._build_layout()

        self.plot_widget.scene().sigMouseClicked.connect(self._on_scene_clicked)

        self._build_marker_menu()

        self._build_renderer()
        self._apply_axes()
        self._sync_to_config()
        self.reset_zoom()
        self.apply_theme()

    def _build_layout(self):
        """Put the axis pickers where the axis labels would be.

            [Y label v]  |  plot            [menu v]
                         |  [X label v]

        pyqtgraph's own axis labels stay empty: the pickers say the same thing
        and can be clicked.
        """
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(5, 5, 5, 5)
        grid.setSpacing(2)

        left = QtCore.Qt.AlignmentFlag.AlignLeft
        centre_v = QtCore.Qt.AlignmentFlag.AlignVCenter
        centre_h = QtCore.Qt.AlignmentFlag.AlignHCenter

        grid.addWidget(self.controls.y_selector, 0, 0, alignment=left | centre_v)
        grid.addWidget(self.plot_widget, 0, 1)
        grid.addWidget(self.controls.options_button, 0, 2,
                       alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.controls.x_selector, 1, 1, alignment=centre_h)

        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)

    # --- Convenience -----------------------------------------------------

    @property
    def plot_item(self):
        return self.plot_widget.getPlotItem()

    @property
    def view_box(self):
        return self.plot_widget.getViewBox()

    @property
    def follows_time_axis(self) -> bool:
        return self.renderer is not None and self.renderer.follows_time_axis

    @property
    def time_axis(self) -> str:
        """Which axis the sync group should drive: 'x', or 'y' when transposed."""
        return self.config.time_axis or 'x'

    # --- Configuration ---------------------------------------------------

    def _on_controls_changed(self, config: PlotConfig):
        self.apply_config(config, from_controls=True)

    def apply_config(self, config: PlotConfig, from_controls=False):
        """Adopt a new configuration in place, keeping the widget alive."""
        config = config.normalised()
        previous = self.config
        kind_changed = config.kind is not previous.kind
        # Moving time between the axes keeps the kind but swaps which side the
        # time axis, the playhead and the sync group act on.
        transposed = config.time_on_y is not previous.time_on_y
        self.config = config

        if not from_controls:
            self.controls.set_config(config)

        if kind_changed or transposed or self.renderer is None:
            self._build_renderer()
            self._apply_axes()
        else:
            # set_config recreates the items, so give them back to the
            # main view box before they are replaced.
            self.axes.clear()
            self.renderer.set_config(config)

        self._sync_to_config()
        self.view_box.clear_measurement()

        if kind_changed or config.x != previous.x or config.y != previous.y:
            self.reset_zoom()

        self.config_changed.emit(self)

    def _sync_to_config(self):
        """Bring the playhead, layers and labels in line with the config."""
        config = self.config
        # The playhead marks a moment in time, so it runs across whichever axis
        # is not the time axis.
        self.playhead.setAngle(0 if config.time_on_y else 90)
        self.playhead.setVisible(self.renderer.shows_playhead)
        self.spectrogram.set_visible(config.spectrogram and self.renderer.supports_spectrogram)
        self.targets.set_series(config.y_specs(), config.x_specs())
        if self._target_config is not None:
            self.targets.update(self._target_config)
        self._sync_markers()
        self.selection.set_axis(config.time_axis)
        self._sync_axes()
        self._apply_labels()
        self.renderer.set_point_size(config.point_size)
        self.refresh_spectrogram()

    def _on_selection_dragged(self, rect):
        """A drag in select mode: take the range off whichever axis is time."""
        axis = self.config.time_axis
        if axis is None:
            return
        low, high = ((rect.left(), rect.right()) if axis == 'x'
                     else (rect.top(), rect.bottom()))
        self.hub.selection.set_range(low, high)

    def _sync_markers(self):
        """Point the marker layer at whichever axis is in Hz, if either.

        A spectrum slice holds log10(Hz) on its axis, so the layer is given the
        renderer's transform rather than being left to assume the axis is in Hz.
        """
        axis = self.config.frequency_axis()
        if axis == 'x':
            self.markers.set_axis('x', self.renderer.x_transform, self.renderer.x_inverse)
        else:
            self.markers.set_axis(axis)

    def _sync_axes(self):
        """Split the multi-valued axis into one scale per series, or undo it."""
        specs = (self.config.x_specs() if self.config.multi_axis() == 'x'
                 else self.config.y_specs())
        self.axes.apply(self.renderer.items, specs, self.config.multi_axis(),
                        self.config.separate_axes, self.hub)

    def _build_renderer(self):
        self.axes.clear()
        if self.renderer is not None:
            self.renderer.detach()
        self.renderer = RENDERERS[self.config.kind](self.plot_item, self.config, self.hub)
        self.renderer.attach()
        self.view_box.measure_formatter = self.renderer.measure_formatter

    def _apply_axes(self):
        self.plot_item.setAxisItems(self.renderer.axis_items())
        self._apply_labels()
        self.apply_theme()

    def _apply_labels(self):
        # The axis pickers carry the labels, so pyqtgraph's own stay empty.
        self.plot_item.setTitle(self.config.title())

    # --- Data and time ---------------------------------------------------

    def on_data_changed(self):
        self.renderer.on_data_changed()
        self.refresh_spectrogram(throttle=self.hub.is_recording)

    def on_time_changed(self, current_time: float):
        if self.renderer.shows_playhead:
            self.playhead.setValue(current_time)
        self.renderer.on_time_changed(current_time)

    def refresh_spectrogram(self, throttle=False):
        if not self.spectrogram.visible:
            return
        self.spectrogram.refresh(self.hub, self.config.value_range(),
                                 transposed=self.config.time_on_y, throttle=throttle)

    # --- Appearance and tools -------------------------------------------

    def refresh_colours(self):
        """Redraw after the series palette changed. Leaves the config and zoom alone."""
        if self.renderer is not None:
            self.axes.clear()
            self.renderer.rebuild()
            self._sync_axes()
            self.renderer.set_point_size(self.config.point_size)
            self.renderer.on_time_changed(self.hub.current_time)

    def set_point_size(self, size: int):
        self.config.point_size = int(size)
        self.controls.set_point_size(size)
        self.renderer.set_point_size(int(size))

    def set_tool_mode(self, mode):
        self.view_box.set_tool_mode(mode)

    def update_targets(self, target_config):
        self._target_config = target_config
        self.targets.update(target_config)

    def reset_zoom(self):
        # With separate axes each series owns its own scale, so the layer
        # restores them all rather than one shared range.
        if self.axes.active:
            self.axes.reset_ranges()
            return

        # The sync group owns the time axis and resets every time plot together,
        # so only restore the axis it does not drive.
        time_axis = self.config.time_axis if self.follows_time_axis else None

        if time_axis != 'y':
            y_range = self.config.effective_y_range()
            if y_range:
                self.plot_widget.setYRange(y_range[0], y_range[1], padding=0)

        if time_axis != 'x':
            x_range = self.config.effective_x_range()
            if x_range:
                low, high = self.renderer.x_transform([x_range[0], x_range[1]])
                self.plot_widget.setXRange(float(low), float(high), padding=0)

    def apply_theme(self):
        theme = PlotTheme.from_palette()
        theme.apply_to_plot(self.plot_widget, self.config.title())
        self.setStyleSheet(theme.container_stylesheet(CONTAINER_NAME))
        for widget in self.controls.widgets():
            widget.setStyleSheet(theme.input_stylesheet())
        self.axes.apply_theme(theme)
        self.playhead.setPen(theme.playhead_pen())
        if self.renderer is not None:
            self.renderer.apply_theme(theme)

    # --- Frequency markers -----------------------------------------------

    def _build_marker_menu(self):
        """Add a marker section to the plot's right-click menu.

        Rebuilt each time it opens: the entries depend on where the click
        landed and on which markers exist at that moment.
        """
        self._marker_menu = QtWidgets.QMenu("Frequency markers")
        self._marker_menu.aboutToShow.connect(self._populate_marker_menu)
        self.view_box.menu.addSeparator()
        self.view_box.menu.addMenu(self._marker_menu)

    def _populate_marker_menu(self):
        menu = self._marker_menu
        menu.clear()

        if not self.markers.enabled:
            menu.addAction("This plot has no frequency axis").setEnabled(False)
            return

        point = self.view_box.last_context_point
        here = self.markers.frequency_at(point)
        existing = self.markers.marker_near(point)

        if existing is not None:
            menu.addAction(f"Move {format_hz(existing)} to...",
                           lambda: self._prompt_marker(existing))
            menu.addAction(f"Remove {format_hz(existing)}",
                           lambda: MARKERS.remove(existing))
            menu.addSeparator()
        elif here is not None:
            menu.addAction(f"Add marker at {format_hz(here)}",
                           lambda: MARKERS.add(here))

        menu.addAction("Add marker at...", lambda: self._prompt_marker(None))

        if len(MARKERS):
            menu.addSeparator()
            menu.addAction("Remove all frequency markers", MARKERS.clear)

    def _prompt_marker(self, existing):
        """Ask for an exact frequency, either for a new marker or to move one."""
        title = "Move frequency marker" if existing is not None else "Add frequency marker"
        start = existing if existing is not None else (
            self.markers.frequency_at(self.view_box.last_context_point) or 220.0)

        value, accepted = QtWidgets.QInputDialog.getDouble(
            self, title, "Frequency (Hz):", float(start),
            MIN_HZ, MAX_HZ, MARKER_DECIMALS)
        if not accepted:
            return

        if existing is None:
            MARKERS.add(value)
        else:
            MARKERS.move(existing, value)

    # --- Annotations -----------------------------------------------------

    def add_annotation_marker(self, marker):
        self.plot_widget.addItem(marker)
        self.annotation_markers.append(marker)

    def remove_annotation_marker(self, marker):
        if marker in self.annotation_markers:
            self.annotation_markers.remove(marker)
        self.plot_widget.removeItem(marker)

    def clear_annotation_markers(self):
        for marker in list(self.annotation_markers):
            self.plot_widget.removeItem(marker)
        self.annotation_markers.clear()

    def _hit_test_annotation(self, scene_pos):
        for marker in self.annotation_markers:
            point = self.view_box.mapViewToScene(QtCore.QPointF(marker.x_val, marker.y_val))
            if point is None:
                continue
            distance = ((point.x() - scene_pos.x()) ** 2 + (point.y() - scene_pos.y()) ** 2) ** 0.5
            if distance <= ANNOTATION_HIT_RADIUS:
                return marker
        return None

    # --- Mouse -----------------------------------------------------------

    def _on_scene_clicked(self, event):
        if self.view_box.measure_mode:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        scene_pos = event.scenePos()
        point = self.view_box.mapSceneToView(scene_pos)

        marker = self._hit_test_annotation(scene_pos)
        if marker is not None:
            self.annotation_clicked.emit(self, marker)
        elif event.double():
            self.annotation_requested.emit(self, point.x(), point.y())
        elif self.renderer.supports_seek:
            # Read the time off whichever axis carries it.
            clicked = point.y() if self.config.time_on_y else point.x()
            self.seek_requested.emit(max(0.0, clicked))

    # --- Teardown --------------------------------------------------------

    def dispose(self):
        """Release plot items before the widget is destroyed."""
        self.clear_annotation_markers()
        self.axes.clear()
        try:
            MARKERS.changed.disconnect(self.markers.refresh)
        except TypeError:
            pass
        self.markers.clear()
        self.selection.clear()
        self.spectrogram.detach()
        self.targets.clear()
        if self.renderer is not None:
            self.renderer.detach()
            self.renderer = None
