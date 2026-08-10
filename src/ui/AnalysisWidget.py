import logging
import queue
import time
import os
import json
import tempfile
import wave
import miniaudio

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
import qtawesome as qta

from ResourceManager import ResourceManager
import SeriesRegistry as Registry
from SeriesRegistry import DEFAULT_POINT_SIZE as defaultSize
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor, TargetConfig
from signal_processing.AudioFeatures import AudioFeatures, FeatureSnapshot
from ui.AnnotationMarker import AnnotationMarker
from ui.HelpWindow import HelpWindow
from ui.TargetConfigDialog import TargetConfigDialog
from workers.AnalysisWorker import AnalysisWorker
from workers.PlaybackWorker import PlaybackWorker
from workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker
from ui.plot import LayoutSerializer
from ui.plot.LayoutSerializer import Layout, LayoutColumn
from ui.plot.PlotCell import PlotCell
from ui.plot.PlotConfig import PlotConfig
from ui.plot.PlotDataHub import PlotDataHub
from ui.plot.TimeAxisSyncGroup import (MODE_IDLE, MODE_PLAYING, MODE_RECORDING,
                                       TimeAxisSyncGroup)

class AnalysisWidget(QtWidgets.QWidget):
    file_loaded_signal = QtCore.pyqtSignal(str)
    new_session_signal = QtCore.pyqtSignal()
    close_session_signal = QtCore.pyqtSignal()

    #################### Init ####################

    def __init__(self):
        super().__init__()

        self.audio_format = None
        self.input_device = None
        self.audio_source = None
        self.audio_data = None
        self.audio_buffer = None
        self.audio_queue = None
        self.poll_timer = None
        self.layout = None
        self.timer = None
        self.menu_bar = None
        self.theme_group = None
        self.action_os_default = None
        self.action_light = None
        self.action_dark = None
        self.record_icon = None
        self.stop_icon = None
        self.play_icon = None
        self.pause_icon = None
        self.save_icon = None
        self.clear_icon = None
        self.reset_zoom_icon = None
        self.zoom_x_icon = None
        self.zoom_y_icon = None
        self.measure_icon = None
        self.record_start_stop_btn = None
        self.playback_btn = None
        self.clear_btn = None
        self.reset_zoom_btn = None
        self.btn_zoom_x = None
        self.btn_zoom_y = None
        self.btn_measure = None
        self.time_label = None
        self.time_edit = None
        self.target_name_label = None
        self.add_icon = None
        self.remove_icon = None
        self.row_label = None
        self.add_row_btn = None
        self.remove_row_btn = None
        self.col_label = None
        self.add_col_btn = None
        self.remove_col_btn = None
        self.size_label = None
        self.size_slider = None
        self.plot_splitter = None
        self.plot_cells = None
        self.columns = None
        self.plot_cells = None
        self.plot_cells = None
        self.record_icon = None
        self.stop_icon = None
        self.play_icon = None
        self.pause_icon = None
        self.save_icon = None
        self.clear_icon = None
        self.reset_zoom_icon = None
        self.zoom_x_icon = None
        self.zoom_y_icon = None
        self.measure_icon = None
        self.loading_dialog = None
        self.worker = None
        self.recording_start_offset = None
        self.rt_worker = None
        self.last_read_pos = None
        self.last_read_pos = None
        self.recording_start_offset = None
        self.play_worker = None
        self.paused_time = None
        self.active_tool_mode = None

        self.resource_manager = ResourceManager()

        self.sampling_rate = 44100

        # Owns the analysed data and the display time; every plot reads through it.
        self.hub = PlotDataHub()
        self.sync_group = TimeAxisSyncGroup(self)

        self.annotations = []
        self.plots = {}

        self.is_recording = False
        self.is_playing = False
        self.playback_start_time = 0.0

        self.audio_device = None
        self.audio_stream = None

        # Track the original file path for annotations, but audio lives in memory
        self.current_audio_file = None
        self.target_config = TargetConfig()

        self.audioFeatureExtractor = AudioFeatureExtractor(self.target_config, self.resource_manager)

        self.setup_GUI()
        self.setup_audio()

        self.help_window = None
        self.sample_text_window = None

        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.save_state_on_exit)

        self.restore_previous_state()

    #################### Shared state ####################

    @property
    def analysedAudioFeatures(self) -> AudioFeatures:
        return self.hub.features

    @analysedAudioFeatures.setter
    def analysedAudioFeatures(self, features: AudioFeatures):
        self.hub.set_features(features)

    @property
    def current_playback_time(self) -> float:
        return self.hub.current_time

    @current_playback_time.setter
    def current_playback_time(self, value: float):
        self.hub.set_time(value)

    def setup_audio(self):
        self.audio_format = QAudioFormat()
        self.audio_format.setSampleRate(self.sampling_rate)
        self.audio_format.setChannelCount(1)
        self.audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self.input_device = QMediaDevices.defaultAudioInput()
        self.audio_source = QAudioSource(self.input_device, self.audio_format, self)

        # Single source of truth for audio samples in memory
        self.audio_data = QByteArray()
        self.audio_buffer = QBuffer(self.audio_data)

        self.audio_queue = queue.Queue()

        self.poll_timer = QtCore.QTimer()
        self.poll_timer.setInterval(33)
        self.poll_timer.timeout.connect(self.read_audio_chunk)

    def setup_GUI(self):
        self.setAcceptDrops(True)
        self.layout = QtWidgets.QVBoxLayout(self)

        self.setupMenu()
        self.setupControlButtons()
        self.setupPlots()

        self.timer = QtCore.QTimer()
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._on_frame_tick)

    def setupMenu(self):
        self.menu_bar = QtWidgets.QMenuBar(self)

        # --- File Menu ---
        file_menu = self.menu_bar.addMenu("&File")
        file_menu.addAction("&New", "Ctrl+N", self.new_session_signal.emit)
        file_menu.addAction("&Open", "Ctrl+O", self.browse_file)
        file_menu.addAction("&Save Annotations", "Ctrl+S", self.save_annotations)
        file_menu.addAction("Save &Audio As...", "Ctrl+Shift+S", self.save_audio)
        file_menu.addSeparator()
        file_menu.addAction("&Close", "Ctrl+W", self.close_session_signal.emit)

        # --- Targets Menu ---
        targets_menu = self.menu_bar.addMenu("&Targets")
        targets_menu.addAction("Set Targets...", self.open_targets_dialog)
        targets_menu.addSeparator()
        targets_menu.addAction("Female", lambda: self.load_targets_from_path("targets/target_female.json"))
        targets_menu.addAction("Male", lambda: self.load_targets_from_path("targets/target_male.json"))
        targets_menu.addSeparator()
        targets_menu.addAction("Import targets...", self.import_targets)
        targets_menu.addAction("Export targets...", self.export_targets)

        # --- View Menu ---
        view_menu = self.menu_bar.addMenu("&View")

        reset_plots_action = view_menu.addAction("Reset plot spacing")
        reset_plots_action.triggered.connect(self.handle_reset_plots)

        view_menu.addSeparator()

        sample_texts_action = view_menu.addAction("Sample Texts")
        sample_texts_action.triggered.connect(self.show_sample_text_window)

        view_menu.addSeparator()


        view_menu.addAction("Load simple layout", lambda: self.load_layout_from_file(self.resource_manager.get_absolute_path("layouts/layout_simple.json")))
        view_menu.addAction("Load medium layout", lambda: self.load_layout_from_file(self.resource_manager.get_absolute_path("layouts/layout_medium.json")))
        view_menu.addAction("Load advanced layout", lambda: self.load_layout_from_file(self.resource_manager.get_absolute_path("layouts/layout_advanced.json")))

        view_menu.addAction("Load Layout...", self.load_layout)
        view_menu.addAction("Save Layout...", self.save_layout)
        view_menu.addSeparator()

        self.theme_group = QtGui.QActionGroup(self)
        self.theme_group.setExclusive(True)

        self.action_os_default = QtGui.QAction("Colour scheme: OS Default", self, checkable=True)
        self.action_light = QtGui.QAction("Colour scheme: Light Mode", self, checkable=True)
        self.action_dark = QtGui.QAction("Colour scheme: Dark Mode", self, checkable=True)

        self.theme_group.addAction(self.action_os_default)
        self.theme_group.addAction(self.action_light)
        self.theme_group.addAction(self.action_dark)

        self.action_os_default.triggered.connect(self.set_theme_os_default)
        self.action_light.triggered.connect(self.set_theme_light)
        self.action_dark.triggered.connect(self.set_theme_dark)

        view_menu.addAction(self.action_os_default)
        view_menu.addAction(self.action_light)
        view_menu.addAction(self.action_dark)
        self.action_os_default.setChecked(True)

        help_menu = self.menu_bar.addMenu("Help")
        open_help_action = help_menu.addAction("Documentation")
        open_help_action.setShortcut("F1")
        open_help_action.triggered.connect(self.show_help_window)

        self.layout.setMenuBar(self.menu_bar)

    def setupControlButtons(self):
        top_buttons_layout = QtWidgets.QHBoxLayout()

        palette = self.palette()
        icon_color = palette.color(QtGui.QPalette.ColorRole.WindowText)

        self.record_icon = qta.icon('fa5s.microphone', color=icon_color)
        self.stop_icon = qta.icon('fa5s.stop', color=icon_color)
        self.play_icon = qta.icon('fa5s.play', color=icon_color)
        self.pause_icon = qta.icon('fa5s.pause', color=icon_color)
        self.save_icon = qta.icon('fa5s.save', color=icon_color)
        self.clear_icon = qta.icon('fa5s.trash', color=icon_color)
        self.reset_zoom_icon = qta.icon('fa6s.maximize', color=icon_color)

        self.zoom_x_icon = qta.icon('fa5s.arrows-alt-h', color=icon_color)
        self.zoom_y_icon = qta.icon('fa5s.arrows-alt-v', color=icon_color)
        self.measure_icon = qta.icon('fa5s.ruler-combined', color=icon_color)

        self.record_start_stop_btn = QtWidgets.QPushButton()
        self.record_start_stop_btn.setFixedSize(40, 40)
        self.record_start_stop_btn.setIcon(self.record_icon)
        self.record_start_stop_btn.setIconSize(QtCore.QSize(20, 20))
        self.record_start_stop_btn.setToolTip("Record")
        self.record_start_stop_btn.clicked.connect(self.handle_start_record_stop)
        top_buttons_layout.addWidget(self.record_start_stop_btn)

        self.playback_btn = QtWidgets.QPushButton()
        self.playback_btn.setFixedSize(40, 40)
        self.playback_btn.setIcon(self.play_icon)
        self.playback_btn.setIconSize(QtCore.QSize(20, 20))
        self.playback_btn.setToolTip("Play/Pause")
        self.playback_btn.clicked.connect(self.handle_playback)
        top_buttons_layout.addWidget(self.playback_btn)

        self.clear_btn = QtWidgets.QPushButton()
        self.clear_btn.setFixedSize(40, 40)
        self.clear_btn.setIcon(self.clear_icon)
        self.clear_btn.setIconSize(QtCore.QSize(20, 20))
        self.clear_btn.setToolTip("Clear")
        self.clear_btn.clicked.connect(self.handle_clear)
        top_buttons_layout.addWidget(self.clear_btn)

        self.reset_zoom_btn = QtWidgets.QPushButton()
        self.reset_zoom_btn.setFixedSize(40, 40)
        self.reset_zoom_btn.setIcon(self.reset_zoom_icon)
        self.reset_zoom_btn.setIconSize(QtCore.QSize(20, 20))
        self.reset_zoom_btn.setToolTip("Reset zoom")
        self.reset_zoom_btn.clicked.connect(self.handle_reset_zoom)
        top_buttons_layout.addWidget(self.reset_zoom_btn)

        top_buttons_layout.addSpacing(10)

        # Tools
        self.btn_zoom_x = QtWidgets.QPushButton()
        self.btn_zoom_x.setFixedSize(40, 40)
        self.btn_zoom_x.setIcon(self.zoom_x_icon)
        self.btn_zoom_x.setIconSize(QtCore.QSize(20, 20))
        self.btn_zoom_x.setToolTip("Zoom X-Axis")
        self.btn_zoom_x.setCheckable(True)
        self.btn_zoom_x.toggled.connect(lambda c: self.handle_tool_toggle('zoom_x', c))
        top_buttons_layout.addWidget(self.btn_zoom_x)

        self.btn_zoom_y = QtWidgets.QPushButton()
        self.btn_zoom_y.setFixedSize(40, 40)
        self.btn_zoom_y.setIcon(self.zoom_y_icon)
        self.btn_zoom_y.setIconSize(QtCore.QSize(20, 20))
        self.btn_zoom_y.setToolTip("Zoom Y-Axis")
        self.btn_zoom_y.setCheckable(True)
        self.btn_zoom_y.toggled.connect(lambda c: self.handle_tool_toggle('zoom_y', c))
        top_buttons_layout.addWidget(self.btn_zoom_y)

        self.btn_measure = QtWidgets.QPushButton()
        self.btn_measure.setFixedSize(40, 40)
        self.btn_measure.setIcon(self.measure_icon)
        self.btn_measure.setIconSize(QtCore.QSize(20, 20))
        self.btn_measure.setToolTip("Measure Time/Value")
        self.btn_measure.setCheckable(True)
        self.btn_measure.toggled.connect(lambda c: self.handle_tool_toggle('measure', c))
        top_buttons_layout.addWidget(self.btn_measure)

        # --- First Stretch to push the time widget to the center ---
        top_buttons_layout.addStretch()

        # --- Time Display/Edit ---
        self.time_label = QtWidgets.QLabel("Time:")

        self.time_edit = QtWidgets.QLineEdit("00:00:00.000")
        self.time_edit.setFixedWidth(110)
        self.time_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.time_edit.returnPressed.connect(self.handle_time_edited)

        # Add them directly to the main layout
        top_buttons_layout.addWidget(self.time_label)
        top_buttons_layout.addWidget(self.time_edit)

        # --- Target Name Label ---
        self.target_name_label = QtWidgets.QLabel(f"|  Target: {self.target_config.config_name}")
        top_buttons_layout.addWidget(self.target_name_label)

        # --- Second Stretch to keep the time widget centered ---
        top_buttons_layout.addStretch()

        # Row layout controls
        # Define the icons for adding/removing
        self.add_icon = qta.icon('fa5s.plus', color=icon_color)
        self.remove_icon = qta.icon('fa5s.minus', color=icon_color)

        # Row layout controls
        self.row_label = QtWidgets.QLabel("Rows:")
        top_buttons_layout.addWidget(self.row_label)

        self.add_row_btn = QtWidgets.QPushButton()
        self.add_row_btn.setFixedSize(40, 40)
        self.add_row_btn.setIcon(self.add_icon)
        self.add_row_btn.setIconSize(QtCore.QSize(20, 20))
        self.add_row_btn.setToolTip("Add row")
        self.add_row_btn.clicked.connect(self.add_plot_row)
        top_buttons_layout.addWidget(self.add_row_btn)

        self.remove_row_btn = QtWidgets.QPushButton()
        self.remove_row_btn.setFixedSize(40, 40)
        self.remove_row_btn.setIcon(self.remove_icon)
        self.remove_row_btn.setIconSize(QtCore.QSize(20, 20))
        self.remove_row_btn.setToolTip("Remove row")
        self.remove_row_btn.clicked.connect(self.remove_plot_row)
        top_buttons_layout.addWidget(self.remove_row_btn)

        top_buttons_layout.addSpacing(10)

        # Column layout controls
        self.col_label = QtWidgets.QLabel("Columns:")
        top_buttons_layout.addWidget(self.col_label)

        self.add_col_btn = QtWidgets.QPushButton()
        self.add_col_btn.setFixedSize(40, 40)
        self.add_col_btn.setIcon(self.add_icon)
        self.add_col_btn.setIconSize(QtCore.QSize(20, 20))
        self.add_col_btn.setToolTip("Add column")
        self.add_col_btn.clicked.connect(self.add_plot_column)
        top_buttons_layout.addWidget(self.add_col_btn)

        self.remove_col_btn = QtWidgets.QPushButton()
        self.remove_col_btn.setFixedSize(40, 40)
        self.remove_col_btn.setIcon(self.remove_icon)
        self.remove_col_btn.setIconSize(QtCore.QSize(20, 20))
        self.remove_col_btn.setToolTip("Remove column")
        self.remove_col_btn.clicked.connect(self.remove_plot_column)
        top_buttons_layout.addWidget(self.remove_col_btn)

        top_buttons_layout.addSpacing(10)

        # Plot item size slider
        self.size_label = QtWidgets.QLabel("Global point size:")
        top_buttons_layout.addWidget(self.size_label)

        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(1)
        self.size_slider.setMaximum(5)
        self.size_slider.setValue(defaultSize)
        self.size_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(1)
        self.size_slider.setFixedWidth(120)
        self.size_slider.valueChanged.connect(self.handle_symbol_size_change)
        top_buttons_layout.addWidget(self.size_slider)

        self.layout.addLayout(top_buttons_layout)

    def handle_tool_toggle(self, tool, checked):
        if checked:
            if tool != 'zoom_x':
                self.btn_zoom_x.blockSignals(True)
                self.btn_zoom_x.setChecked(False)
                self.btn_zoom_x.blockSignals(False)
            if tool != 'zoom_y':
                self.btn_zoom_y.blockSignals(True)
                self.btn_zoom_y.setChecked(False)
                self.btn_zoom_y.blockSignals(False)
            if tool != 'measure':
                self.btn_measure.blockSignals(True)
                self.btn_measure.setChecked(False)
                self.btn_measure.blockSignals(False)
            self.active_tool_mode = tool
        else:
            if self.active_tool_mode == tool:
                self.active_tool_mode = None

        if hasattr(self, 'plot_cells'):
            for controller in self.plot_cells:
                controller.set_tool_mode(self.active_tool_mode)

    def setupPlots(self):
        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.layout.addWidget(self.plot_splitter)

        self.plot_cells = []
        self.columns = []  # Tracks dynamic QSplitter columns

        # Default to 2 columns
        self._create_column()
        self._create_column()

        defaults = [PlotConfig.from_preset(name, self._point_size())
                    for name in Registry.DEFAULT_LAYOUT]

        self._add_specific_row(defaults[0:2])
        self._add_specific_row(defaults[2:4])

    def _point_size(self):
        return self.size_slider.value() if getattr(self, 'size_slider', None) else defaultSize

    def _create_column(self):
        col = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.plot_splitter.addWidget(col)
        self.columns.append(col)
        return col

    def _add_specific_row(self, configs):
        for i, col in enumerate(self.columns):
            config = configs[i] if i < len(configs) else configs[-1]
            cell = self.create_plot_cell(config)
            self.plot_cells.append(cell)
            col.addWidget(cell)

    def create_plot_cell(self, config: PlotConfig = None) -> PlotCell:
        """Build one plot. Every cell is built here; there is no per-kind dispatch."""
        if config is None:
            config = PlotConfig.from_preset(Registry.DEFAULT_PRESET, self._point_size())

        cell = PlotCell(config, self.hub, parent=self)
        cell.config_changed.connect(self._on_cell_config_changed)
        cell.seek_requested.connect(self._on_seek_requested)
        cell.annotation_requested.connect(self._on_annotation_requested)
        cell.annotation_clicked.connect(self._on_annotation_clicked)

        cell.set_tool_mode(self.active_tool_mode)
        cell.update_targets(self.audioFeatureExtractor.target_config)
        self._register_with_sync_group(cell)
        cell.on_data_changed()
        cell.on_time_changed(self.current_playback_time)
        return cell

    def _dispose_cells(self, cells):
        for cell in cells:
            self.sync_group.unregister(cell.view_box)
            cell.dispose()
            cell.setParent(None)
            cell.deleteLater()

    def add_plot_row(self):
        for col in self.columns:
            cell = self.create_plot_cell()
            self.plot_cells.append(cell)
            col.addWidget(cell)

        self.handle_symbol_size_change(self._point_size())

    def remove_plot_row(self):
        if len(self.columns) == 0 or self.columns[0].count() <= 1:
            return

        removed = []
        for col in self.columns:
            widget = col.widget(col.count() - 1)
            if isinstance(widget, PlotCell):
                removed.append(widget)

        self.plot_cells = [c for c in self.plot_cells if c not in removed]
        self._dispose_cells(removed)

    def add_plot_column(self):
        num_rows = self.columns[0].count() if self.columns else 1
        new_col = self._create_column()

        for _ in range(num_rows):
            cell = self.create_plot_cell()
            self.plot_cells.append(cell)
            new_col.addWidget(cell)

        self.handle_symbol_size_change(self._point_size())

    def remove_plot_column(self):
        if len(self.columns) <= 1:
            return

        col_to_remove = self.columns.pop()
        removed = [col_to_remove.widget(i) for i in range(col_to_remove.count())]
        removed = [w for w in removed if isinstance(w, PlotCell)]

        self.plot_cells = [c for c in self.plot_cells if c not in removed]
        self._dispose_cells(removed)
        col_to_remove.deleteLater()

    def _on_cell_config_changed(self, cell: PlotCell):
        """A cell changed what it shows; re-check its place in the time group."""
        self._register_with_sync_group(cell)

    def _register_with_sync_group(self, cell: PlotCell):
        if cell.follows_time_axis:
            self.sync_group.register(cell.view_box)
        else:
            self.sync_group.unregister(cell.view_box)

    def _time_cells(self):
        return [cell for cell in self.plot_cells if cell.follows_time_axis]

    # --- Theme Switching Methods ---
    def set_theme_os_default(self):
        if hasattr(QtGui.QGuiApplication.styleHints(), 'unsetColorScheme'):
            QtGui.QGuiApplication.styleHints().unsetColorScheme()

    def set_theme_light(self):
        if hasattr(QtGui.QGuiApplication.styleHints(), 'setColorScheme'):
            QtGui.QGuiApplication.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)

    def set_theme_dark(self):
        if hasattr(QtGui.QGuiApplication.styleHints(), 'setColorScheme'):
            QtGui.QGuiApplication.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Dark)

    def changeEvent(self, event):
        if event.type() in (QtCore.QEvent.Type.PaletteChange, QtCore.QEvent.Type.ApplicationPaletteChange):
            palette = self.palette()
            icon_color = palette.color(QtGui.QPalette.ColorRole.WindowText)

            self.record_icon = qta.icon('fa5s.microphone', color=icon_color)
            self.stop_icon = qta.icon('fa5s.stop', color=icon_color)
            self.play_icon = qta.icon('fa5s.play', color=icon_color)
            self.pause_icon = qta.icon('fa5s.pause', color=icon_color)
            self.save_icon = qta.icon('fa5s.save', color=icon_color)
            self.clear_icon = qta.icon('fa5s.trash', color=icon_color)
            self.reset_zoom_icon = qta.icon('fa6s.maximize', color=icon_color)

            self.zoom_x_icon = qta.icon('fa5s.arrows-alt-h', color=icon_color)
            self.zoom_y_icon = qta.icon('fa5s.arrows-alt-v', color=icon_color)
            self.measure_icon = qta.icon('fa5s.ruler-combined', color=icon_color)

            if hasattr(self, 'record_stop_btn'):
                if "Record" in self.record_start_stop_btn.toolTip():
                    self.record_start_stop_btn.setIcon(self.record_icon)
                else:
                    self.record_start_stop_btn.setIcon(self.stop_icon)

            if hasattr(self, 'playback_btn'):
                if "Play" in self.playback_btn.toolTip():
                    self.playback_btn.setIcon(self.play_icon)
                else:
                    self.playback_btn.setIcon(self.pause_icon)

            if hasattr(self, 'clear_btn'):
                self.clear_btn.setIcon(self.clear_icon)

            if hasattr(self, 'save_btn'):
                self.save_btn.setIcon(self.save_icon)

            if hasattr(self, 'reset_zoom_btn'):
                self.reset_zoom_btn.setIcon(self.reset_zoom_icon)

            if hasattr(self, 'btn_zoom_x'):
                self.btn_zoom_x.setIcon(self.zoom_x_icon)
                self.btn_zoom_y.setIcon(self.zoom_y_icon)
                self.btn_measure.setIcon(self.measure_icon)

            if hasattr(self, 'plot_cells'):
                for controller in self.plot_cells:
                    if hasattr(controller, 'apply_theme'):
                        controller.apply_theme()

        super().changeEvent(event)

    def show_sample_text_window(self):
        if self.sample_text_window is None:
            from ui.SampleTextWindow import SampleTextWindow
            self.sample_text_window = SampleTextWindow(self.resource_manager)

        self.sample_text_window.show()
        self.sample_text_window.raise_()
        self.sample_text_window.activateWindow()

    #################### File loading/saving ####################

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()

            if file_path.lower().endswith('.json'):
                self.load_annotations_file(file_path)
            elif file_path.lower().endswith(('.wav', '.mp3')):
                self.load_audio_to_memory(file_path)

    def browse_file(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Audio or Annotation File",
            "",
            "Supported Files (*.wav *.mp3 *.json);;Audio Files (*.wav *.mp3);;Annotations (*.json);;All Files (*)"
        )

        if file_name:
            if file_name.lower().endswith('.json'):
                self.load_annotations_file(file_name)
            else:
                self.load_audio_to_memory(file_name)

    def load_audio_to_memory(self, file_path):
        try:
            self.clear_annotations()
            self.current_audio_file = file_path

            # Decode to raw PCM bytes
            decoded_audio = miniaudio.decode_file(
                file_path,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=self.sampling_rate
            )

            # Store in our single source of truth buffer
            self.audio_data.clear()
            self.audio_data.append(decoded_audio.samples)

            self.file_loaded_signal.emit(file_path)
            self.select_analysis_from_memory()

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", f"An error occurred while loading audio:\n{str(e)}")

    def load_annotations_file(self, json_file_path):
        try:
            active_audio_path, annotations, original_audio_path, fallback_audio_path = AnnotationMarker.load_from_file(
                json_file_path)

            if active_audio_path is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Missing Audio",
                    f"The linked audio file could not be found at either location:\n\n"
                    f"Original: {original_audio_path}\n"
                    f"Fallback: {fallback_audio_path}\n\n"
                    f"Please restore the audio file or load it manually."
                )
                return

            self.load_audio_to_memory(active_audio_path)

            for annotation in annotations:
                cell = self._cell_for_annotation(annotation)
                if cell is None:
                    logging.warning("No plot shows %r; skipping its annotation",
                                    annotation.get('series') or annotation.get('plot'))
                    continue
                self._attach_annotation(cell, annotation['time'], annotation['y'],
                                        annotation['text'])

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error",
                                           f"An error occurred while loading annotations:\n{str(e)}")

    def save_audio(self):
        if self.audio_data.isEmpty():
            QtWidgets.QMessageBox.warning(self, "No Audio", "There is no audio currently loaded or recorded to save.")
            return

        default_save_path = "saved_audio.wav"
        if self.current_audio_file:
            base_path, _ = os.path.splitext(self.current_audio_file)
            default_save_path = f"{base_path}_saved.wav"

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Audio As",
            default_save_path,
            "WAV Files (*.wav);;All Files (*)"
        )

        if save_path:
            try:
                # Manually write raw PCM data to disk
                with wave.open(save_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sampling_rate)
                    wf.writeframes(self.audio_data.data())

                self.current_audio_file = save_path
                self.file_loaded_signal.emit(save_path)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error",
                                               f"An error occurred while saving the audio:\n{str(e)}")

    #################### File analysis ####################

    def select_analysis_from_memory(self):
        self.loading_dialog = QtWidgets.QProgressDialog("Analyzing audio...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Please Wait")
        self.loading_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.show()

        # Passes memory bytes to worker instead of disk file path
        self.worker = AnalysisWorker(
            self.audioFeatureExtractor,
            audio_bytes=self.audio_data.data(),
            sample_rate=self.sampling_rate
        )
        self.worker.result_ready.connect(self.on_analysis_finished)
        self.worker.error_occurred.connect(self.on_analysis_error)
        self.worker.finished.connect(self.loading_dialog.close)
        self.worker.start()

    def on_analysis_finished(self, results):
        self.hub.set_features(results)
        self.current_playback_time = 0
        self.update_plots()
        self.handle_reset_zoom()

    def on_analysis_error(self, error_msg):
        QtWidgets.QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis:\n{error_msg}")

    #################### Record, playback ####################

    def handle_start_record_stop(self):
        if self.is_playing:
            self.stop_playback()

        if self.is_recording:
            self.record_stop()
        else:
            self.record_start()


    def record_start(self):
        # Check if there are any available audio input devices
        if not QMediaDevices.audioInputs():
            QtWidgets.QMessageBox.critical(self, "Recording error", f"Could not find any microphone or audio input device.")
            return

        if self.is_playing:
            self.stop_playback()

        self.is_recording = True

        self.record_start_stop_btn.setIcon(self.stop_icon)
        self.record_start_stop_btn.setToolTip("Stop Recording")

        while not self.audio_queue.empty():
            self.audio_queue.get()

        self.recording_start_offset = self.current_playback_time
        self.hub.begin_recording()

        self.rt_worker = RealTimeAnalysisWorker(self.audioFeatureExtractor, self.audio_queue, self.sampling_rate)
        self.rt_worker.new_data_point.connect(self.append_live_data)
        self.rt_worker.start()

        target_byte_pos = int(self.current_playback_time * self.sampling_rate) * 2

        if target_byte_pos > self.audio_data.size():
            padding_size = target_byte_pos - self.audio_data.size()
            self.audio_data.append(QByteArray(padding_size, b'\x00'))

        self.audio_buffer.close()
        self.audio_buffer.open(QIODevice.OpenModeFlag.ReadWrite)

        self.audio_buffer.seek(target_byte_pos)
        self.last_read_pos = target_byte_pos

        self.audio_source.start(self.audio_buffer)
        self.poll_timer.start()
        # Drives the playhead and the sliding window while recording.
        self.timer.start()

    def record_stop(self):
        self.record_start_stop_btn.setIcon(self.record_icon)
        self.record_start_stop_btn.setToolTip("Record")

        self.poll_timer.stop()
        self.read_audio_chunk()

        self.audio_source.stop()
        self.audio_buffer.close()
        self.timer.stop()

        if hasattr(self, 'rt_worker'):
            self.rt_worker.stop()
            self.rt_worker.wait()

        self.hub.end_recording()

        # Clear the recording flag before moving the playhead, or update_playhead
        # reads the position straight back off the (now closed) audio buffer.
        self.is_recording = False
        self.current_playback_time = 0
        self.update_playhead()

        # Audio is now kept entirely in memory buffer, trigger final batch analysis
        self.select_analysis_from_memory()

    def read_audio_chunk(self):
        current_pos = self.audio_buffer.pos()
        if current_pos > self.last_read_pos:
            new_bytes = self.audio_data.mid(self.last_read_pos, current_pos - self.last_read_pos).data()
            self.last_read_pos = current_pos

            if new_bytes:
                self.audio_queue.put(new_bytes)

    def append_live_data(self, latest_point: FeatureSnapshot):
        """Hand one live analysis frame to the hub.

        Plots are not touched here: the frame timer picks the new data up. The
        old code appended the same snapshot once per visible curve, so a feature
        shown in two plots was recorded twice.
        """
        latest_point.time += self.recording_start_offset or 0.0
        self.hub.append_snapshot(latest_point)

    def handle_playback(self):
        if self.is_recording: return
        if not self.is_playing:
            self.seek_and_play()
        else:
            self.stop_playback()

    def handle_clear(self):
        if self.is_playing:
            self.stop_playback()
        if self.is_recording:
            self.record_stop()

        self.current_audio_file = None
        self.audio_data.clear()
        self.hub.clear()

        if hasattr(self, 'recording_start_offset'):
            self.recording_start_offset = 0

        self.clear_annotations()
        self.update_plots()
        self.handle_reset_zoom()
        logging.debug("All data cleared.")

    def stop_playback(self):
        self.is_playing = False
        self.playback_btn.setIcon(self.play_icon)

        if self.play_worker is not None:
            self.play_worker.stop_backend()

        self.timer.stop()

    def seek_and_play(self):
        if self.audio_data.isEmpty():
            return

        target_time = max(0.0, self.current_playback_time)

        current_sr = self.analysedAudioFeatures.sample_rate if getattr(self.analysedAudioFeatures, 'sample_rate',
                                                                       None) else self.sampling_rate
        seek_frame = int(target_time * current_sr)

        if self.play_worker is not None and self.play_worker.is_running():
            self.play_worker.stop_backend()
            self.play_worker.wait()

        self.play_worker = PlaybackWorker(
            samples=self.audio_data.data(),
            seek_frame=seek_frame,
            sample_rate=current_sr
        )
        self.play_worker.playback_finished.connect(self.stop_playback)
        self.play_worker.start()

        self.playback_start_time = time.time() - target_time
        self.is_playing = True
        self.playback_btn.setIcon(self.pause_icon)
        self.timer.start()

    def _transport_mode(self):
        if self.is_recording:
            return MODE_RECORDING
        return MODE_PLAYING if self.is_playing else MODE_IDLE

    def _advance_transport(self):
        """Move the clock forward from whichever source is currently driving."""
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time
            if self.current_playback_time > self.hub.length_seconds:
                self.stop_playback()
                self.current_playback_time = 0

        elif self.is_recording:
            self.current_playback_time = self.audio_buffer.pos() / (2 * self.sampling_rate)
            total_duration = self.audio_data.size() / (2 * self.sampling_rate)
            features = self.hub.features
            features.length_seconds = max(features.length_seconds, total_duration)

    def _on_frame_tick(self):
        """The only per-frame work while playing or recording.

        Curve data is only re-pushed when it has actually changed, so playback
        costs one playhead move per plot instead of a full redraw of every
        series in the grid.
        """
        self._advance_transport()

        if self.hub.take_dirty():
            for cell in self.plot_cells:
                cell.on_data_changed()

        current_time = self.current_playback_time
        for cell in self.plot_cells:
            cell.on_time_changed(current_time)

        self.sync_group.follow(current_time, self._transport_mode(), self.hub.length_seconds)
        self._update_time_edit()

    def _update_time_edit(self):
        if hasattr(self, 'time_edit') and not self.time_edit.hasFocus():
            self.time_edit.setText(self.format_time(self.current_playback_time))

    def update_playhead(self):
        """Move the playhead outside the frame loop, e.g. after a seek."""
        self._advance_transport()
        current_time = self.current_playback_time
        for cell in self.plot_cells:
            cell.on_time_changed(current_time)
        self.sync_group.follow(current_time, self._transport_mode(), self.hub.length_seconds)
        self._update_time_edit()

    #################### Misc plot stuff ####################

    def handle_symbol_size_change(self, value):
        if not getattr(self, 'plot_cells', None):
            return
        for cell in self.plot_cells:
            cell.set_point_size(value)

    def handle_reset_zoom(self):
        if hasattr(self, 'btn_zoom_x'):
            self.btn_zoom_x.setChecked(False)
            self.btn_zoom_y.setChecked(False)
            self.btn_measure.setChecked(False)
            self.active_tool_mode = None

        if not getattr(self, 'plot_cells', None):
            return

        for cell in self.plot_cells:
            cell.set_tool_mode(None)
            cell.reset_zoom()

        # Time plots share one X range, so they are reset together.
        self.sync_group.reset(self.hub.length_seconds)

    def handle_reset_plots(self):
        col_count = len(self.columns)
        if col_count > 0:
            total_width = self.plot_splitter.width()
            self.plot_splitter.setSizes([int(total_width / col_count)] * col_count)
            for col in self.columns:
                row_count = col.count()
                if row_count > 0:
                    total_height = col.height()
                    col.setSizes([int(total_height / row_count)] * row_count)

    def update_plots(self):
        """Re-read every plot from the hub. Called on data changes, not per frame."""
        for cell in self.plot_cells:
            cell.on_data_changed()
        self.hub.take_dirty()
        self.update_playhead()

    #################### Targets ####################

    def open_targets_dialog(self):
        dialog = TargetConfigDialog(self.audioFeatureExtractor.target_config, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            updated_config = dialog.get_confirmed_config()
            self.set_target_config(updated_config)

    def export_targets(self):
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Targets", "", "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        if save_path:
            try:
                config_obj = self.audioFeatureExtractor.target_config
                config_obj.to_json(save_path)
                logging.info(f"Successfully saved targets to: {save_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving targets:\n{str(e)}")

    def import_targets(self):
        open_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Targets", "", "Text/JSON Files (*.txt *.json);;All Files (*)"
        )
        if open_path:
            try:
                new_config = TargetConfig.from_json(open_path)
                self.set_target_config(new_config)
                logging.info(f"Successfully loaded targets from: {open_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Load Error",
                                               f"An error occurred while loading targets:\n{str(e)}")

    def load_targets_from_path(self, target_file_name):
        full_path = self.resource_manager.get_absolute_path(target_file_name)
        if full_path is not None:
            target_config = TargetConfig.from_json(full_path)
            self.set_target_config(target_config)
        else:
            QtWidgets.QMessageBox.critical(self, "Load Error", f"An error occurred while loading targets:\n{str(e)}")

    def set_target_config(self, new_config: TargetConfig):
        self.audioFeatureExtractor.target_config = new_config

        if hasattr(self, 'target_name_label'):
            self.target_name_label.setText(f"|  Target: {new_config.config_name}")

        for cell in self.plot_cells:
            cell.update_targets(new_config)

        self.update_plots()

    #################### Mouse & keyboard actions ####################

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key.Key_Space:
            if self.is_playing:
                self.stop_playback()
            elif not self.audio_data.isEmpty():
                self.seek_and_play()
            event.accept()

        elif key == QtCore.Qt.Key.Key_R:
            if self.is_recording:
                self.record_stop()
            else:
                self.record_start()
            event.accept()

        elif key == QtCore.Qt.Key.Key_D:
            self.handle_clear()
            event.accept()

        else:
            super().keyPressEvent(event)

    def _on_seek_requested(self, target_time: float):
        """A click on a time plot. Non-time plots never emit this."""
        self.current_playback_time = target_time
        if self.is_playing:
            self.seek_and_play()
        else:
            self.update_playhead()

    def _on_annotation_requested(self, cell, target_time, target_y):
        self.add_annotation(cell, target_time, target_y)

    def _on_annotation_clicked(self, cell, marker):
        self.add_annotation(cell, marker.x_val, marker.y_val, existing_marker=marker)

    #################### Annotations  ####################

    def _cell_for_annotation(self, annotation):
        """Find the plot an annotation belongs on.

        Plots no longer have fixed names, so match on the data series first and
        only then fall back to the stored plot name, which is what annotation
        files written by earlier versions carry.
        """
        series_key = annotation.get('series')
        if series_key:
            for cell in self._time_cells():
                if series_key in cell.config.y:
                    return cell

        name = annotation.get('plot')
        if not name:
            return None

        preset = Registry.PRESETS_BY_NAME.get(name)
        for cell in self._time_cells():
            if cell.config.title() == name:
                return cell
            if preset and list(preset.y) == list(cell.config.y):
                return cell
        return None

    def _attach_annotation(self, cell, target_time, target_y, text):
        series_key = cell.config.y[0] if cell.config.y else None
        marker = AnnotationMarker(target_time, target_y, text, cell.config.title(),
                                  cell.plot_widget, self, series_key=series_key)
        cell.add_annotation_marker(marker)
        record = {
            "time": target_time,
            "y": target_y,
            "text": text,
            "plot": cell.config.title(),
            "series": series_key,
            "marker": marker,
            "cell": cell,
        }
        self.annotations.append(record)
        return record

    def add_annotation(self, cell, target_time, target_y, existing_marker=None):
        if self.is_playing:
            self.stop_playback()
            self.paused_time = time.time() - self.playback_start_time

        dialog = QtWidgets.QDialog(self)
        title = "Edit Annotation" if existing_marker else "New Annotation"
        dialog.setWindowTitle(f"{title} - {cell.config.title()} @ {target_time:.2f}s")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(dialog)

        text_edit = QtWidgets.QTextEdit(dialog)
        if existing_marker:
            text_edit.setPlainText(existing_marker.text_val)
        layout.addWidget(text_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(save_btn)

        if existing_marker:
            delete_btn = QtWidgets.QPushButton("Delete")
            btn_layout.addWidget(delete_btn)

            def on_delete():
                cell.remove_annotation_marker(existing_marker)
                self.annotations = [a for a in self.annotations if a.get('marker') != existing_marker]
                dialog.accept()

            delete_btn.clicked.connect(on_delete)

        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_save():
            new_text = text_edit.toPlainText().strip()
            if new_text:
                if existing_marker:
                    existing_marker.text_val = new_text
                    existing_marker.setToolTip(new_text)
                    for ann in self.annotations:
                        if ann.get('marker') == existing_marker:
                            ann['text'] = new_text
                            break
                else:
                    self._attach_annotation(cell, target_time, target_y, new_text)
            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def clear_annotations(self):
        for ann in self.annotations:
            marker, cell = ann.get('marker'), ann.get('cell')
            if marker is not None and cell is not None:
                cell.remove_annotation_marker(marker)
        self.annotations.clear()

    def save_annotations(self):
        if not hasattr(self, 'annotations') or not self.annotations:
            QtWidgets.QMessageBox.warning(self, "No Annotations", "There are no annotations to save yet.")
            return

        default_save_path = ""
        if self.current_audio_file:
            base_path, _ = os.path.splitext(self.current_audio_file)
            default_save_path = f"{base_path}.json"

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotations",
            default_save_path,
            "JSON Files (*.json);;All Files (*)"
        )

        if save_path and self.current_audio_file is not None:
            try:
                markers = [ann['marker'] for ann in self.annotations if 'marker' in ann]
                AnnotationMarker.save_to_file(save_path, markers, self.current_audio_file)
                logging.info(f"Successfully saved annotations to: {save_path}")

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving:\n{str(e)}")

    #################### Help  ####################

    def show_help_window(self):
        if self.help_window is None:
            self.help_window = HelpWindow(self.resource_manager)

        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()

    #################### Layout Management ####################

    def get_current_layout(self) -> Layout:
        layout = Layout(
            global_size=self._point_size(),
            main_splitter_sizes=self.plot_splitter.sizes(),
        )

        for col in self.columns:
            configs = [col.widget(i).config for i in range(col.count())
                       if isinstance(col.widget(i), PlotCell)]
            layout.columns.append(LayoutColumn(configs=configs, sizes=col.sizes()))

        return layout

    def get_current_layout_data(self):
        return LayoutSerializer.dump(self.get_current_layout())

    def apply_layout_data(self, layout_data):
        layout = LayoutSerializer.load(layout_data, self._point_size())
        if layout.is_empty:
            raise ValueError("Layout contains no plots.")

        if hasattr(self, 'size_slider'):
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(layout.global_size)
            self.size_slider.blockSignals(False)

        self._dispose_cells(list(self.plot_cells))
        self.plot_cells.clear()

        for col in self.columns:
            col.setParent(None)
            col.deleteLater()
        self.columns.clear()

        vertical_sizes_to_apply = []

        for column in layout.columns:
            new_col = self._create_column()
            for config in column.configs:
                cell = self.create_plot_cell(config)
                self.plot_cells.append(cell)
                new_col.addWidget(cell)

            if column.sizes:
                vertical_sizes_to_apply.append((new_col, column.sizes))

        self.update_plots()

        def apply_splitter_sizes():
            for col_widget, sizes in vertical_sizes_to_apply:
                col_widget.setSizes(sizes)

            if layout.main_splitter_sizes:
                self.plot_splitter.setSizes(layout.main_splitter_sizes)
            else:
                self.handle_reset_plots()

        QtCore.QTimer.singleShot(0, apply_splitter_sizes)

    def save_layout(self):
        layout_data = self.get_current_layout_data()
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save View Layout", "", "JSON Files (*.json);;All Files (*)"
        )

        if save_path:
            try:
                with open(save_path, 'w') as f:
                    json.dump(layout_data, f, indent=4)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error",
                                               f"An error occurred while saving the layout:\n{str(e)}")

    def load_layout(self):
        open_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load View Layout", "", "JSON Files (*.json);;All Files (*)"
        )

        if open_path:
            self.load_layout_from_file(open_path)

    def load_layout_from_file(self, open_path):
        try:
            with open(open_path, 'r') as f:
                layout_data = json.load(f)
            self.apply_layout_data(layout_data)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error",
                                           f"An error occurred while loading the layout:\n{str(e)}")

    #################### Auto-Save / Auto-Restore Logic ####################

    def save_state_on_exit(self):
        settings = QtCore.QSettings("AudioAnalyzer", "LiveMultiPlotWidget")
        try:
            layout_data = self.get_current_layout_data()
            settings.setValue("last_active_layout", json.dumps(layout_data))

            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
                tmp_path = tmp.name

            self.audioFeatureExtractor.target_config.to_json(tmp_path)

            with open(tmp_path, 'r', encoding='utf-8') as f:
                target_json_str = f.read()

            os.remove(tmp_path)
            settings.setValue("last_target_config", target_json_str)

        except Exception as e:
            logging.error(f"Failed to auto-save application state: {e}")

    def restore_previous_state(self):
        settings = QtCore.QSettings("AudioAnalyzer", "LiveMultiPlotWidget")

        target_json_str = settings.value("last_target_config", "")
        if target_json_str:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
                    tmp.write(target_json_str.encode('utf-8'))
                    tmp_path = tmp.name

                new_config = TargetConfig.from_json(tmp_path)
                self.set_target_config(new_config)

                os.remove(tmp_path)
            except Exception as e:
                logging.error(f"Failed to restore previous target config: {e}")

        layout_str = settings.value("last_active_layout", "")
        if layout_str:
            try:
                layout_data = json.loads(layout_str)
                self.apply_layout_data(layout_data)
            except Exception as e:
                logging.error(f"Failed to restore previous layout: {e}")

    def format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def parse_time(self, time_str: str) -> float:
        try:
            time_str = time_str.strip()
            if not time_str:
                return 0.0

            parts = time_str.split(':')
            total_seconds = 0.0

            if len(parts) == 1:
                total_seconds = float(parts[0])
            elif len(parts) == 2:
                total_seconds = int(parts[0]) * 60 + float(parts[1])
            elif len(parts) >= 3:
                total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

            return total_seconds
        except ValueError:
            return 0.0

    def handle_time_edited(self):
        if self.is_recording:
            self.time_edit.setText(self.format_time(self.current_playback_time))
            self.time_edit.clearFocus()
            return

        time_str = self.time_edit.text()
        new_time = self.parse_time(time_str)

        max_time = getattr(self.analysedAudioFeatures, 'length_seconds', 0.0) or 0.0
        if max_time > 0:
            new_time = max(0.0, min(new_time, max_time))

        self.current_playback_time = new_time

        self.time_edit.clearFocus()

        if self.is_playing:
            self.seek_and_play()
        else:
            self.update_playhead()
            self.time_edit.setText(self.format_time(self.current_playback_time))