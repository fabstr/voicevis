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
from signal_processing import AudioEdit
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor, TargetConfig
from signal_processing.AudioFeatures import AudioFeatures, FeatureSnapshot
from signal_processing.ChunkedAnalysis import ChunkedAudioAnalysis
from signal_processing.GainMap import GainMap, INFINITY
from ui.AnnotationMarker import AnnotationMarker
from ui.AudioHistory import AudioHistory
from ui.HelpWindow import HelpWindow
from ui.ResponsiveToolBar import ResponsiveToolBar, ToolbarGroup
from ui.SeriesColourDialog import SeriesColourDialog
from ui.TargetConfigDialog import TargetConfigDialog
from workers.AnalysisWorker import AnalysisWorker
from workers.PlaybackWorker import PlaybackWorker
from workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker
from ui.plot import LayoutSerializer
from ui.plot.FrequencyMarkers import MARKERS
from ui.plot.LayoutSerializer import Layout, LayoutColumn
from ui.plot.PlotCell import PlotCell
from ui.plot.PlotConfig import PlotConfig
from ui.plot.PlotDataHub import PlotDataHub
from ui.plot.TimeAxisSyncGroup import (MODE_IDLE, MODE_PLAYING, MODE_RECORDING,
                                       TimeAxisSyncGroup)

#: How long to wait for a background thread to finish when closing a session.
WORKER_SHUTDOWN_MS = 2000

#: Icons for the audio-editing tools. Both are qtawesome names, so swapping in
#: a different look is a one-line change.
SELECT_ICON = 'mdi6.selection-drag'
SILENCE_ICON = 'mdi6.volume-off'
CUT_ICON = 'fa5s.cut'
GAIN_ICON = 'fa5s.sliders-h'
UNDO_ICON = 'mdi6.undo'
REDO_ICON = 'mdi6.redo'

SELECT_TOOLTIP = ("Select audio: drag on a time plot to select, drag the band "
                  "to move that audio, drag its edges to adjust")

#: How far a gain can be pushed either way, in dB. Wide enough to rescue a
#: recording made at the wrong input level, narrow enough to stay a gain.
GAIN_LIMIT_DB = 40.0


class AnalysisWidget(QtWidgets.QWidget):
    file_loaded_signal = QtCore.pyqtSignal(str)
    new_session_signal = QtCore.pyqtSignal()
    close_session_signal = QtCore.pyqtSignal()
    #: The series palette is application-wide, so every window has to redraw.
    series_colours_changed = QtCore.pyqtSignal()

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
        #: (action, qtawesome name) for every menu entry, so a change of colour
        #: scheme can redraw the lot.
        self._icon_actions = []
        self._icon_colour = self.palette().color(QtGui.QPalette.ColorRole.WindowText)
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
        self.action_record = None
        self.action_play = None
        self.action_clear = None
        self.action_select = None
        self.action_silence = None
        self.action_cut = None
        self.action_gain = None
        self.action_undo = None
        self.action_redo = None
        self.playback_btn = None
        self.reset_zoom_btn = None
        self.btn_zoom_x = None
        self.btn_zoom_y = None
        self.btn_measure = None
        self.time_label = None
        self.time_edit = None
        self.target_name_label = None
        self.gain_label = None
        self.gain_group = None
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
        self.hub.selection.changed.connect(self._on_selection_changed)
        self.history = AudioHistory(self)
        self.history.changed.connect(self._on_history_changed)
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

        # Level changes the analysis and an export see, but the buffer never
        # gets: the recording stays at the level it was captured at.
        self.gain_map = GainMap()

        # Keeps the analysis of each 10 s of audio, so recording onto the end of
        # a long take, or editing part of it, only re-analyses what it touched.
        self.analysis_cache = ChunkedAudioAnalysis()
        #: An analysis is wanted but the previous one has not stopped yet.
        self._analysis_pending = False

        self.setup_GUI()
        self.setup_audio()

        self.help_window = None
        self.sample_text_window = None

        self.restore_previous_state()

    #################### Lifecycle ####################

    def shutdown(self):
        """Release audio devices and threads before the window closes.

        Each session saves its own layout here rather than on ``aboutToQuit``.
        With one session per window, a connection to the application outlives
        the widget it belongs to, and firing it after the window has gone would
        reach a deleted C++ object.
        """
        if self.is_recording:
            self._teardown_recording()
        if self.is_playing:
            self.stop_playback()

        self.timer.stop()
        self.poll_timer.stop()

        # Nobody will see the result, and cancelling lets the wait below return
        # at the next chunk instead of after the whole recording.
        self._analysis_pending = False
        if self.worker is not None:
            self.worker.cancel()
            self.worker.finished.disconnect(self._on_analysis_thread_finished)

        for worker in (self.play_worker, self.rt_worker, self.worker):
            if worker is not None and worker.isRunning():
                worker.wait(WORKER_SHUTDOWN_MS)

        for window in (self.help_window, self.sample_text_window):
            if window is not None:
                window.close()

        self.save_state_on_exit()

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

        # Icons first: both the menu and the toolbar are built from them.
        self._make_icons(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        self.setupEditActions()
        self.setupMenu()
        self.setupControlButtons()
        self.setupPlots()

        self.timer = QtCore.QTimer()
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._on_frame_tick)

    def setupEditActions(self):
        """The transport and audio-editing commands, as menu actions.

        They live in the Edit menu rather than the toolbar, which leaves the
        toolbar for the view controls. Record and play swap icon and text as
        they toggle, so the menu reads as what pressing it will do next.
        """


        self.action_undo = self._action(
            self.undo_icon, "&Undo", self.handle_undo,
            shortcut=QtGui.QKeySequence.StandardKey.Undo)
        self.action_redo = self._action(
            self.redo_icon, "&Redo", self.handle_redo,
            shortcut=QtGui.QKeySequence.StandardKey.Redo)

        self.action_record = self._action(
            self.record_icon, "&Record\tR", self.handle_start_record_stop)
        self.action_play = self._action(
            self.play_icon, "&Play\tSpace", self.handle_playback)
        self.action_play.setToolTip("Play (Space)")
        self.action_clear = self._action(
            self.clear_icon, "C&lear\tD", self.handle_clear)

        self.action_select = self._action(
            self.select_icon, "&Select Audio", checkable=True,
            on_toggle=lambda c: self.handle_tool_toggle('select', c))
        self.action_select.setToolTip(SELECT_TOOLTIP)
        self.action_silence = self._action(
            self.silence_icon, "Replace with Si&lence", self.handle_silence_selection)
        self.action_cut = self._action(
            self.cut_icon, "C&ut Selection", self.handle_cut_selection)
        self.action_gain = self._action(
            self.gain_icon, "&Gain...", self.handle_set_gain)
        self.action_gain.setToolTip(
            "Gain or attenuation, in dB, applied to the audio before it is "
            "analysed -- the selection if there is one, otherwise all of it")

        for action in (self.action_silence, self.action_cut,
                       self.action_undo, self.action_redo):
            action.setEnabled(False)

        # Shortcuts on menu actions only fire while the menu bar's window has
        # focus unless they are also added to the widget itself.
        self.addActions([self.action_undo, self.action_redo])

    def _action(self, icon, text, on_trigger=None, shortcut=None,
                checkable=False, on_toggle=None):
        action = QtGui.QAction(icon, text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if checkable:
            action.setCheckable(True)
        if on_trigger is not None:
            action.triggered.connect(lambda _checked: on_trigger())
        if on_toggle is not None:
            action.toggled.connect(on_toggle)
        return action

    def _menu_action(self, menu, text, icon_name, on_trigger=None, shortcut=None,
                     checkable=False):
        """A menu entry with an icon that survives a change of colour scheme.

        The icon name is remembered rather than the icon, so ``_make_icons``
        can redraw every one of them in the new text colour.
        """
        action = QtGui.QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if checkable:
            action.setCheckable(True)
        if on_trigger is not None:
            action.triggered.connect(lambda _checked: on_trigger())

        self._icon_actions.append((action, icon_name))
        action.setIcon(qta.icon(icon_name, color=self._icon_colour))

        menu.addAction(action)
        return action

    def _apply_menu_icons(self, colour):
        for action, icon_name in self._icon_actions:
            action.setIcon(qta.icon(icon_name, color=colour))

    def setupMenu(self):
        self.menu_bar = QtWidgets.QMenuBar(self)

        # --- File Menu ---
        file_menu = self.menu_bar.addMenu("&File")
        self._menu_action(file_menu, "&New", 'fa5s.file',
                          self.new_session_signal.emit, "Ctrl+N")
        self._menu_action(file_menu, "&Open", 'fa5s.folder-open',
                          self.browse_file, "Ctrl+O")
        self._menu_action(file_menu, "&Save Annotations", 'fa5s.save',
                          self.save_annotations, "Ctrl+S")
        self._menu_action(file_menu, "Save &Audio As...", 'fa5s.file-audio',
                          self.save_audio, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._menu_action(file_menu, "&Close", 'fa5s.window-close',
                          self.close_session_signal.emit, "Ctrl+W")

        # --- Edit Menu ---
        edit_menu = self.menu_bar.addMenu("&Edit")
        edit_menu.setToolTipsVisible(True)
        edit_menu.addAction(self.action_record)
        edit_menu.addAction(self.action_play)
        edit_menu.addAction(self.action_clear)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_select)
        edit_menu.addAction(self.action_silence)
        edit_menu.addAction(self.action_cut)
        edit_menu.addAction(self.action_gain)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_redo)

        # --- Targets Menu ---
        targets_menu = self.menu_bar.addMenu("&Targets")
        self._menu_action(targets_menu, "Set Targets...", 'fa5s.bullseye',
                          self.open_targets_dialog)
        targets_menu.addSeparator()
        self._menu_action(targets_menu, "Female", 'fa5s.venus',
                          lambda: self.load_targets_from_path("targets/target_female.json"))
        self._menu_action(targets_menu, "Male", 'fa5s.mars',
                          lambda: self.load_targets_from_path("targets/target_male.json"))
        targets_menu.addSeparator()
        self._menu_action(targets_menu, "Import targets...", 'fa5s.file-import',
                          self.import_targets)
        self._menu_action(targets_menu, "Export targets...", 'fa5s.file-export',
                          self.export_targets)

        # --- View Menu ---
        view_menu = self.menu_bar.addMenu("&View")

        self._menu_action(view_menu, "Reset plot spacing", 'fa5s.th-large',
                          self.handle_reset_plots)
        self._menu_action(view_menu, "Series colours...", 'fa5s.palette',
                          self.open_series_colour_dialog)

        view_menu.addSeparator()

        self._menu_action(view_menu, "Sample Texts", 'fa5s.font',
                          self.show_sample_text_window)

        view_menu.addSeparator()

        layouts = self.resource_manager.get_absolute_path
        self._menu_action(view_menu, "Load simple layout", 'mdi6.view-agenda-outline',
                          lambda: self.load_layout_from_file(layouts("layouts/layout_simple.json")))
        self._menu_action(view_menu, "Load medium layout", 'mdi6.view-grid-outline',
                          lambda: self.load_layout_from_file(layouts("layouts/layout_medium.json")))
        self._menu_action(view_menu, "Load advanced layout", 'mdi6.view-dashboard-outline',
                          lambda: self.load_layout_from_file(layouts("layouts/layout_advanced.json")))

        self._menu_action(view_menu, "Load Layout...", 'fa5s.folder-open', self.load_layout)
        self._menu_action(view_menu, "Save Layout...", 'fa5s.save', self.save_layout)
        view_menu.addSeparator()

        self.theme_group = QtGui.QActionGroup(self)
        self.theme_group.setExclusive(True)

        self.action_os_default = self._menu_action(
            view_menu, "Colour scheme: OS Default", 'fa5s.desktop',
            self.set_theme_os_default, checkable=True)
        self.action_light = self._menu_action(
            view_menu, "Colour scheme: Light Mode", 'fa5s.sun',
            self.set_theme_light, checkable=True)
        self.action_dark = self._menu_action(
            view_menu, "Colour scheme: Dark Mode", 'fa5s.moon',
            self.set_theme_dark, checkable=True)

        for action in (self.action_os_default, self.action_light, self.action_dark):
            self.theme_group.addAction(action)
        self.action_os_default.setChecked(True)

        help_menu = self.menu_bar.addMenu("Help")
        self._menu_action(help_menu, "Documentation", 'fa5s.book',
                          self.show_help_window, "F1")

        self.layout.setMenuBar(self.menu_bar)

    def setupControlButtons(self):
        """Build the toolbar as groups that fold into dropdowns when narrow."""
        icon_color = self.palette().color(QtGui.QPalette.ColorRole.WindowText)

        self.toolbar = ResponsiveToolBar()

        # --- Playback: the rest of the transport lives in the Edit menu, but
        # play/pause is reached too often to sit behind one. The button drives
        # the menu's action, so the two never disagree about play versus pause,
        # and its own group keeps it from folding away when the row is narrow.
        self.playback_btn = self._action_button(self.action_play)

        playback = ToolbarGroup("Playback", collapsible=False)
        playback.add(self.playback_btn)
        self.toolbar.add_group(playback)

        # --- View tools
        self.reset_zoom_btn = self._tool_button(
            self.reset_zoom_icon, "Reset zoom", self.handle_reset_zoom)
        self.btn_zoom_x = self._tool_button(
            self.zoom_x_icon, "Zoom X-Axis", checkable=True,
            on_toggle=lambda c: self.handle_tool_toggle('zoom_x', c))
        self.btn_zoom_y = self._tool_button(
            self.zoom_y_icon, "Zoom Y-Axis", checkable=True,
            on_toggle=lambda c: self.handle_tool_toggle('zoom_y', c))
        self.btn_measure = self._tool_button(
            self.measure_icon, "Measure Time/Value", checkable=True,
            on_toggle=lambda c: self.handle_tool_toggle('measure', c))

        tools = ToolbarGroup("View tools", 'fa5s.search-plus')
        tools.add(self.reset_zoom_btn, self.btn_zoom_x, self.btn_zoom_y, self.btn_measure)
        self.toolbar.add_group(tools, collapse_priority=5)

        self.toolbar.add_stretch()

        # --- Time
        self.time_label = QtWidgets.QLabel("Time:")
        self.time_edit = QtWidgets.QLineEdit("00:00:00.000")
        self.time_edit.setFixedWidth(110)
        self.time_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.time_edit.returnPressed.connect(self.handle_time_edited)

        time_group = ToolbarGroup("Time", 'fa5s.clock')
        time_group.add(self.time_label, self.time_edit)
        self.toolbar.add_group(time_group, collapse_priority=4)

        # --- Target
        self.target_name_label = QtWidgets.QLabel(
            f"Target: {self.target_config.config_name}")
        target = ToolbarGroup("Target", 'fa5s.bullseye')
        target.add(self.target_name_label)
        self.toolbar.add_group(target, collapse_priority=3)

        # --- Gain: a level change the plots show but the waveform does not, so
        # it says so here whenever there is one. The whole group hides when
        # there is none -- hiding only the label would leave the row's spacing
        # either side of it and shift everything after it by 10 px. It never
        # folds into a dropdown, where an empty group would still show its
        # button.
        self.gain_label = QtWidgets.QLabel()
        self.gain_group = ToolbarGroup("Gain", collapsible=False)
        self.gain_group.add(self.gain_label)
        self.gain_group.hide()
        self.toolbar.add_group(self.gain_group)

        self.toolbar.add_stretch()

        # --- Rows and columns
        self.add_icon = qta.icon('fa5s.plus', color=icon_color)
        self.remove_icon = qta.icon('fa5s.minus', color=icon_color)

        self.row_label = QtWidgets.QLabel("Rows:")
        self.add_row_btn = self._tool_button(self.add_icon, "Add row", self.add_plot_row)
        self.remove_row_btn = self._tool_button(
            self.remove_icon, "Remove row", self.remove_plot_row)
        self.col_label = QtWidgets.QLabel("Columns:")
        self.add_col_btn = self._tool_button(self.add_icon, "Add column", self.add_plot_column)
        self.remove_col_btn = self._tool_button(
            self.remove_icon, "Remove column", self.remove_plot_column)

        grid = ToolbarGroup("Rows and columns", 'fa5s.th-large')
        grid.add(self.row_label, self.add_row_btn, self.remove_row_btn)
        grid.add_spacing(10)
        grid.add(self.col_label, self.add_col_btn, self.remove_col_btn)
        self.toolbar.add_group(grid, collapse_priority=2)

        # --- Global point size
        self.size_label = QtWidgets.QLabel("Global point size:")
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(1)
        self.size_slider.setMaximum(5)
        self.size_slider.setValue(defaultSize)
        self.size_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(1)
        self.size_slider.setFixedWidth(120)
        self.size_slider.valueChanged.connect(self.handle_symbol_size_change)

        size = ToolbarGroup("Point size", 'fa5s.braille')
        size.add(self.size_label, self.size_slider)
        self.toolbar.add_group(size, collapse_priority=1)

        self.toolbar.apply_icons(icon_color)
        self.layout.addWidget(self.toolbar)

    def _make_icons(self, colour):
        self._icon_colour = colour
        self._apply_menu_icons(colour)

        self.record_icon = qta.icon('fa5s.microphone', color=colour)
        self.stop_icon = qta.icon('fa5s.stop', color=colour)
        self.play_icon = qta.icon('fa5s.play', color=colour)
        self.pause_icon = qta.icon('fa5s.pause', color=colour)
        self.save_icon = qta.icon('fa5s.save', color=colour)
        self.clear_icon = qta.icon('fa5s.trash', color=colour)
        self.reset_zoom_icon = qta.icon('fa6s.maximize', color=colour)
        self.zoom_x_icon = qta.icon('fa5s.arrows-alt-h', color=colour)
        self.zoom_y_icon = qta.icon('fa5s.arrows-alt-v', color=colour)
        self.measure_icon = qta.icon('fa5s.ruler-combined', color=colour)
        self.select_icon = qta.icon(SELECT_ICON, color=colour)
        self.silence_icon = qta.icon(SILENCE_ICON, color=colour)
        self.cut_icon = qta.icon(CUT_ICON, color=colour)
        self.gain_icon = qta.icon(GAIN_ICON, color=colour)
        self.undo_icon = qta.icon(UNDO_ICON, color=colour)
        self.redo_icon = qta.icon(REDO_ICON, color=colour)

    @staticmethod
    def _tool_button(icon, tooltip, on_click=None, checkable=False, on_toggle=None):
        button = QtWidgets.QPushButton()
        button.setFixedSize(40, 40)
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(20, 20))
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        if on_click is not None:
            button.clicked.connect(on_click)
        if on_toggle is not None:
            button.toggled.connect(on_toggle)
        return button

    def _action_button(self, action):
        """A toolbar button showing a menu action, and following it as it changes.

        The action stays the single source of truth for the icon and the
        tooltip, so play and pause cannot get out of step between the two.
        """
        button = self._tool_button(action.icon(), action.toolTip(), action.trigger)

        def follow():
            button.setIcon(action.icon())
            button.setToolTip(action.toolTip())
            button.setEnabled(action.isEnabled())

        action.changed.connect(follow)
        return button

    def _tool_toggles(self):
        """The mutually exclusive drag tools -- toolbar buttons and menu actions."""
        return {'zoom_x': self.btn_zoom_x, 'zoom_y': self.btn_zoom_y,
                'measure': self.btn_measure, 'select': self.action_select}

    def handle_tool_toggle(self, tool, checked):
        """The drag tools are mutually exclusive; only one can own the mouse."""
        if checked:
            for name, toggle in self._tool_toggles().items():
                if name != tool:
                    toggle.blockSignals(True)
                    toggle.setChecked(False)
                    toggle.blockSignals(False)
            self.active_tool_mode = tool
        else:
            if self.active_tool_mode == tool:
                self.active_tool_mode = None
            # Leaving select mode drops the selection, so an edit can never be
            # applied to a range the user can no longer see.
            if tool == 'select':
                self.hub.selection.clear()

        if hasattr(self, 'plot_cells'):
            for cell in self.plot_cells:
                cell.set_tool_mode(self.active_tool_mode)

    def setupPlots(self):
        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        # Spare vertical space belongs to the plots, not the toolbar.
        self.layout.addWidget(self.plot_splitter, stretch=1)

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
        cell.audio_move_requested.connect(self.handle_audio_move)

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
            # A transposed plot has time on Y, so the group drives that axis.
            self.sync_group.register(cell.view_box, cell.time_axis)
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

            self._make_icons(icon_color)
            self.add_icon = qta.icon('fa5s.plus', color=icon_color)
            self.remove_icon = qta.icon('fa5s.minus', color=icon_color)

            if hasattr(self, 'toolbar'):
                self.toolbar.apply_icons(icon_color)
            for button, icon in ((getattr(self, 'add_row_btn', None), self.add_icon),
                                 (getattr(self, 'add_col_btn', None), self.add_icon),
                                 (getattr(self, 'remove_row_btn', None), self.remove_icon),
                                 (getattr(self, 'remove_col_btn', None), self.remove_icon)):
                if button is not None:
                    button.setIcon(icon)

            if self.action_record is not None:
                self.action_record.setIcon(
                    self.stop_icon if self.is_recording else self.record_icon)
                self.action_play.setIcon(
                    self.pause_icon if self.is_playing else self.play_icon)
                self.action_clear.setIcon(self.clear_icon)
                self.action_select.setIcon(self.select_icon)
                self.action_silence.setIcon(self.silence_icon)
                self.action_cut.setIcon(self.cut_icon)
                self.action_gain.setIcon(self.gain_icon)
                self.action_undo.setIcon(self.undo_icon)
                self.action_redo.setIcon(self.redo_icon)

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
            # A different recording is a different history, and none of the
            # cached chunks describe it.
            self.history.reset()
            self.analysis_cache.reset()
            self.hub.selection.clear()
            # The gains described stretches of the recording being replaced.
            self.gain_map.clear()
            self._update_gain_label()
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
                # Manually write raw PCM data to disk, at the level the
                # analysis saw it: the export is what the numbers were made
                # from, gains and all.
                with wave.open(save_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sampling_rate)
                    wf.writeframes(self._gained_audio())

                self.current_audio_file = save_path
                self.file_loaded_signal.emit(save_path)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error",
                                               f"An error occurred while saving the audio:\n{str(e)}")

    #################### File analysis ####################

    def select_analysis_from_memory(self):
        """Ask for an analysis of the current buffer.

        Only one runs at a time: the chunk cache is the worker's to write while
        it runs, and a second worker on the same cache would fight it. A request
        made while one is in flight cancels that one and takes its place, which
        also stops a burst of edits queueing up analyses nobody will look at.
        """
        self._analysis_pending = True
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            return
        self._start_analysis()

    def _start_analysis(self):
        self._analysis_pending = False
        self._show_analysis_dialog()

        # Passes memory bytes to worker instead of disk file path. The gains go
        # on before it leaves: the chunk cache keys on the audio it is handed,
        # so a gain over one stretch re-analyses that stretch and no other.
        self.worker = AnalysisWorker(
            self.audioFeatureExtractor,
            audio_bytes=self._gained_audio(),
            sample_rate=self.sampling_rate,
            cache=self.analysis_cache
        )
        self.worker.result_ready.connect(self.on_analysis_finished)
        self.worker.error_occurred.connect(self.on_analysis_error)
        self.worker.finished.connect(self._on_analysis_thread_finished)
        self.worker.start()

    def _show_analysis_dialog(self):
        """Show the wait dialog, unless one is already up from a cancelled run."""
        if self.loading_dialog is not None and self.loading_dialog.isVisible():
            return
        self.loading_dialog = QtWidgets.QProgressDialog("Analyzing audio...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Please Wait")
        self.loading_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.show()

    def _on_analysis_thread_finished(self):
        """Retire the finished worker and run whatever was waiting for it."""
        finished, self.worker = self.worker, None
        if finished is not None:
            # The thread is still emitting; let the event loop drop it.
            finished.deleteLater()

        if self._analysis_pending:
            QtCore.QTimer.singleShot(0, self._start_analysis)
            return

        if self.loading_dialog is not None:
            self.loading_dialog.close()

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

        self.action_record.setIcon(self.stop_icon)
        self.action_record.setText("Stop &Recording\tR")

        while not self.audio_queue.empty():
            self.audio_queue.get()

        # Snapshot before capture starts: undoing a recording puts the
        # buffer back the way it was before the microphone opened.
        self._capture("Recording")

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
        self._teardown_recording()

        self.current_playback_time = 0
        self.update_playhead()

        # Audio is now kept entirely in memory buffer, trigger final batch analysis
        self.select_analysis_from_memory()

    def _teardown_recording(self):
        """Stop capture and live analysis, without starting a re-analysis.

        Separate from ``record_stop`` so that closing the window can release the
        microphone without kicking off a batch analysis nobody will see.
        """
        self.action_record.setIcon(self.record_icon)
        self.action_record.setText("&Record\tR")

        self.poll_timer.stop()
        self.read_audio_chunk()

        self.audio_source.stop()
        self.audio_buffer.close()
        self.timer.stop()

        if self.rt_worker is not None:
            self.rt_worker.stop()
            self.rt_worker.wait()

        self.hub.end_recording()

        # Clear the recording flag before anything moves the playhead, or
        # update_playhead reads the position straight back off the (now closed)
        # audio buffer.
        self.is_recording = False

    def read_audio_chunk(self):
        current_pos = self.audio_buffer.pos()
        if current_pos > self.last_read_pos:
            chunk_start = self.last_read_pos
            new_bytes = self.audio_data.mid(chunk_start, current_pos - chunk_start).data()
            self.last_read_pos = current_pos

            if new_bytes:
                # The live analysis is analysis too, so the chunk is gained on
                # its way past -- at the position it occupies in the recording,
                # since a gain may cover only part of it.
                new_bytes, _ = self.gain_map.apply(
                    new_bytes, self.sampling_rate,
                    offset_seconds=chunk_start / float(AudioEdit.BYTES_PER_SAMPLE
                                                       * self.sampling_rate))
                self.audio_queue.put(new_bytes)

    def append_live_data(self, latest_point: FeatureSnapshot):
        """Hand one live analysis frame to the hub.

        Plots are not touched here: the frame timer picks the new data up. The
        old code appended the same snapshot once per visible curve, so a feature
        shown in two plots was recorded twice.
        """
        latest_point.time += self.recording_start_offset or 0.0
        self.hub.append_snapshot(latest_point)

    #################### Audio editing ####################

    def _on_selection_changed(self):
        has_audio = not self.audio_data.isEmpty()
        editable = self.hub.selection.active and has_audio
        self.action_silence.setEnabled(editable)
        self.action_cut.setEnabled(editable)

    def _on_history_changed(self):
        self.action_undo.setEnabled(self.history.can_undo)
        self.action_redo.setEnabled(self.history.can_redo)
        # The label names what will be undone, so the menu says what it will do.
        self.action_undo.setText(
            f"&Undo {self.history.undo_label}" if self.history.can_undo else "&Undo")
        self.action_redo.setText(
            f"&Redo {self.history.redo_label}" if self.history.can_redo else "&Redo")

    def _capture(self, label):
        """Remember the current audio so this action can be undone.

        The gains go into the entry with it: a cut or a move takes them along,
        so putting the audio back has to put them back as they were too.
        """
        self.history.capture(self.audio_data, self.current_audio_file, label,
                             gains=self.gain_map.copy())

    def handle_silence_selection(self):
        """Replace the selected audio with silence, keeping the timeline length."""
        selection = self.hub.selection
        if not selection.active:
            return

        self._capture("Silence")
        if AudioEdit.silence(self.audio_data, selection.start, selection.end,
                             self.sampling_rate):
            self._after_audio_edit()

    def handle_cut_selection(self):
        """Cut the selected audio out, closing the gap."""
        selection = self.hub.selection
        if not selection.active:
            return

        self._capture("Cut")
        if AudioEdit.cut(self.audio_data, selection.start, selection.end,
                         self.sampling_rate):
            # Everything after the cut has shifted; the old range no longer
            # describes the same audio, so the selection goes with it. The
            # gains describe stretches of audio too, and follow the same way.
            self.gain_map.cut(selection.start, selection.end)
            selection.clear()
            self._after_audio_edit()

    def handle_audio_move(self, delta_seconds: float):
        """Move the selected audio, overwriting whatever it lands on."""
        selection = self.hub.selection
        if not selection.active or not delta_seconds:
            return

        self._capture("Move")
        if AudioEdit.move(self.audio_data, selection.start, selection.end,
                          delta_seconds, self.sampling_rate):
            self.gain_map.move(selection.start, selection.end, delta_seconds)
            selection.shift(delta_seconds)
            self._after_audio_edit()
        else:
            # Nothing moved; put the band back where the audio still is.
            self.hub.selection.changed.emit()

    #################### Gain ####################

    def handle_set_gain(self):
        """Set the gain, in dB, applied to the audio before it is analysed."""
        if self.audio_data.isEmpty():
            QtWidgets.QMessageBox.warning(self, "No Audio",
                                          "There is no audio to apply a gain to.")
            return

        selection = self.hub.selection
        if selection.active:
            start, end = selection.start, selection.end
            scope = (f"the selection ({self.format_time(start)} to "
                     f"{self.format_time(end)})")
        else:
            # To infinity rather than to the end of the buffer, so that audio
            # recorded onto the end later is covered by the same gain.
            start, end = 0.0, INFINITY
            scope = "the whole recording"

        current = self.gain_map.uniform_gain(start, end)
        prompt = f"Gain applied to {scope} before analysis (dB):"
        if current is None:
            prompt += ("\n\nThis range carries more than one gain; applying "
                       "replaces all of them.")

        value, accepted = QtWidgets.QInputDialog.getDouble(
            self, "Gain", prompt, current or 0.0,
            -GAIN_LIMIT_DB, GAIN_LIMIT_DB, 1)

        if accepted:
            self.apply_gain(start, end, value)

    def apply_gain(self, start, end, db, warn_on_clipping=True):
        """Put ``db`` in force over a range, and re-analyse what it changed.

        Separate from the dialog so that asking for a figure and acting on one
        stay apart -- the screenshot tool and the tests set a gain without a
        dialog to answer. Returns False when the gain was already in force.
        """
        if not self.gain_map.set_gain(start, end, db):
            return False

        # A stream already playing was handed the old level; the next play
        # picks the new one up, as it does after any other edit.
        if self.is_playing:
            self.stop_playback()

        self._update_gain_label()

        if warn_on_clipping and self.gain_map.clips(self.audio_data.data(),
                                                    self.sampling_rate):
            QtWidgets.QMessageBox.information(
                self, "Clipping",
                "This gain drives part of the audio past full scale. Those "
                "samples are clamped, so the analysis sees a flattened "
                "waveform where it happens.")

        if not self.audio_data.isEmpty():
            self.select_analysis_from_memory()
        return True

    def _update_gain_label(self):
        """Name the gains in force in the toolbar, or take the readout away."""
        if self.gain_label is None:
            return

        segments = self.gain_map.segments()
        if not segments:
            self.gain_label.setToolTip("")
            self.gain_group.hide()
            self.toolbar.refit()
            return

        if len(segments) == 1 and segments[0].covers_everything:
            self.gain_label.setText(f"Gain: {segments[0].db:+.1f} dB")
        else:
            self.gain_label.setText(f"Gain: {len(segments)} ranges")

        self.gain_label.setToolTip("\n".join(
            f"{self.format_time(segment.start)} to "
            f"{'end' if segment.end == INFINITY else self.format_time(segment.end)}"
            f": {segment.db:+.1f} dB"
            for segment in segments))
        self.gain_group.show()
        # The row has one more thing in it than it had; nothing else would
        # notice, since the toolbar only re-fits when it is resized.
        self.toolbar.refit()

    def _gained_audio(self):
        """The buffer as the analysis, playback and an export get it.

        The gains are applied to a copy each time. The buffer itself keeps the
        level it was captured at, and so does the file it was loaded from --
        that file is the only thing a gain never reaches.
        """
        gained, _ = self.gain_map.apply(self.audio_data.data(), self.sampling_rate)
        return gained

    #################### Undo ####################

    def handle_undo(self):
        self._step_history(self.history.undo)

    def handle_redo(self):
        self._step_history(self.history.redo)

    def _step_history(self, step):
        if self.is_recording:
            self.record_stop()

        entry = step(self.audio_data, self.current_audio_file, self.gain_map.copy())
        if entry is None:
            return

        self.audio_data.clear()
        self.audio_data.append(entry.audio)
        self.current_audio_file = entry.audio_file
        if entry.gains is not None:
            self.gain_map = entry.gains
        self.hub.selection.clear()
        self._after_audio_edit()

    def _after_audio_edit(self):
        """Re-analyse, the same way finishing a recording does."""
        if self.is_playing:
            self.stop_playback()
        self._on_selection_changed()
        self._update_gain_label()

        if self.audio_data.isEmpty():
            self.hub.clear()
            self.update_plots()
            self.handle_reset_zoom()
            return

        self.select_analysis_from_memory()

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

        if not self.audio_data.isEmpty():
            self._capture("Clear")

        self.current_audio_file = None
        self.audio_data.clear()
        self.analysis_cache.reset()
        self.gain_map.clear()
        self._update_gain_label()
        self.hub.clear()

        if hasattr(self, 'recording_start_offset'):
            self.recording_start_offset = 0

        self.hub.selection.clear()
        self.clear_annotations()
        self.update_plots()
        self.handle_reset_zoom()
        logging.debug("All data cleared.")

    def stop_playback(self):
        self.is_playing = False
        self.action_play.setIcon(self.play_icon)
        self.action_play.setText("&Play\tSpace")
        self.action_play.setToolTip("Play (Space)")

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
            samples=self._gained_audio(),
            seek_frame=seek_frame,
            sample_rate=current_sr
        )
        self.play_worker.playback_finished.connect(self.stop_playback)
        self.play_worker.start()

        self.playback_start_time = time.time() - target_time
        self.is_playing = True
        self.action_play.setIcon(self.pause_icon)
        self.action_play.setText("&Pause\tSpace")
        self.action_play.setToolTip("Pause (Space)")
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

    def open_series_colour_dialog(self):
        dialog = SeriesColourDialog(parent=self)
        # Live preview: repaint on every pick, and again if the user cancels.
        dialog.colours_changed.connect(self.series_colours_changed.emit)
        dialog.exec()

    def refresh_series_colours(self):
        for cell in self.plot_cells:
            cell.refresh_colours()

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
            self.target_name_label.setText(f"Target: {new_config.config_name}")

        for cell in self.plot_cells:
            cell.update_targets(new_config)

        self.update_plots()

    #################### Mouse & keyboard actions ####################

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key.Key_Space:
            # Space is the stop key while recording as well: whatever is
            # running, space is what ends it.
            if self.is_recording:
                self.record_stop()
            elif self.is_playing:
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

            settings.setValue("series_colours", json.dumps(Registry.colour_overrides()))
            settings.setValue("frequency_markers", json.dumps(MARKERS.to_list()))

        except Exception as e:
            logging.error(f"Failed to auto-save application state: {e}")

    def restore_previous_state(self):
        settings = QtCore.QSettings("AudioAnalyzer", "LiveMultiPlotWidget")

        colours_str = settings.value("series_colours", "")
        if colours_str:
            try:
                Registry.apply_colour_overrides(json.loads(colours_str))
            except Exception as e:
                logging.error(f"Failed to restore series colours: {e}")

        markers_str = settings.value("frequency_markers", "")
        if markers_str:
            try:
                MARKERS.restore(json.loads(markers_str))
            except Exception as e:
                logging.error(f"Failed to restore frequency markers: {e}")

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