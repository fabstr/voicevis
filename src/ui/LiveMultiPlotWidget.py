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

    def setup_audio(self):
        # 1. Define the audio format (Standard CD quality PCM)
        self.audio_format = QAudioFormat()
        self.audio_format.setSampleRate(self.sampling_rate)
        self.audio_format.setChannelCount(1)  # Mono for voice
        self.audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)  # 16-bit PCM

        # 2. Get default audio input device (Microphone)
        self.input_device = QMediaDevices.defaultAudioInput()

        # 3. Create the QAudioSource
        self.audio_source = QAudioSource(self.input_device, self.audio_format, self)

        # 4. Set up a QByteArray and QBuffer to store the recorded data in RAM
        self.audio_data = QByteArray()
        self.audio_buffer = QBuffer(self.audio_data)

        self.audio_queue = queue.Queue()

        self.poll_timer = QtCore.QTimer()
        self.poll_timer.setInterval(33)  # Grab audio every 100ms
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
        file_menu.addAction("&Open", "Ctrl+O", self.browse_file)
        file_menu.addAction("&Save Annotations", "Ctrl+S", self.save_annotations)
        file_menu.addAction("Save &Audio As...", "Ctrl+Shift+S", self.save_audio)
        file_menu.addSeparator()
        file_menu.addAction("&Close", "Ctrl+W", self.close)

        # --- Targets Menu [NEW] ---
        targets_menu = self.menu_bar.addMenu("&Targets")
        targets_menu.addAction("Set Targets...", self.open_targets_dialog)
        targets_menu.addSeparator()
        targets_menu.addAction("Female", lambda: self.load_targets_from_path("src/target_female.json"))
        targets_menu.addAction("Male", lambda: self.load_targets_from_path("src/target_male.json"))
        targets_menu.addSeparator()
        targets_menu.addAction("Import targets...", self.import_targets)
        targets_menu.addAction("Export targets...", self.export_targets)

        # --- View Menu ---
        plots_menu = self.menu_bar.addMenu("&Plots")

        reset_zoom_action = plots_menu.addAction("&Reset zoom")
        reset_zoom_action.triggered.connect(self.handle_reset_zoom)

        # New "Reset plots" Action
        reset_plots_action = plots_menu.addAction("Reset plots")
        reset_plots_action.triggered.connect(self.handle_reset_plots)

        # New "Reset plots" Action
        show_all_plots_action = plots_menu.addAction("Show all plots")
        show_all_plots_action.triggered.connect(self.show_all_plots)

        plots_menu.addSeparator()

        # We keep track of the toggle actions in a dictionary so handle_reset_plots can re-check them
        self.menu_toggle_actions = {
            'plots': {},
            'pixels': {},
            'bandwidths': {}
        }

        # Grouping dynamically by Plot
        for plot_key, plot_spec in spec.items():
            plot_submenu = plots_menu.addMenu(plot_spec['title'])

            # 1. Action to Show/Hide the entire Plot panel
            is_visible = not plot_spec.get('hidden', False)

            show_plot_action = plot_submenu.addAction("Show Plot Panel")
            show_plot_action.setCheckable(True)
            show_plot_action.setChecked(is_visible)

            show_plot_action.triggered.connect(
                lambda checked, name=plot_key: self.handle_toggle_plot(name, checked)
            )
            self.menu_toggle_actions['plots'][plot_key] = show_plot_action
            plot_submenu.addSeparator()

            # 2. Actions for every pixel/scatter curve inside this plot
            for curve_key, curve_spec in plot_spec['curves'].items():
                if not curve_spec.get("BW", False):
                    show_pixel_action = plot_submenu.addAction(f"Show '{curve_key}' Pixels")
                    show_pixel_action.setCheckable(True)
                    show_pixel_action.setChecked(True)
                    show_pixel_action.triggered.connect(
                        lambda checked, p_key=plot_key, c_key=curve_key:
                        self.handle_toggle_pixels(p_key, c_key, checked)
                    )
                    # Use a composite key to safely track nested components
                    self.menu_toggle_actions['pixels'][(plot_key, curve_key)] = show_pixel_action

            # 3. Actions for every Bandwidth curve inside this plot
            for curve_key, curve_spec in plot_spec['curves'].items():
                if curve_spec.get("BW", False):
                    show_bw_action = plot_submenu.addAction("Show Bandwidth Region")
                    show_bw_action.setCheckable(True)
                    show_bw_action.setChecked(True)
                    show_bw_action.triggered.connect(
                        lambda checked, p_key=plot_key, c_key=curve_key:
                        self.handle_toggle_bandwidth(p_key, c_key, checked)
                    )
                    self.menu_toggle_actions['bandwidths'][(plot_key, curve_key)] = show_bw_action

        # --- View Menu (Theme Settings) ---
        view_menu = self.menu_bar.addMenu("&View")

        # QActionGroup ensures only one option is checked at a time
        self.theme_group = QtGui.QActionGroup(self)
        self.theme_group.setExclusive(True)

        self.action_os_default = QtGui.QAction("OS Default", self, checkable=True)
        self.action_light = QtGui.QAction("Light Mode", self, checkable=True)
        self.action_dark = QtGui.QAction("Dark Mode", self, checkable=True)

        self.theme_group.addAction(self.action_os_default)
        self.theme_group.addAction(self.action_light)
        self.theme_group.addAction(self.action_dark)

        # Connect actions to the logic
        self.action_os_default.triggered.connect(self.set_theme_os_default)
        self.action_light.triggered.connect(self.set_theme_light)
        self.action_dark.triggered.connect(self.set_theme_dark)

        view_menu.addAction(self.action_os_default)
        view_menu.addAction(self.action_light)
        view_menu.addAction(self.action_dark)

        # Default to OS behavior on initialization
        self.action_os_default.setChecked(True)

        # Build the Help Menu
        help_menu = self.menu_bar.addMenu("Help")

        # Add the Action
        open_help_action = help_menu.addAction("Documentation")
        open_help_action.setShortcut("F1")
        open_help_action.triggered.connect(self.show_help_window)

        self.layout.setMenuBar(self.menu_bar)

    def setupControlButtons(self):
        top_buttons_layout = QtWidgets.QHBoxLayout()

        # Pre-load QtAwesome icons
        self.record_icon = qta.icon('fa5s.microphone')
        # self.stop_icon = qta.icon('fa5s.mirophone-slash')
        self.stop_icon = qta.icon('fa5s.stop')  # Or 'fa5s.stop'
        self.play_icon = qta.icon('fa5s.play')
        self.pause_icon = qta.icon('fa5s.pause')
        self.save_icon = qta.icon('fa5s.save')

        # Record Button
        self.record_stop_btn = QtWidgets.QPushButton()
        self.record_stop_btn.setFixedSize(40, 40)  # Harmonized size
        self.record_stop_btn.setIcon(self.record_icon)
        self.record_stop_btn.setIconSize(QtCore.QSize(20, 20))
        self.record_stop_btn.setToolTip("Record")  # Added Tooltip
        self.record_stop_btn.clicked.connect(self.handle_record_stop)

        # Playback Button
        self.playback_btn = QtWidgets.QPushButton()
        self.playback_btn.setFixedSize(40, 40)  # Harmonized size
        self.playback_btn.setIcon(self.play_icon)
        self.playback_btn.setIconSize(QtCore.QSize(20, 20))
        self.playback_btn.setToolTip("Play/Pause")
        self.playback_btn.clicked.connect(self.handle_playback)

        # Save Button
        self.save_btn = QtWidgets.QPushButton()
        self.save_btn.setFixedSize(40, 40)  # Harmonized size
        self.save_btn.setIcon(self.save_icon)
        self.save_btn.setIconSize(QtCore.QSize(20, 20))
        self.save_btn.setToolTip("Save Annotations")
        self.save_btn.clicked.connect(self.save_annotations)

        top_buttons_layout.addWidget(self.record_stop_btn)
        top_buttons_layout.addWidget(self.playback_btn)
        top_buttons_layout.addWidget(self.save_btn)

        ################ Plot item size slider
        # Label for the slider
        self.size_label = QtWidgets.QLabel("Point Size:")
        top_buttons_layout.addWidget(self.size_label)

        # The Slider
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(1)
        self.size_slider.setMaximum(5)
        self.size_slider.setValue(defaultSize)  # Default initial size
        self.size_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(1)
        self.size_slider.setFixedWidth(120)  # Keeps it looking clean

        # Connect to the callback function
        self.size_slider.valueChanged.connect(self.handle_symbol_size_change)
        top_buttons_layout.addWidget(self.size_slider)

        # Push everything to the left side of the window
        top_buttons_layout.addStretch()

        top_buttons_layout.addStretch()
        self.layout.addLayout(top_buttons_layout)

    def setupPlots(self):
        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        stretch_factors = []
        self.plot_controllers = {}

        for plot_name, plot_spec in spec.items():
            controller = PlotController(plot_name, plot_spec, self.on_mouse_clicked)
            self.plot_controllers[plot_name] = controller

            # Target bands setup is fully delegated into the controller class now!
            self.plot_splitter.addWidget(controller.widget)

            stretch = plot_spec.get('stretch', default_stretch)
            stretch_factors.append(stretch)

        # Secondary Pass: Cross-linking
        for plot_name, plot_spec in spec.items():
            if plot_spec.get('linkX') is not None:
                target_plot_name = plot_spec['linkX']
                if target_plot_name in self.plot_controllers:
                    target_widget = self.plot_controllers[target_plot_name].widget
                    self.plot_controllers[plot_name].widget.setXLink(target_widget)

        for idx, stretch in enumerate(stretch_factors):
            self.plot_splitter.setStretchFactor(idx, stretch)

        self.layout.addWidget(self.plot_splitter)

    # --- Theme Switching Methods ---
    def set_theme_os_default(self):
        # unsetColorScheme removes any manual override, falling back to dynamic OS settings
        if hasattr(QtGui.QGuiApplication.styleHints(), 'unsetColorScheme'):
            QtGui.QGuiApplication.styleHints().unsetColorScheme()
        else:
            print("Native OS theme syncing requires Qt 6.8+")

    def set_theme_light(self):
        # Overrides the OS setting to force Light Mode
        if hasattr(QtGui.QGuiApplication.styleHints(), 'setColorScheme'):
            QtGui.QGuiApplication.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)

    def set_theme_dark(self):
        # Overrides the OS setting to force Dark Mode
        if hasattr(QtGui.QGuiApplication.styleHints(), 'setColorScheme'):
            QtGui.QGuiApplication.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Dark)


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
        """Parses a JSON annotation file, loads the linked audio, and redraws markers."""
        try:
            # 1. Use the static method from AnnotationMarker
            active_audio_path, annotations, original_audio_path, fallback_audio_path = AnnotationMarker.load_from_file(json_file_path)

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

            # 2. Clear old data and load the audio file using the found path
            self.clear_annotations()
            self.file_path = active_audio_path
            self.file_loaded_signal.emit(self.file_path)
            self.select_analysis_file(active_audio_path)

            # 3. Parse annotations
            for annotation in annotations:
                plot_widget = None
                target_plot_key = None

                # Match the saved text against either the dictionary key or the plot's title
                for p_key, p_data in self.plots.items():
                    # Get the title from your spec config if it exists
                    from PlotsSpec import spec
                    plot_title = spec.get(p_key, {}).get('title', '')

                    if annotation['plot'] == p_key or annotation['plot'] == plot_title:
                        plot_widget = p_data['plot']
                        target_plot_key = p_key
                        break

                # Recreate the marker and save it to memory
                if plot_widget:
                    # Crucial: Override the text feature string back to the standardized plot key
                    # so future updates or saves remain stable
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
        """Saves the currently loaded/recorded audio to a permanent WAV file."""
        if not hasattr(self, 'file_path') or not self.file_path or not os.path.exists(self.file_path):
            QtWidgets.QMessageBox.warning(self, "No Audio", "There is no audio currently loaded or recorded to save.")
            return

        # Determine a default save name based on the current file path
        base_path, _ = os.path.splitext(self.file_path)
        default_save_path = f"{base_path}_saved.wav"

        # Open a save file dialog
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Audio As",
            default_save_path,
            "WAV Files (*.wav);;All Files (*)"
        )

        if save_path:
            try:
                # Copy the temporary/current file to the new permanent destination
                shutil.copy2(self.file_path, save_path)
                print(f"Successfully saved audio to: {save_path}")

                # Update the application's file path to point to the new permanent file
                # This ensures future annotations save alongside the permanent file, not the temp one.
                self.file_path = save_path
                self.file_loaded_signal.emit(self.file_path)

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error",
                                               f"An error occurred while saving the audio:\n{str(e)}")



    #################### File analysis ####################

    def select_analysis_file(self, file_name):
        # 1. Setup and show the loading dialog
        self.loading_dialog = QtWidgets.QProgressDialog("Analyzing audio file...", None, 0, 0, self)
        self.loading_dialog.setWindowTitle("Please Wait")
        self.loading_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.loading_dialog.setMinimumDuration(0)  # Ensure it shows immediately
        self.loading_dialog.show()

        # 2. Setup the worker thread
        self.worker = AnalysisWorker(self.audioFeatureExtractor, file_name)

        # Connect signals to slots
        self.worker.result_ready.connect(self.on_analysis_finished)
        self.worker.error_occurred.connect(self.on_analysis_error)
        self.worker.finished.connect(self.loading_dialog.close)

        # 3. Start the background thread
        self.worker.start()

    def on_analysis_finished(self, results):
        """Called automatically when the worker thread finishes successfully."""
        self.analysedAudioFeatures = results
        self.current_playback_time = 0
        self.update_plots()

    def on_analysis_error(self, error_msg):
        """Called automatically if the worker thread encounters an error."""
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
            # --- UI Updates ---
            self.record_stop_btn.setIcon(self.stop_icon)
            self.record_stop_btn.setToolTip("Stop Recording")  # Use tooltip instead of text

            # Clear the analysed features
            self.analysedAudioFeatures = AudioFeatures()
            self.clear_annotations()

            # 2. Setup background worker (Clear queue from previous runs)
            while not self.audio_queue.empty():
                self.audio_queue.get()

            self.rt_worker = RealTimeAnalysisWorker(self.audioFeatureExtractor, self.audio_queue, self.sampling_rate)
            self.rt_worker.new_data_point.connect(self.append_live_data)
            self.rt_worker.start()

            # 3. Audio Recording Logic
            self.audio_data.clear()
            self.audio_buffer.open(QIODevice.OpenModeFlag.ReadWrite)

            # Track exactly where we are in the byte array to avoid the Cursor Trap
            self.last_read_pos = 0

            self.audio_source.start(self.audio_buffer)
            self.poll_timer.start()  # Start the data harvester

            self.timer.start()

            print("Real-time recording started...")

    def record_stop(self):
        # --- UI Updates ---
        self.record_stop_btn.setIcon(self.record_icon)
        self.record_stop_btn.setToolTip("Record")
        print("Recording stopped.")

        # --- Audio Stop Logic ---
        self.poll_timer.stop()

        # [NEW] Force one last read to catch stranded bytes before closing the buffer
        self.read_audio_chunk()

        self.audio_source.stop()
        self.audio_buffer.close()
        self.timer.stop()

        # --- Stop Worker ---
        if hasattr(self, 'rt_worker'):
            self.rt_worker.stop()
            self.rt_worker.wait()

        # --- Save to WAV for Playback ---
        pcm_bytes = self.audio_data.data()

        # 1. Save to the temporary location first
        temp_wav_path = save_to_temp_wav(pcm_bytes, self.sampling_rate)

        # 2. Generate a unique filename using the current date and time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        unique_wav_path = f"recording_{timestamp}.wav"

        # 3. Rename/move the temp file to the unique, permanent filename
        shutil.move(temp_wav_path, unique_wav_path)

        # 4. Set the app to use the new unique file
        self.file_path = unique_wav_path

        self.current_playback_time = 0
        self.update_playhead()

        # Perform analysis
        self.select_analysis_file(self.file_path)

    def read_audio_chunk(self):
        """Safely slices new audio bytes directly from RAM without touching the buffer cursor."""
        current_size = self.audio_data.size()

        # If the array has grown since we last checked...
        if current_size > self.last_read_pos:
            # Extract just the new bytes using .mid(start_position, length)
            new_bytes = self.audio_data.mid(self.last_read_pos, current_size - self.last_read_pos).data()

            # Update our tracker so we don't read these bytes again
            self.last_read_pos = current_size

            if new_bytes:
                self.audio_queue.put(new_bytes)

    def append_live_data(self, latest_point: FeatureSnapshot):
        """Dispatches an incoming streaming FeatureSnapshot directly into
        the active plotting controllers for incremental drawing.
        """
        for plot_name, controller in self.plot_controllers.items():
            for curve_name in controller.curves.keys():
                # Route the snapshot data down into the controller
                controller.append_curve_point(
                    curve_name=curve_name,
                    snapshot=latest_point,
                    audio_features_ctx=self.analysedAudioFeatures
                )

        # Move global elements like synced playhead lines or scrolling viewports
        self.update_playhead()

    def handle_playback(self):
        if self.is_recording:
            print("Cannot start playback while recording.")
            return

        if not self.is_playing:
            self.seek_and_play()
            print("Playback started...")
        else:
            self.stop_playback()

    def stop_playback(self):
        self.is_playing = False
        self.playback_btn.setIcon(self.play_icon)  # FIXED: Ensured icon always goes to Play

        if hasattr(self, 'play_worker'):
            self.play_worker.stop_backend()

        self.timer.stop()

    def seek_and_play(self):
        target_time = max(0.0, self.current_playback_time)
        seek_frame = int(target_time * self.analysedAudioFeatures.sample_rate)

        # Clear old worker if running
        if hasattr(self, 'play_worker') and self.play_worker.isRunning():
            self.play_worker.stop_backend()
            self.play_worker.wait()

        # Spawn background playback
        self.play_worker = PlaybackWorker(self.file_path, seek_frame)
        self.play_worker.playback_finished.connect(self.stop_playback)
        self.play_worker.start()

        self.playback_start_time = time.time() - target_time
        self.is_playing = True
        self.playback_btn.setIcon(self.pause_icon)  # FIXED: Unified explicit icon setting here
        self.timer.start()

    def update_playhead(self):
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time if self.is_playing else 0
            if self.current_playback_time > self.analysedAudioFeatures.length_seconds:
                self.stop_playback()
                self.current_playback_time = 0
        elif self.is_recording:
            # Calculate time based on raw bytes recorded (16-bit Mono = 2 bytes per sample)
            self.current_playback_time = self.audio_data.size() / (2 * self.sampling_rate)

            # Update the max length so playback works correctly later even with trailing silence
            self.analysedAudioFeatures.length_seconds = self.current_playback_time

        # --- Updated Loop utilizing the new PlotController setter ---
        for plot_name, controller in self.plot_controllers.items():
            controller.set_playhead_value(self.current_playback_time)

            if self.is_recording:
                view_window_seconds = 10.0
                min_x = max(0.0, self.current_playback_time - view_window_seconds)
                controller.widget.setXRange(min_x, max(view_window_seconds, self.current_playback_time), padding=0)

    #################### Misc plot stuff ####################

    def handle_symbol_size_change(self, value):
        """Called whenever the slider is moved.

        'value' will be an integer between 1 and 5.
        """
        for controller in self.plot_controllers.values():
            controller.set_symbol_size(value)

    def handle_reset_zoom(self):
        """Resets the zoom, applying fixed min/max spec boundaries where defined,
        and falling back to autoRange elsewhere across all controllers.
        """
        for controller in self.plot_controllers.values():
            controller.reset_zoom()

    def handle_toggle_plot(self, plot_key: str, checked: bool):
        """Toggles visibility of the entire plot widget panel."""
        if plot_key in self.plot_controllers:
            self.plot_controllers[plot_key].set_plot_visible(checked)

    def handle_toggle_pixels(self, plot_key: str, curve_key: str, checked: bool):
        """Toggles visibility of standard scatter points or lines on a specific canvas."""
        if plot_key in self.plot_controllers:
            self.plot_controllers[plot_key].set_curve_visible(curve_key, checked)

    def handle_toggle_bandwidth(self, plot_key: str, curve_key: str, checked: bool):
        """Toggles visibility of bandwidth shaded regions and bounds."""
        if plot_key in self.plot_controllers:
            self.plot_controllers[plot_key].set_bandwidth_visible(curve_key, checked)

    def handle_reset_plots(self):
        """Restores visibility to all plots, curves, and bandwidth regions,
        updates the menu checkboxes, and resets the draggable layout splitter
        back to its original default stretch configurations.
        """
        # --- 1. Reset Draggable Sizes ---
        if hasattr(self, 'plot_splitter'):
            # Look up the current combined height of the plot container area
            total_height = self.plot_splitter.height()

            # Recalculate total stretch units allocated across all specs
            total_stretch = sum(plot_spec.get('stretch', default_stretch) for plot_spec in spec.values())

            # Calculate pixel distribution per plot based on its original stretch factor
            default_sizes = []
            for plot_spec in spec.values():
                stretch = plot_spec.get('stretch', default_stretch)
                # Assign proportional pixel shares from the live height layout
                allocated_pixels = int((stretch / total_stretch) * total_height)
                default_sizes.append(allocated_pixels)

            # Forces the splitter to re-snap to the original geometric proportions
            self.plot_splitter.setSizes(default_sizes)

        # --- 2. Reset Component Visibilities & Menu Sync ---
        for plot_key, plot_spec in spec.items():
            # Reset Plot Panel Visibility to Default Spec
            is_visible = not plot_spec.get('hidden', False)

            self.handle_toggle_plot(plot_key, is_visible)
            if plot_key in self.menu_toggle_actions['plots']:
                self.menu_toggle_actions['plots'][plot_key].setChecked(is_visible)

            for curve_key, curve_spec in plot_spec['curves'].items():
                # Reset Pixel Visibility
                if not curve_spec.get("BW", False):
                    self.handle_toggle_pixels(plot_key, curve_key, True)
                    action_key = (plot_key, curve_key)
                    if action_key in self.menu_toggle_actions['pixels']:
                        self.menu_toggle_actions['pixels'][action_key].setChecked(True)

                # Reset Bandwidth Visibility
                else:
                    self.handle_toggle_bandwidth(plot_key, curve_key, True)
                    action_key = (plot_key, curve_key)
                    if action_key in self.menu_toggle_actions['bandwidths']:
                        self.menu_toggle_actions['bandwidths'][action_key].setChecked(True)

    def show_all_plots(self):
        # --- 1. Reset Draggable Sizes ---
        if hasattr(self, 'plot_splitter'):
            # Look up the current combined height of the plot container area
            total_height = self.plot_splitter.height()

            # Recalculate total stretch units allocated across all specs
            total_stretch = sum(plot_spec.get('stretch', default_stretch) for plot_spec in spec.values())

            # Calculate pixel distribution per plot based on its original stretch factor
            default_sizes = []
            for plot_spec in spec.values():
                stretch = plot_spec.get('stretch', default_stretch)
                # Assign proportional pixel shares from the live height layout
                allocated_pixels = int((stretch / total_stretch) * total_height)
                default_sizes.append(allocated_pixels)

            # Forces the splitter to re-snap to the original geometric proportions
            self.plot_splitter.setSizes(default_sizes)

        # --- 2. Reset Component Visibilities & Menu Sync ---
        for plot_key, plot_spec in spec.items():
            self.handle_toggle_plot(plot_key, True)

            if plot_key in self.menu_toggle_actions['plots']:
                self.menu_toggle_actions['plots'][plot_key].setChecked(True)

    def update_plots(self):
        for plot_name, controller in self.plot_controllers.items():
            for curve_name, curve_config in controller.curves.items():

                # Ensure the required feature exists in our AudioFeatures result object
                if not hasattr(self.analysedAudioFeatures, curve_config['analysisResult']):
                    continue

                # Retrieve the data object (e.g., a SignalTimeSeries instance)
                data = getattr(self.analysedAudioFeatures, curve_config['analysisResult'])

                # Guard against unexpected types or mismatched vectors
                if not hasattr(data, 'x') or not hasattr(data, 'y'):
                    continue
                if len(data.x) != len(data.y):
                    print(f"Mismatch in length for {plot_name}.{curve_name}")
                    continue

                # Route rendering data through the clean interface
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
        """Displays a detached clean configuration panel dialog box for visual target configs."""
        # 1. Instantiate the dialog passing your extractor config payload as the strict input interface
        dialog = TargetConfigDialog(self.audioFeatureExtractor.target_config, parent=self)

        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            # 2. Extract updated TargetConfig instance out of the dialog wrapper on successful submission
            updated_config = dialog.get_confirmed_config()
            self.audioFeatureExtractor.target_config = updated_config

            # 3. Dynamic lookup and injection across our clean PlotController abstraction
            for plot_name, controller in self.plot_controllers.items():

                # Synchronize enablement states from the dialog GUI elements into the controller bands
                for target_name, band in controller.target_bands.items():
                    key = target_name.lower()
                    is_enabled = dialog.gui_elements[key]['cb'].isChecked() if key in dialog.gui_elements else True
                    band['enabled'] = is_enabled

                    if not is_enabled:
                        band['item'].setVisible(False)

                # Let the controller automatically map and update the min/max regions
                controller.update_target_bands(updated_config)

            # 4. Trigger calculations downstream and refresh active viewports
            self.analysedAudioFeatures = self.audioFeatureExtractor.recalculate_size(self.analysedAudioFeatures)
            self.update_plots()

    def export_targets(self):
        """Dumps TargetConfig rules directly to a standard JSON or text file."""
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Targets", "", "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        if save_path:
            try:
                # Leverage the TargetConfig 4-significant-digits JSON exporter directly
                config_obj = self.audioFeatureExtractor.target_config
                config_obj.to_json(save_path)
                print(f"Successfully saved targets to: {save_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving targets:\n{str(e)}")

    def import_targets(self):
        """Opens a file dialog to dynamically select and load a JSON configuration file."""
        open_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Targets", "", "Text/JSON Files (*.txt *.json);;All Files (*)"
        )
        if open_path:
            self.load_targets_from_path(open_path)

    def load_targets_from_path(self, open_path):
        """Shared logic to read, parse, and synchronize TargetConfig configurations with the UI."""
        try:
            new_config = TargetConfig.from_json(open_path)
            self.audioFeatureExtractor.target_config = new_config

            for plot_name, controller in self.plot_controllers.items():
                for band in controller.target_bands.values():
                    band['enabled'] = True

                controller.update_target_bands(new_config)

            self.analysedAudioFeatures.size = self.audioFeatureExtractor.recalculate_size(self.analysedAudioFeatures)
            self.update_plots()
            print(f"Successfully loaded targets from: {open_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error",
                                           f"An error occurred while loading targets:\n{str(e)}")
            raise e


    #################### Mouse & keyboard actions ####################

    def keyPressEvent(self, event):
        # Check if the pressed key is the Spacebar
        if event.key() == QtCore.Qt.Key.Key_Space:
            if self.is_playing:
                # FIXED: Route through stop_playback to safely stop the worker thread and change the button icon
                self.stop_playback()
            else:
                if self.file_path:
                    self.seek_and_play()

            event.accept()  # Tell Qt we handled this key press
        else:
            # Pass any other keys (like arrows, etc.) back to the standard Qt handler
            super().keyPressEvent(event)

    def on_mouse_clicked(self, event, plot_widget, plot_name):
        # Check if the click was a left-click
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.scenePos()  # The pixel coordinates of the click

            # We don't need to guess the plot anymore; we just use plot_widget!
            mouse_point = plot_widget.plotItem.vb.mapSceneToView(pos)

            # The X and Y coordinates
            target_time = mouse_point.x()
            target_y = mouse_point.y()

            HIT_RADIUS_PIXELS = 15  # Generous clickable area
            clicked_marker = None

            for ann in self.annotations:
                if ann['plot'] == plot_name:
                    marker = ann['marker']

                    # Map the marker's underlying data coordinates back to screen pixels
                    marker_pt = QtCore.QPointF(marker.x_val, marker.y_val)
                    scene_pt = plot_widget.plotItem.vb.mapViewToScene(marker_pt)

                    if scene_pt:
                        # Calculate the physical pixel distance between the mouse and the star
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
                # if a double click, handle new annotations
                if event.double():
                    self.add_annotation(plot_name, plot_widget, target_time, target_y)

                # if a single click, update current playback time and handle playback
                else:
                    self.current_playback_time = target_time

                    if self.is_playing:
                        self.seek_and_play()

                    self.update_playhead()



    #################### Annotations  ####################

    def add_annotation(self, plot_name, plot, target_time, target_y, existing_marker=None):
        # FIXED: Route cleanly through stop_playback() to keep states and UI synced
        if self.is_playing:
            self.stop_playback()
            self.paused_time = time.time() - self.playback_start_time

        # Setup the Custom Dialog Window
        dialog = QtWidgets.QDialog(self)
        title = "Edit Annotation" if existing_marker else "New Annotation"
        dialog.setWindowTitle(f"{title} - {plot_name} @ {target_time:.2f}s")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Multi-row text box
        text_edit = QtWidgets.QTextEdit(dialog)
        if existing_marker:
            text_edit.setPlainText(existing_marker.text_val)
        layout.addWidget(text_edit)

        # Setup Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(save_btn)

        # Only show the Delete button if we are editing an existing annotation
        if existing_marker:
            delete_btn = QtWidgets.QPushButton("Delete")
            btn_layout.addWidget(delete_btn)

            def on_delete():
                # Remove the visual symbol from the graph
                plot.removeItem(existing_marker)
                # Remove the dictionary from our master list
                self.annotations = [a for a in self.annotations if a.get('marker') != existing_marker]
                dialog.accept()

            delete_btn.clicked.connect(on_delete)

        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Save Logic
        def on_save():
            new_text = text_edit.toPlainText().strip()
            if new_text:
                if existing_marker:
                    # Update existing marker and dict
                    existing_marker.text_val = new_text
                    existing_marker.setToolTip(new_text)
                    for ann in self.annotations:
                        if ann.get('marker') == existing_marker:
                            ann['text'] = new_text
                            break
                else:
                    # Create new marker
                    marker = AnnotationMarker(target_time, target_y, new_text, plot_name, plot, self)
                    plot.addItem(marker)

                    # Store the complete dict
                    self.annotations.append({
                        "time": target_time,
                        "y": target_y,
                        "text": new_text,
                        "plot": plot_name,
                        "marker": marker  # Keeping the object reference makes deletion easy
                    })
            dialog.accept()

        # Connect buttons
        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def clear_annotations(self):
        """Removes all current annotations from the plots and memory."""
        for ann in self.annotations:
            marker = ann.get('marker')
            plot_name = ann.get('plot')

            # Route removal through the controller's underlying widget pipeline
            if marker and plot_name in self.plot_controllers:
                self.plot_controllers[plot_name].widget.removeItem(marker)
        self.annotations.clear()

    def save_annotations(self):
        """Saves the self.annotations list of AnnotationMarker objects to a JSON file."""
        if not hasattr(self, 'annotations') or not self.annotations:
            QtWidgets.QMessageBox.warning(self, "No Annotations", "There are no annotations to save yet.")
            return

        # Determine Default Save Path
        default_save_path = ""
        if hasattr(self, 'file_path') and self.file_path:
            base_path, _ = os.path.splitext(self.file_path)
            default_save_path = f"{base_path}.json"  # Changed to .json

        # Open a save file dialog
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotations",
            default_save_path,
            "JSON Files (*.json);;All Files (*)"  # Changed filter
        )

        if save_path and self.file_path is not None:
            try:
                markers = [ann['marker'] for ann in self.annotations if 'marker' in ann]
                AnnotationMarker.save_to_file(save_path, markers, self.file_path)
                print(f"Successfully saved annotations to: {save_path}")

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving:\n{str(e)}")



    #################### Hwlp  ####################

    def show_help_window(self):
        # Create the window only if it doesn't exist yet
        if self.help_window is None:
            self.help_window = HelpWindow()

        # Show it and bring it to the front
        self.help_window.show()
        self.help_window.raise_()
        self.help_window.activateWindow()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())