import queue
import sys
import time
import os
import shutil

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
import pyqtgraph as pg
import qtawesome as qta

import numpy as np
from numpy.f2py.auxfuncs import throw_error

from PlotsSpec import spec, defaultSize, default_stretch
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor, TargetConfig
from signal_processing.AudioFeatures import AudioFeatures, BandwidthTimeSeries, FeatureSnapshot
from ui.AnnotationMarker import AnnotationMarker
from ui.HelpWindow import HelpWindow
from ui.PlotController import PlotController
from ui.TargetConfigDialog import TargetConfigDialog
from ui.workers.AnalysisWorker import AnalysisWorker
from ui.workers.PlaybackWorker import PlaybackWorker
from ui.workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker
from utils import save_to_temp_wav


class LiveMultiPlotWidget(QtWidgets.QWidget):
    file_loaded_signal = QtCore.pyqtSignal(str)
    new_session_signal = QtCore.pyqtSignal()
    close_session_signal = QtCore.pyqtSignal()

    #################### Init ####################

    def __init__(self):
        super().__init__()

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
        self.file_path = None
        self.target_config = TargetConfig()

        self.audioFeatureExtractor = AudioFeatureExtractor(self.target_config)

        self.setup_GUI()
        self.setup_audio()

        self.help_window = None
        self.sample_text_window = None

        self.menu_toggle_actions = {
            'plots': {}
        }

    def setup_audio(self):
        self.audio_format = QAudioFormat()
        self.audio_format.setSampleRate(self.sampling_rate)
        self.audio_format.setChannelCount(1)
        self.audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self.input_device = QMediaDevices.defaultAudioInput()
        self.audio_source = QAudioSource(self.input_device, self.audio_format, self)

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
        targets_menu.addAction("Female", lambda: self.load_targets_from_path("target_female.json"))
        targets_menu.addAction("Male", lambda: self.load_targets_from_path("target_male.json"))
        targets_menu.addSeparator()
        targets_menu.addAction("Import targets...", self.import_targets)
        targets_menu.addAction("Export targets...", self.export_targets)

        # --- View Menu ---
        view_menu = self.menu_bar.addMenu("&View")

        reset_zoom_action = view_menu.addAction("&Reset zoom")
        reset_zoom_action.triggered.connect(self.handle_reset_zoom)

        reset_plots_action = view_menu.addAction("Reset plot spacing")
        reset_plots_action.triggered.connect(self.handle_reset_plots)

        view_menu.addSeparator()

        sample_texts_action = view_menu.addAction("Sample Texts")
        sample_texts_action.triggered.connect(self.show_sample_text_window)

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
        self.clear_icon =  qta.icon('fa5s.trash', color=icon_color)

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
        self.clear_btn.setToolTip("Play/Pause")
        self.clear_btn.clicked.connect(self.handle_clear)
        top_buttons_layout.addWidget(self.clear_btn)

        # --- Push everything following this to the right ---
        top_buttons_layout.addStretch()

        # Row layout controls
        self.add_row_btn = QtWidgets.QPushButton("Add row")
        self.add_row_btn.clicked.connect(self.add_plot_row)
        top_buttons_layout.addWidget(self.add_row_btn)

        self.remove_row_btn = QtWidgets.QPushButton("Remove row")
        self.remove_row_btn.clicked.connect(self.remove_plot_row)
        top_buttons_layout.addWidget(self.remove_row_btn)

        # Column layout controls
        self.add_col_btn = QtWidgets.QPushButton("Add column")
        self.add_col_btn.clicked.connect(self.add_plot_column)
        top_buttons_layout.addWidget(self.add_col_btn)

        self.remove_col_btn = QtWidgets.QPushButton("Remove column")
        self.remove_col_btn.clicked.connect(self.remove_plot_column)
        top_buttons_layout.addWidget(self.remove_col_btn)

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

    def setupPlots(self):
        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.layout.addWidget(self.plot_splitter)

        self.plot_cells = []
        self.columns = []  # Tracks dynamic QSplitter columns

        # Default to 2 columns
        self._create_column()
        self._create_column()

        available_plots = list(spec.keys())
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
        """Helper to inject specific plots into a new row during initialization."""
        for i, col in enumerate(self.columns):
            name = plot_names[i] if i < len(plot_names) else plot_names[-1]
            controller = self.create_plot_cell(name)
            self.plot_cells.append(controller)
            col.addWidget(controller.container)
        self.sync_all_x_axes()

    def create_plot_cell(self, plot_name):
        if not plot_name: return None

        initial_size = self.size_slider.value() if hasattr(self, 'size_slider') else defaultSize

        controller = PlotController(
            plot_name=plot_name,
            all_specs=spec,
            click_callback=self.on_mouse_clicked,
            change_plot_callback=self.handle_plot_selection,
            initial_size=initial_size
        )
        return controller

    def add_plot_row(self):
        """Adds a new row across all existing columns."""
        available_plots = list(spec.keys())
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
        """Removes the bottom row across all columns."""
        # Keep at least 1 row
        if len(self.columns) == 0 or self.columns[0].count() <= 1:
            return

        widgets_to_remove = []
        for col in self.columns:
            last_widget = col.widget(col.count() - 1)
            widgets_to_remove.append(last_widget)
            last_widget.deleteLater()

        self.plot_cells = [c for c in self.plot_cells if c.container not in widgets_to_remove]

    def add_plot_column(self):
        """Adds a new column on the right side, matching the current number of rows."""
        num_rows = self.columns[0].count() if self.columns else 1
        available_plots = list(spec.keys())
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
        """Removes the right-most column."""
        # Keep at least 1 column
        if len(self.columns) <= 1:
            return

        col_to_remove = self.columns.pop()

        # Identify all controllers within this column
        widgets_to_remove = [col_to_remove.widget(i) for i in range(col_to_remove.count())]
        self.plot_cells = [c for c in self.plot_cells if c.container not in widgets_to_remove]

        col_to_remove.deleteLater()

    def handle_plot_selection(self, old_controller, new_plot_name):
        if old_controller.plot_name == new_plot_name:
            return

        # 1. Capture current size and create the new controller
        current_size = old_controller.local_slider.value()
        new_controller = PlotController(
            plot_name=new_plot_name,
            all_specs=spec,
            click_callback=self.on_mouse_clicked,
            change_plot_callback=self.handle_plot_selection,
            initial_size=current_size
        )

        # 2. Swap out the controllers safely inside the QSplitter
        splitter = old_controller.container.parentWidget()
        if isinstance(splitter, QtWidgets.QSplitter):
            # Find exactly where the old plot was and swap it natively
            index = splitter.indexOf(old_controller.container)
            splitter.replaceWidget(index, new_controller.container)
        else:
            # Fallback just in case it ever ends up in a standard layout
            parent_layout = old_controller.container.parentWidget().layout()
            if parent_layout:
                parent_layout.replaceWidget(old_controller.container, new_controller.container)

        # Explicitly show the new container
        new_controller.container.show()

        # Update tracking list
        self.plot_cells[self.plot_cells.index(old_controller)] = new_controller

        # Clean up the old controller
        old_controller.container.deleteLater()
        old_controller.deleteLater()

        # 3. Sync UI menus and apply target configurations
        if new_plot_name in self.menu_toggle_actions['plots']:
            self.menu_toggle_actions['plots'][new_plot_name].setChecked(True)

        new_controller.update_target_bands(self.audioFeatureExtractor.target_config)

        # 4. Push data and sync axes
        self.sync_all_x_axes()
        self.update_plots()

        # 5. Force the camera to frame the newly drawn data
        new_controller.reset_zoom()
        new_controller.set_symbol_size(current_size)

    def sync_all_x_axes(self):
        """Cross-links panning/zooming for all active plots."""
        target_widget = None
        for controller in self.plot_cells:
            if controller.plot_name == 'Loudness':
                target_widget = controller.widget
                break

        if not target_widget: return

        for controller in self.plot_cells:
            if controller.spec.get('linkX') == 'Loudness':
                if controller.widget != target_widget:
                    controller.widget.setXLink(target_widget)

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
            self.clear_icon = qta.icon('fa5s.trash', color=icon_color)  # <-- Add this

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

            if hasattr(self, 'clear_btn'):  # <-- Add this
                self.clear_btn.setIcon(self.clear_icon)

            if hasattr(self, 'save_btn'):
                self.save_btn.setIcon(self.save_icon)

            # Explicitly push theme update down to all plot controllers
            if hasattr(self, 'plot_cells'):
                for controller in self.plot_cells:
                    if hasattr(controller, 'apply_theme'):
                        controller.apply_theme()

        super().changeEvent(event)

    def show_sample_text_window(self):
        if self.sample_text_window is None:
            from ui.SampleTextWindow import SampleTextWindow
            self.sample_text_window = SampleTextWindow()

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
                self.file_path = file_path
                self.file_loaded_signal.emit(file_path)
                self.clear_annotations()
                self.select_analysis_file(file_path)

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
                self.clear_annotations()
                self.file_path = file_name
                self.file_loaded_signal.emit(file_name)
                self.select_analysis_file(file_name)

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

            self.clear_annotations()
            self.file_path = active_audio_path
            self.file_loaded_signal.emit(self.file_path)
            self.select_analysis_file(active_audio_path)

            for annotation in annotations:
                plot_widget = None
                target_plot_key = None

                for controller in self.plot_cells:
                    plot_title = controller.spec.get('title', '')
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
        if not hasattr(self, 'file_path') or not self.file_path or not os.path.exists(self.file_path):
            QtWidgets.QMessageBox.warning(self, "No Audio", "There is no audio currently loaded or recorded to save.")
            return

        base_path, _ = os.path.splitext(self.file_path)
        default_save_path = f"{base_path}_saved.wav"

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Audio As",
            default_save_path,
            "WAV Files (*.wav);;All Files (*)"
        )

        if save_path:
            try:
                shutil.copy2(self.file_path, save_path)
                self.file_path = save_path
                self.file_loaded_signal.emit(self.file_path)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error",
                                               f"An error occurred while saving the audio:\n{str(e)}")

    #################### File analysis ####################

    def select_analysis_file(self, file_name):
        self.loading_dialog = QtWidgets.QProgressDialog("Analyzing audio file...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Please Wait")
        self.loading_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)
        self.loading_dialog.show()

        self.worker = AnalysisWorker(self.audioFeatureExtractor, file_name)
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

        pcm_bytes = self.audio_data.data()
        temp_wav_path = save_to_temp_wav(pcm_bytes, self.sampling_rate)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        unique_wav_path = f"recording_{timestamp}.wav"

        shutil.move(temp_wav_path, unique_wav_path)
        self.file_path = unique_wav_path

        self.current_playback_time = 0
        self.update_playhead()
        self.select_analysis_file(self.file_path)

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
        """Stops playback/recording, clears audio buffers, and resets all plots."""
        # 1. Stop any active media
        if self.is_playing:
            self.stop_playback()
        if self.is_recording:
            self.record_stop()
            self.is_recording = False

        # 2. Reset audio buffers and internal states
        self.file_path = None
        self.analysedAudioFeatures = AudioFeatures()
        self.audio_data.clear()
        self.current_playback_time = 0

        if hasattr(self, 'recording_start_offset'):
            self.recording_start_offset = 0

        # 3. Clear UI annotations
        self.clear_annotations()

        # 4. Wipe all visual curves from the screen
        if hasattr(self, 'plot_cells'):
            for controller in self.plot_cells:
                for curve_name in controller.curves.keys():
                    # Pushing empty arrays forces pyqtgraph to clear the drawn lines/scatters
                    controller.set_curve_data(curve_name, [], [])

                # Reset playhead line to the beginning
                controller.set_playhead_value(0)

        # 5. Reset camera boundaries
        self.handle_reset_zoom()
        print("All data cleared.")

    def stop_playback(self):
        self.is_playing = False
        self.playback_btn.setIcon(self.play_icon)

        if hasattr(self, 'play_worker'):
            self.play_worker.stop_backend()

        self.timer.stop()

    def seek_and_play(self):
        target_time = max(0.0, self.current_playback_time)
        if self.analysedAudioFeatures.sample_rate is None: return

        seek_frame = int(target_time * self.analysedAudioFeatures.sample_rate)

        if hasattr(self, 'play_worker') and self.play_worker.isRunning():
            self.play_worker.stop_backend()
            self.play_worker.wait()

        self.play_worker = PlaybackWorker(self.file_path, seek_frame)
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

        # --- Sync with Controllers ---
        for controller in self.plot_cells:
            controller.set_playhead_value(self.current_playback_time)

            if self.is_recording:
                view_window_seconds = 10.0
                min_x = max(0.0, self.current_playback_time - view_window_seconds)
                controller.widget.setXRange(min_x, max(view_window_seconds, self.current_playback_time), padding=0)

    #################### Misc plot stuff ####################

    def handle_symbol_size_change(self, value):
        """Called whenever the Global slider is moved."""
        if not hasattr(self, 'plot_cells'): return

        for controller in self.plot_cells:
            if hasattr(controller, 'local_slider'):
                controller.local_slider.blockSignals(True)
                controller.local_slider.setValue(value)
                controller.local_slider.blockSignals(False)

            controller.set_symbol_size(value)

    def handle_reset_zoom(self):
        if not hasattr(self, 'plot_cells'): return
        for controller in self.plot_cells:
            controller.reset_zoom()

    def handle_toggle_plot(self, plot_key: str, checked: bool):
        for controller in self.plot_cells:
            if controller.plot_name == plot_key:
                controller.set_plot_visible(checked)

    def handle_reset_plots(self):
        # --- 1. Distribute Draggable Sizes Equally ---
        col_count = len(self.columns)
        if col_count > 0:
            total_width = self.plot_splitter.width()
            self.plot_splitter.setSizes([int(total_width / col_count)] * col_count)

            for col in self.columns:
                row_count = col.count()
                if row_count > 0:
                    total_height = col.height()
                    col.setSizes([int(total_height / row_count)] * row_count)

        # --- 2. Reset Component Visibilities & Menu Sync ---
        for plot_key, plot_spec in spec.items():
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
            for curve_name, curve_config in controller.curves.items():
                if not hasattr(self.analysedAudioFeatures, curve_config['analysisResult']):
                    continue

                data = getattr(self.analysedAudioFeatures, curve_config['analysisResult'])
                if not hasattr(data, 'x') or not hasattr(data, 'y'):
                    continue

                is_spectrogram = curve_config.get('is_spectrogram', False)
                if not is_spectrogram and len(data.x) != len(data.y):
                    continue

                controller.set_curve_data(
                    curve_name=curve_name,
                    x=data.x,
                    y=data.y,
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
                print(f"Successfully saved targets to: {save_path}")
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
                print(f"Successfully loaded targets from: {open_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Load Error",
                                               f"An error occurred while loading targets:\n{str(e)}")

    def load_targets_from_path(self, target_file_name):
        try:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                base_dir = os.path.join(base_dir, '..')

            full_path = os.path.join(base_dir, 'targets', target_file_name)
            new_config = TargetConfig.from_json(full_path)
            self.set_target_config(new_config)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", f"An error occurred while loading targets:\n{str(e)}")

    def set_target_config(self, new_config: TargetConfig):
        self.audioFeatureExtractor.target_config = new_config

        for controller in self.plot_cells:
            for band in controller.target_bands.values():
                band['enabled'] = True
            controller.update_target_bands(new_config)

        self.analysedAudioFeatures.size = self.audioFeatureExtractor.recalculate_size(self.analysedAudioFeatures)
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
                if self.file_path:
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
        if hasattr(self, 'file_path') and self.file_path:
            base_path, _ = os.path.splitext(self.file_path)
            default_save_path = f"{base_path}.json"

        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotations",
            default_save_path,
            "JSON Files (*.json);;All Files (*)"
        )

        if save_path and self.file_path is not None:
            try:
                markers = [ann['marker'] for ann in self.annotations if 'marker' in ann]
                AnnotationMarker.save_to_file(save_path, markers, self.file_path)
                print(f"Successfully saved annotations to: {save_path}")

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving:\n{str(e)}")

    #################### Help  ####################

    def show_help_window(self):
        if self.help_window is None:
            self.help_window = HelpWindow()

        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())