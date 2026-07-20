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
from PlotsSpec import PlotsSpec, defaultSize
from plot.FrequencyPlotController import FrequencyPlotController
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor, TargetConfig
from signal_processing.AudioFeatures import AudioFeatures, FeatureSnapshot
from ui.AnnotationMarker import AnnotationMarker
from ui.HelpWindow import HelpWindow
from ui.TargetConfigDialog import TargetConfigDialog
from ui.workers.AnalysisWorker import AnalysisWorker
from ui.workers.PlaybackWorker import PlaybackWorker
from ui.workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker
from ui.plot.PlotController import PlotController
from ui.plot.InstantaneousPlotController import InstantaneousPlotController

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
        self.record_stop_btn = None
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
        self.analysedAudioFeatures = AudioFeatures()

        self.annotations = []
        self.plots = {}

        self.is_recording = False
        self.is_playing = False
        self.playback_start_time = 0.0

        self.current_playback_time = 0

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

        self.menu_toggle_actions = {
            'plots': {}
        }

        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.save_state_on_exit)

        self.restore_previous_state()

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
        self.timer.timeout.connect(self.update_plots)

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

        self.record_stop_btn = QtWidgets.QPushButton()
        self.record_stop_btn.setFixedSize(40, 40)
        self.record_stop_btn.setIcon(self.record_icon)
        self.record_stop_btn.setIconSize(QtCore.QSize(20, 20))
        self.record_stop_btn.setToolTip("Record")
        self.record_stop_btn.clicked.connect(self.handle_record_stop)
        top_buttons_layout.addWidget(self.record_stop_btn)

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

        available_plots = list(PlotsSpec.keys())
        p1 = available_plots[0] if len(available_plots) > 0 else None
        p2 = available_plots[1] if len(available_plots) > 1 else p1
        p3 = available_plots[2] if len(available_plots) > 2 else p1
        p4 = available_plots[3] if len(available_plots) > 3 else p1

        # Populate the initial 2x2 grid
        self._add_specific_row([p1, p2])
        self._add_specific_row([p3, p4])

    def _create_column(self):
        col = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.plot_splitter.addWidget(col)
        self.columns.append(col)
        return col

    def _add_specific_row(self, plot_names):
        for i, col in enumerate(self.columns):
            name = plot_names[i] if i < len(plot_names) else plot_names[-1]
            controller = self.create_plot_cell(name)
            self.plot_cells.append(controller)
            col.addWidget(controller.container)
        self.sync_all_x_axes()

    def create_plot_cell(self, plot_name):
        if not plot_name: return None

        initial_size = self.size_slider.value() if hasattr(self, 'size_slider') else defaultSize

        plot = PlotsSpec.get(plot_name)
        is_freq_analysis = plot.get('is_frequency_analysis', False)

        is_inst = plot.get('is_instantaneous', False)
        if is_freq_analysis:
            controller_class = FrequencyPlotController
        elif is_inst:
            controller_class = InstantaneousPlotController
        else:
            controller_class = PlotController

        controller = controller_class(
            plot_name=plot_name,
            all_specs=PlotsSpec,
            click_callback=self.on_mouse_clicked,
            change_plot_callback=self.handle_plot_selection,
            initial_size=initial_size
        )

        # controller = PlotController(
        #     plot_name=plot_name,
        #     all_specs=spec,
        #     click_callback=self.on_mouse_clicked,
        #     change_plot_callback=self.handle_plot_selection,
        #     initial_size=initial_size
        # )
        if hasattr(self, 'active_tool_mode'):
            controller.set_tool_mode(self.active_tool_mode)
        return controller

    def add_plot_row(self):
        available_plots = list(PlotsSpec.keys())
        default_plot = available_plots[0] if available_plots else None

        for col in self.columns:
            controller = self.create_plot_cell(default_plot)
            self.plot_cells.append(controller)
            col.addWidget(controller.container)

        self.sync_all_x_axes()
        self.update_plots()

        if hasattr(self, 'size_slider'):
            self.handle_symbol_size_change(self.size_slider.value())

    def remove_plot_row(self):
        if len(self.columns) == 0 or self.columns[0].count() <= 1:
            return

        widgets_to_remove = []
        for col in self.columns:
            last_widget = col.widget(col.count() - 1)
            widgets_to_remove.append(last_widget)
            last_widget.deleteLater()

        self.plot_cells = [c for c in self.plot_cells if c.container not in widgets_to_remove]

    def add_plot_column(self):
        num_rows = self.columns[0].count() if self.columns else 1
        available_plots = list(PlotsSpec.keys())
        default_plot = available_plots[0] if available_plots else None

        new_col = self._create_column()

        for _ in range(num_rows):
            controller = self.create_plot_cell(default_plot)
            self.plot_cells.append(controller)
            new_col.addWidget(controller.container)

        self.sync_all_x_axes()
        self.update_plots()

        if hasattr(self, 'size_slider'):
            self.handle_symbol_size_change(self.size_slider.value())

    def remove_plot_column(self):
        if len(self.columns) <= 1:
            return

        col_to_remove = self.columns.pop()

        widgets_to_remove = [col_to_remove.widget(i) for i in range(col_to_remove.count())]
        self.plot_cells = [c for c in self.plot_cells if c.container not in widgets_to_remove]

        col_to_remove.deleteLater()

    def handle_plot_selection(self, old_controller, new_plot_name):
        if old_controller.plot_name == new_plot_name:
            return

        current_size = old_controller.local_slider.value()
        new_controller = PlotController(
            plot_name=new_plot_name,
            all_specs=PlotsSpec,
            click_callback=self.on_mouse_clicked,
            change_plot_callback=self.handle_plot_selection,
            initial_size=current_size
        )
        if hasattr(self, 'active_tool_mode'):
            new_controller.set_tool_mode(self.active_tool_mode)

        splitter = old_controller.container.parentWidget()
        if isinstance(splitter, QtWidgets.QSplitter):
            index = splitter.indexOf(old_controller.container)
            splitter.replaceWidget(index, new_controller.container)
        else:
            parent_layout = old_controller.container.parentWidget().layout()
            if parent_layout:
                parent_layout.replaceWidget(old_controller.container, new_controller.container)

        new_controller.container.show()
        self.plot_cells[self.plot_cells.index(old_controller)] = new_controller
        old_controller.container.deleteLater()
        old_controller.deleteLater()

        if new_plot_name in self.menu_toggle_actions['plots']:
            self.menu_toggle_actions['plots'][new_plot_name].setChecked(True)

        new_controller.update_target_bands(self.audioFeatureExtractor.target_config)
        self.sync_all_x_axes()
        self.update_plots()
        new_controller.set_symbol_size(current_size)

    def sync_all_x_axes(self):
        master_widget = None

        for cell in self.plot_cells:
            # Check the cell's spec to see if it contains a frequency curve
            is_freq_plot = any(
                curve.get('is_frequency_analysis', False)
                for curve in cell.spec.get('curves', {}).values()
            )

            is_inst_plot = cell.spec.get('is_instantaneous', False)

            if is_freq_plot or is_inst_plot:
                # Explicitly clear any existing link so it doesn't accidentally
                # pan/zoom when you scrub the time plots
                cell.widget.setXLink(None)
            else:
                # First time-based plot becomes the master anchor
                if master_widget is None:
                    master_widget = cell.widget
                    master_widget.setXLink(None)  # Clear stale links on the master
                else:
                    # Link all subsequent time plots to the master
                    cell.widget.setXLink(master_widget)

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
                if "Record" in self.record_stop_btn.toolTip():
                    self.record_stop_btn.setIcon(self.record_icon)
                else:
                    self.record_stop_btn.setIcon(self.stop_icon)

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
                plot_widget = None
                target_plot_key = None

                for controller in self.plot_cells:
                    plot_title = controller.PlotsSpec.get('title', '')
                    if annotation['plot'] == controller.plot_name or annotation['plot'] == plot_title:
                        plot_widget = controller.widget
                        target_plot_key = controller.plot_name
                        break

                if plot_widget:
                    annotation['plot'] = target_plot_key
                    marker = AnnotationMarker(
                        annotation['time'],
                        annotation['y'],
                        annotation['text'],
                        target_plot_key,
                        plot_widget,
                        self
                    )
                    plot_widget.addItem(marker)
                    annotation['marker'] = marker
                    self.annotations.append(annotation)

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
        self.analysedAudioFeatures = results
        self.current_playback_time = 0
        self.update_plots()
        self.handle_reset_zoom()

    def on_analysis_error(self, error_msg):
        QtWidgets.QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis:\n{error_msg}")

    #################### Record, playback ####################

    def handle_record_stop(self):
        if self.is_playing:
            self.stop_playback()

        self.is_recording = not self.is_recording

        if self.is_recording:
            self.record_start()
        else:
            self.record_stop()

    def record_start(self):
        self.record_stop_btn.setIcon(self.stop_icon)
        self.record_stop_btn.setToolTip("Stop Recording")

        while not self.audio_queue.empty():
            self.audio_queue.get()

        self.recording_start_offset = self.current_playback_time

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
        self.timer.start()

    def record_stop(self):
        self.record_stop_btn.setIcon(self.record_icon)
        self.record_stop_btn.setToolTip("Record")

        self.poll_timer.stop()
        self.read_audio_chunk()

        self.audio_source.stop()
        self.audio_buffer.close()
        self.timer.stop()

        if hasattr(self, 'rt_worker'):
            self.rt_worker.stop()
            self.rt_worker.wait()

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
        if hasattr(latest_point, 'time'):
            latest_point.time += self.recording_start_offset
        elif hasattr(latest_point, 'timestamp'):
            latest_point.timestamp += self.recording_start_offset

        for controller in self.plot_cells:
            for curve_name in controller.curves.keys():
                controller.append_curve_point(
                    curve_name=curve_name,
                    snapshot=latest_point,
                    audio_features_ctx=self.analysedAudioFeatures
                )

        self.update_playhead()

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
            self.is_recording = False

        self.current_audio_file = None
        self.analysedAudioFeatures = AudioFeatures()
        self.audio_data.clear()
        self.current_playback_time = 0

        if hasattr(self, 'recording_start_offset'):
            self.recording_start_offset = 0

        self.clear_annotations()

        if hasattr(self, 'plot_cells'):
            for controller in self.plot_cells:
                for curve_name in controller.curves.keys():
                    controller.set_curve_data(curve_name, [], [])
                controller.set_playhead_value(0)

        self.update_plots()
        self.handle_reset_zoom()
        logging.debug("All data cleared.")

    def stop_playback(self):
        self.is_playing = False
        self.playback_btn.setIcon(self.play_icon)

        if hasattr(self, 'play_worker'):
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

    def update_playhead(self):
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time if self.is_playing else 0
            if self.current_playback_time > self.analysedAudioFeatures.length_seconds:
                self.stop_playback()
                self.current_playback_time = 0

        elif self.is_recording:
            self.current_playback_time = self.audio_buffer.pos() / (2 * self.sampling_rate)
            total_duration = self.audio_data.size() / (2 * self.sampling_rate)
            self.analysedAudioFeatures.length_seconds = max(self.analysedAudioFeatures.length_seconds, total_duration)

        if hasattr(self, 'time_edit') and not self.time_edit.hasFocus():
            self.time_edit.setText(self.format_time(self.current_playback_time))

        for controller in self.plot_cells:
            controller.set_playhead_value(self.current_playback_time)

        # Find the first standard time-based plot to act as the viewport driver
        time_plot_cell = next(
            (c for c in self.plot_cells
             if not c.spec.get('is_instantaneous') and not any(
                cv.get('is_frequency_analysis') for cv in c.spec.get('curves', {}).values())),
            None
        )

        if time_plot_cell:
            if self.is_recording:
                view_window_seconds = 10.0

                # Add a 1-second visual buffer so the playhead isn't clipped by the right border
                future_padding = 1.0

                min_x = max(0.0, self.current_playback_time - view_window_seconds + future_padding)
                max_x = max(view_window_seconds, self.current_playback_time + future_padding)

                time_plot_cell.widget.setXRange(min_x, max_x, padding=0)

            elif self.is_playing:
                view_box = time_plot_cell.widget.getViewBox()
                x_range = view_box.viewRange()[0]
                min_x, max_x = x_range[0], x_range[1]
                view_width = max_x - min_x

                total_length = getattr(self.analysedAudioFeatures, 'length_seconds', 0.0) or 0.0

                if view_width < (total_length - 0.01):
                    future_buffer = 0.50 * view_width
                    if self.current_playback_time > (max_x - future_buffer):
                        new_max_x = self.current_playback_time + future_buffer
                        new_min_x = new_max_x - view_width
                        time_plot_cell.widget.setXRange(new_min_x, new_max_x, padding=0)
                    elif self.current_playback_time < min_x:
                        new_min_x = max(0.0, self.current_playback_time - future_buffer)
                        new_max_x = new_min_x + view_width
                        time_plot_cell.widget.setXRange(new_min_x, new_max_x, padding=0)

    #################### Misc plot stuff ####################

    def handle_symbol_size_change(self, value):
        if not hasattr(self, 'plot_cells'): return

        for controller in self.plot_cells:
            if hasattr(controller, 'local_slider'):
                controller.local_slider.blockSignals(True)
                controller.local_slider.setValue(value)
                controller.local_slider.blockSignals(False)
            controller.set_symbol_size(value)

    def handle_reset_zoom(self):
        if hasattr(self, 'btn_zoom_x'):
            self.btn_zoom_x.setChecked(False)
            self.btn_zoom_y.setChecked(False)
            self.btn_measure.setChecked(False)
            self.active_tool_mode = None

        if not hasattr(self, 'plot_cells'): return
        for controller in self.plot_cells:
            controller.set_tool_mode(None)
            controller.reset_zoom()

    def handle_toggle_plot(self, plot_key: str, checked: bool):
        for controller in self.plot_cells:
            if controller.plot_name == plot_key:
                controller.set_plot_visible(checked)

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

        for plot_key, plot_spec in PlotsSpec.items():
            is_visible = not plot_spec.get('hidden', False)
            self.handle_toggle_plot(plot_key, is_visible)
            if plot_key in self.menu_toggle_actions['plots']:
                self.menu_toggle_actions['plots'][plot_key].setChecked(is_visible)

        if hasattr(self, 'plot_cells'):
            for controller in self.plot_cells:
                for cb in getattr(controller, 'toggles', []):
                    cb.setChecked(True)

    def update_plots(self):
        for controller in self.plot_cells:

            # --- Handle Instantaneous Plots ---
            if controller.spec.get('is_instantaneous'):
                for curve_name in controller.curves.keys():
                    controller.set_curve_data(
                        curve_name=curve_name,
                        x=[], y=[],  # The controller pulls x/y directly from audio_features_ctx
                        data_container=None,
                        audio_features_ctx=self.analysedAudioFeatures
                    )
                continue

            # --- Handle Standard Time-Series & Frequency Plots ---
            for curve_name, curve_config in controller.curves.items():
                result_key = curve_config.get('analysisResult')

                # Skip if there's no analysis result mapped to this curve
                if not result_key:
                    continue

                if not hasattr(self.analysedAudioFeatures, result_key):
                    logging.error(f"Unknown curve: {result_key}")
                    continue

                data = getattr(self.analysedAudioFeatures, result_key)
                if not hasattr(data, 'x') or not hasattr(data, 'y'):
                    logging.error(f"Missing x or y data for {curve_name}")
                    continue

                is_spectrogram = curve_config.get('is_spectrogram', False)
                is_frequency_analysis = controller.spec.get('is_frequency_analysis', False)
                is_instantaneous = controller.spec.get('is_instantaneous', False)

                if not is_spectrogram and not is_frequency_analysis and not is_instantaneous and len(data.x) != len(data.y):
                    logging.error(f"Mismatch in dimensions for curve {curve_name}")
                    continue

                controller.set_curve_data(
                    curve_name=curve_name,
                    x=data.get_x_without_NaN(),
                    y=data.get_y_without_NaN(),
                    data_container=data,
                    audio_features_ctx=self.analysedAudioFeatures
                )

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

        for controller in self.plot_cells:
            for band in controller.target_bands.values():
                band['enabled'] = True
            controller.update_target_bands(new_config)

        self.update_plots()

    #################### Mouse & keyboard actions ####################

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key.Key_Space:
            if self.is_recording:
                self.is_recording = False
                self.record_stop()
            elif self.is_playing:
                self.stop_playback()
            else:
                if not self.audio_data.isEmpty():
                    self.seek_and_play()
            event.accept()

        elif key == QtCore.Qt.Key.Key_R:
            if self.is_recording:
                self.is_recording = False
                self.record_stop()
            else:
                if self.is_playing:
                    self.stop_playback()
                self.is_recording = True
                self.record_start()
            event.accept()

        elif key == QtCore.Qt.Key.Key_D:
            self.handle_clear()
            event.accept()

        else:
            super().keyPressEvent(event)

    def on_mouse_clicked(self, event, plot_widget, plot_name):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.scenePos()
            mouse_point = plot_widget.plotItem.vb.mapSceneToView(pos)

            target_time = mouse_point.x()
            if target_time < 0: target_time = 0
            target_y = mouse_point.y()

            HIT_RADIUS_PIXELS = 15
            clicked_marker = None

            for ann in self.annotations:
                if ann['plot'] == plot_name:
                    marker = ann['marker']
                    marker_pt = QtCore.QPointF(marker.x_val, marker.y_val)
                    scene_pt = plot_widget.plotItem.vb.mapViewToScene(marker_pt)

                    if scene_pt:
                        dist = ((scene_pt.x() - pos.x()) ** 2 + (scene_pt.y() - pos.y()) ** 2) ** 0.5
                        if dist <= HIT_RADIUS_PIXELS:
                            clicked_marker = marker
                            break

            if clicked_marker:
                self.add_annotation(
                    plot_name, plot_widget,
                    clicked_marker.x_val, clicked_marker.y_val,
                    existing_marker=clicked_marker
                )
            else:
                if event.double():
                    self.add_annotation(plot_name, plot_widget, target_time, target_y)
                else:
                    self.current_playback_time = target_time
                    if self.is_playing:
                        self.seek_and_play()
                    self.update_playhead()

    #################### Annotations  ####################

    def add_annotation(self, plot_name, plot, target_time, target_y, existing_marker=None):
        if self.is_playing:
            self.stop_playback()
            self.paused_time = time.time() - self.playback_start_time

        dialog = QtWidgets.QDialog(self)
        title = "Edit Annotation" if existing_marker else "New Annotation"
        dialog.setWindowTitle(f"{title} - {plot_name} @ {target_time:.2f}s")
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
                plot.removeItem(existing_marker)
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
                    marker = AnnotationMarker(target_time, target_y, new_text, plot_name, plot, self)
                    plot.addItem(marker)
                    self.annotations.append({
                        "time": target_time,
                        "y": target_y,
                        "text": new_text,
                        "plot": plot_name,
                        "marker": marker
                    })
            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def clear_annotations(self):
        for ann in self.annotations:
            marker = ann.get('marker')
            plot_name = ann.get('plot')

            if marker:
                for controller in self.plot_cells:
                    if controller.plot_name == plot_name:
                        controller.widget.removeItem(marker)
                        break
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

    def get_current_layout_data(self):
        layout_data = {
            "global_size": self.size_slider.value() if hasattr(self, 'size_slider') else defaultSize,
            "main_splitter_sizes": self.plot_splitter.sizes(),
            "columns": []
        }

        for col in self.columns:
            col_data = {
                "plots": [],
                "sizes": col.sizes()
            }
            for i in range(col.count()):
                widget = col.widget(i)
                for controller in self.plot_cells:
                    if controller.container == widget:
                        toggles_state = {}
                        for cb in getattr(controller, 'toggles', []):
                            toggles_state[cb.text()] = cb.isChecked()

                        local_size = controller.local_slider.value() if hasattr(controller,
                                                                                'local_slider') else defaultSize

                        col_data["plots"].append({
                            "name": controller.plot_name,
                            "local_size": local_size,
                            "toggles": toggles_state
                        })
                        break

            layout_data["columns"].append(col_data)
        return layout_data

    def apply_layout_data(self, layout_data):
        if "columns" not in layout_data:
            raise ValueError("Invalid layout configuration format.")

        if "global_size" in layout_data and hasattr(self, 'size_slider'):
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(layout_data["global_size"])
            self.size_slider.blockSignals(False)

        for col in self.columns:
            col.setParent(None)
            col.deleteLater()
        self.columns.clear()
        self.plot_cells.clear()

        available_plots = list(PlotsSpec.keys())
        fallback_plot = available_plots[0] if available_plots else None
        is_legacy_format = len(layout_data["columns"]) > 0 and isinstance(layout_data["columns"][0], list)
        vertical_sizes_to_apply = []

        for col_data in layout_data["columns"]:
            new_col = self._create_column()
            plot_items = col_data if is_legacy_format else col_data.get("plots", [])

            for plot_item in plot_items:
                if isinstance(plot_item, dict):
                    plot_name = plot_item.get("name", fallback_plot)
                    local_size = plot_item.get("local_size", self.size_slider.value())
                    toggles_state = plot_item.get("toggles", {})
                else:
                    plot_name = plot_item
                    local_size = self.size_slider.value()
                    toggles_state = {}

                valid_plot = plot_name if plot_name in available_plots else fallback_plot

                controller = self.create_plot_cell(valid_plot)
                self.plot_cells.append(controller)
                new_col.addWidget(controller.container)

                if hasattr(controller, 'local_slider'):
                    controller.local_slider.blockSignals(True)
                    controller.local_slider.setValue(local_size)
                    controller.local_slider.blockSignals(False)
                if hasattr(controller, 'set_symbol_size'):
                    controller.set_symbol_size(local_size)

                if toggles_state:
                    for cb in getattr(controller, 'toggles', []):
                        if cb.text() in toggles_state:
                            cb.setChecked(toggles_state[cb.text()])

                controller.update_target_bands(self.audioFeatureExtractor.target_config)
                if hasattr(controller, 'apply_theme'):
                    controller.apply_theme()

            if not is_legacy_format and "sizes" in col_data:
                vertical_sizes_to_apply.append((new_col, col_data["sizes"]))

        self.sync_all_x_axes()
        self.update_plots()

        def apply_splitter_sizes():
            for col_widget, sizes in vertical_sizes_to_apply:
                col_widget.setSizes(sizes)

            if not is_legacy_format and "main_splitter_sizes" in layout_data:
                self.plot_splitter.setSizes(layout_data["main_splitter_sizes"])
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