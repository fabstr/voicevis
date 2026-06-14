import queue
import shutil
import sys
import time
import os
import json

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
import pyqtgraph as pg
import qtawesome as qta

import numpy as np

from PlotsSpec import spec, defaultSize, default_stretch
from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor, TargetConfig
from signal_processing.AudioFeatures import AudioFeatures, BandwidthTimeSeries
from ui.AnnotationMarker import AnnotationMarker
from ui.workers.AnalysisWorker import AnalysisWorker
from ui.workers.PlaybackWorker import PlaybackWorker
from ui.workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker
from utils import save_to_file, load_from_file, save_to_temp_wav



class LiveMultiPlotWidget(QtWidgets.QWidget):
    file_loaded_signal = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.sampling_rate = 44100
        self.analysedAudioFeatures = AudioFeatures()

        self.annotations = []
        self.plots = {}
        self.target_bands = {}

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
        self.timer.setInterval(30)
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
        targets_menu.addAction("Female", lambda: self._load_targets_from_path("src/target_female.json"))
        targets_menu.addSeparator()
        targets_menu.addAction("Import targets...", self.import_targets)
        targets_menu.addAction("Export targets...", self.export_targets)

        # --- View Menu ---
        view_menu = self.menu_bar.addMenu("&View")

        reset_zoom_action = view_menu.addAction("&Reset zoom")
        reset_zoom_action.triggered.connect(self.handle_reset_zoom)

        # New "Reset plots" Action
        reset_plots_action = view_menu.addAction("Reset plots")
        reset_plots_action.triggered.connect(self.handle_reset_plots)

        view_menu.addSeparator()

        # We keep track of the toggle actions in a dictionary so handle_reset_plots can re-check them
        self.menu_toggle_actions = {
            'plots': {},
            'pixels': {},
            'bandwidths': {}
        }

        # Grouping dynamically by Plot
        for plot_key, plot_spec in spec.items():
            plot_submenu = view_menu.addMenu(plot_spec['title'])

            # 1. Action to Show/Hide the entire Plot panel
            show_plot_action = plot_submenu.addAction("Show Plot Panel")
            show_plot_action.setCheckable(True)
            show_plot_action.setChecked(True)
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
        # Create a vertical splitter so users can drag boundaries up and down
        self.plot_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)

        # Keep track of stretch factors to apply them to the splitter later
        stretch_factors = []

        for plot_name, plot_spec in spec.items():
            plot = pg.PlotWidget(title=plot_spec['title'])
            plot.showGrid(x=True, y=True, alpha=0.3)

            # Determine stretch factor
            stretch = plot_spec.get('stretch', default_stretch)
            stretch_factors.append(stretch)

            # CRITICAL: Add the plot directly to the splitter instead of self.layout
            self.plot_splitter.addWidget(plot)

            mouseX = plot_spec.get('mouse_enabled_x', True)
            mouseY = plot_spec.get('mouse_enabled_y', True)
            plot.setMouseEnabled(x=mouseX, y=mouseY)

            self.plots[plot_name] = {
                'plot': plot,
                'playhead': pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2)),
                'curves': {},
            }

            for curveName, curveSpec in plot_spec['curves'].items():
                self.plots[plot_name]['curves'][curveName] = {}

                if "BW" in curveSpec and curveSpec["BW"]:
                    self.plots[plot_name]['curves'][curveName]['has_bw'] = True

                    # 1. Define explicit bounding Curve Items (Not using .plot shortcut)
                    # We use a solid but completely transparent alpha channel pen
                    transparent_pen = pg.mkPen(color=(0, 0, 0, 0), width=1)

                    min_curve = pg.PlotCurveItem([], pen=transparent_pen)
                    max_curve = pg.PlotCurveItem([], pen=transparent_pen)

                    self.plots[plot_name]['curves'][curveName]['bw_curve_min'] = min_curve
                    self.plots[plot_name]['curves'][curveName]['bw_curve_max'] = max_curve

                    # 2. Build the bridging Fill Item
                    fill_item = pg.FillBetweenItem(
                        min_curve,
                        max_curve,
                        brush=pg.mkBrush(curveSpec['colour'])
                    )
                    self.plots[plot_name]['curves'][curveName]['fill_band'] = fill_item

                    # 3. CRITICAL: Add all 3 items explicitly to the plot viewport canvas
                    self.plots[plot_name]['plot'].addItem(min_curve)
                    self.plots[plot_name]['plot'].addItem(max_curve)
                    self.plots[plot_name]['plot'].addItem(fill_item)

                    # 4. Push the shaded area beneath markers and curves
                    fill_item.setZValue(-10)

                else:
                    self.plots[plot_name]['curves'][curveName]['curve'] = self.plots[plot_name]['plot'].plot(
                            [],
                            symbol="o",
                            pen=None,
                            symbolBrush=curveSpec['colour'],
                            symbolPen=None,
                            symbolSize=curveSpec['size']  # Sets the point size
                        )

                self.plots[plot_name]['curves'][curveName]['analysisResult'] = curveSpec['analysisResult']

            self.plots[plot_name]['plot'].addItem(self.plots[plot_name]['playhead'])

            # --- [NEW] Construct the Target Bands ---
            self.target_bands[plot_name] = {}
            for target_name, target_spec in plot_spec.get('targets', {}).items():
                # Generate horizontal linear region
                region = pg.LinearRegionItem(orientation='horizontal', movable=False, brush=target_spec['colour'])

                # Remove outline borders from pyqtgraph's linear region item
                for line in region.lines:
                    line.setPen(pg.mkPen(None))
                    line.setHoverPen(pg.mkPen(None))

                region.setZValue(-20)  # Make sure the band is deeply below annotations and lines
                region.setVisible(False)
                self.plots[plot_name]['plot'].addItem(region)

                self.target_bands[plot_name][target_name] = {
                    'item': region,
                    'min': 0.0,
                    'max': 1.0,
                    'enabled': False
                }

            if 'y_min' in plot_spec and 'y_max' in plot_spec:
                self.plots[plot_name]['plot'].setYRange(plot_spec['y_min'], plot_spec['y_max'], padding=0)

            if plot_spec['linkX'] is not None:
                targetPlot = self.plots[plot_spec['linkX']]['plot']
                self.plots[plot_name]['plot'].setXLink(targetPlot)

            self.plots[plot_name]['plot'].scene().sigMouseClicked.connect(
                lambda event, p_name=plot_name, p_title=plot_spec['title']:
                self.on_mouse_clicked(event, self.plots[p_name]['plot'], p_title)
            )

            # Apply the initial stretch sizes to the splitter items
        for idx, stretch in enumerate(stretch_factors):
            self.plot_splitter.setStretchFactor(idx, stretch)

            # Finally, add the entire splitter tool into your main layout
        self.layout.addWidget(self.plot_splitter)



    def browse_file(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Audio or Annotation File",
            "",
            "Supported Files (*.wav *.mp3 *.txt);;Audio Files (*.wav *.mp3);;Annotations (*.txt);;All Files (*)"
        )

        if file_name:
            if file_name.lower().endswith('.txt'):
                self.load_annotations_file(file_name)
            else:
                self.clear_annotations()  # Clear old annotations before loading a new raw audio file
                self.file_path = file_name
                self.file_loaded_signal.emit(file_name)
                self.selectAnalysisFile(file_name)

    def selectAnalysisFile(self, file_name):
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()

            if file_path.lower().endswith('.txt'):
                self.load_annotations_file(file_path)
            elif file_path.lower().endswith(('.wav', '.mp3')):
                self.file_path = file_path
                self.file_loaded_signal.emit(file_path)
                self.clear_annotations()
                self.selectAnalysisFile(file_path)

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

    def clear_annotations(self):
        """Removes all current annotations from the plots and memory."""
        for ann in self.annotations:
            marker = ann.get('marker')
            plot_name = ann.get('plot')
            if marker:
                self.plots[plot_name]['plot'].removeItem(marker)
        self.annotations.clear()

    def load_annotations_file(self, txt_file_path):
        """Parses an annotation file, loads the linked audio, and redraws markers."""
        try:
            active_audio_path, annotations, original_audio_path, fallback_audio_path = load_from_file(txt_file_path)

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
            self.selectAnalysisFile(active_audio_path)

            # 3. Parse annotations (skip headers: lines 0, 1, and 2)
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
        import shutil
        shutil.move(temp_wav_path, unique_wav_path)

        # 4. Set the app to use the new unique file
        self.file_path = unique_wav_path

        self.current_playback_time = 0
        self.update_playhead()

        # Perform analysis
        self.selectAnalysisFile(self.file_path)


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

    def append_live_data(self, latest_point):
        """Receives a single processed data point and appends it dynamically
        using the layout structures from update_plots.
        """
        current_time = latest_point["time"]

        # Use the structural mapping loop from update_plots
        for plot_name, plot in self.plots.items():
            for curve_name, curve in plot['curves'].items():
                result_key = curve['analysisResult']

                # If this quality metric isn't an attribute of our results object, skip it
                if not hasattr(self.analysis_results, result_key):
                    print("key not in results: " + result_key)
                    continue

                # Retrieve the specific SignalTimeSeries or BandwidthTimeSeries container
                data_container = getattr(self.analysis_results, result_key)

                # Ensure the specific point value exists in our incoming live stream packet
                if result_key in latest_point and latest_point[result_key] is not None:
                    new_y_val = latest_point[result_key]

                    # Append coordinates dynamically. Dataclasses guarantee they are numpy arrays.
                    data_container.x = np.append(data_container.x, current_time)
                    data_container.y = np.append(data_container.y, new_y_val)

    def handle_playback(self):
        if self.is_recording:
            print("Cannot start playback while recording.")
            return

        if not self.is_playing:
            self.seek_and_play()
            print("Playback started...")
        else:
            self.stop_playback()

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

    def stop_playback(self):
        self.is_playing = False
        self.playback_btn.setIcon(self.play_icon)  # FIXED: Ensured icon always goes to Play

        if hasattr(self, 'play_worker'):
            self.play_worker.stop_backend()

        self.timer.stop()

    def update_plots(self):
        for plot_name, plot_container in self.plots.items():
            for curve_name, curve in plot_container['curves'].items():
                # Ensure the required feature exists in our AudioFeatures result object
                if not hasattr(self.analysedAudioFeatures, curve['analysisResult']):
                    continue

                # Retrieve the data object (e.g., a SignalTimeSeries or BandwidthTimeSeries instance)
                data = getattr(self.analysedAudioFeatures, curve['analysisResult'])

                # Guard against unexpected types (mimicking your isinstance(data, list) check)
                if not hasattr(data, 'x') or not hasattr(data, 'y'):
                    continue

                if len(data.x) != len(data.y):
                    print(f"Mismatch in length for {plot_name}.{curve_name}")
                else:
                    if 'has_bw' in curve:
                        y_arr = np.array(data.y, dtype=float)
                        x_arr = np.array(data.x, dtype=float)

                        if isinstance(data, BandwidthTimeSeries) and len(data.BW) == len(y_arr):
                            bw_arr = np.array(data.BW, dtype=float)
                        else:
                            bw_arr = np.zeros_like(y_arr)

                        new_upper = y_arr + (bw_arr / 2)
                        new_lower = y_arr - (bw_arr / 2)

                        # Set data coordinates directly on the individual curves
                        curve['bw_curve_min'].setData(x=x_arr, y=new_lower)
                        curve['bw_curve_max'].setData(x=x_arr, y=new_upper)
                    else:
                        curve['curve'].setData(x=data.x, y=data.y)

        self.update_playhead()

    def update_playhead(self):
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time if self.is_playing else 0
            if self.current_playback_time > self.analysedAudioFeatures.length_seconds:
                self.stop_playback()
                self.current_playback_time = 0
        elif self.is_recording:
            # Calculate time based on raw bytes recorded
            # 16-bit Mono = 2 bytes per sample
            self.current_playback_time = self.audio_data.size() / (2 * self.sampling_rate)

            # Update the max length so playback works correctly later even with trailing silence
            self.analysedAudioFeatures.length_seconds = self.current_playback_time

        # Move the vertical lines to the new X position
        for plot_name, plot in self.plots.items():
            plot['playhead'].setValue(self.current_playback_time)

    def save_annotations(self):
        """Saves the self.annotations list of AnnotationMarker objects to a text file."""
        if not hasattr(self, 'annotations') or not self.annotations:
            QtWidgets.QMessageBox.warning(self, "No Annotations", "There are no annotations to save yet.")
            return

        # --- [NEW] Determine Default Save Path ---
        default_save_path = ""
        if hasattr(self, 'file_path') and self.file_path:
            # os.path.splitext splits "folder/file.wav" into ("folder/file", ".wav")
            base_path, _ = os.path.splitext(self.file_path)
            default_save_path = f"{base_path}.txt"

        # Open a save file dialog, using the default_save_path
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotations",
            default_save_path,  # Now points to the same folder and base filename
            "Text Files (*.txt);;All Files (*)"
        )

        if save_path and self.file_path is not None:
            try:
                save_to_file(save_path, self.annotations, self.file_path)
                print(f"Successfully saved annotations to: {save_path}")

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving:\n{str(e)}")

    def handle_symbol_size_change(self, value):
        """
        Called whenever the slider is moved.
        'value' will be an integer between 1 and 5.
        """

        for plot_name, plot in self.plots.items():
            # Loop through the visual items on the plot canvas
            for item in plot['plot'].getPlotItem().items:

                # 1. Handle standard ScatterPlotItems
                if isinstance(item, pg.ScatterPlotItem):
                    if isinstance(item, AnnotationMarker):
                        # Annotation markers should keep ther size
                        pass
                    else:
                        item.setSize(value)
                        if plot_name == "Weight":
                            item.setSize(value+1)


                # 2. Handle PlotDataItems (The helper function items)
                elif isinstance(item, pg.PlotDataItem):
                    # STEP A: Update the internal options dictionary so
                    # pyqtgraph remembers this size during clicks/pans/zooms
                    item.opts['symbolSize'] = value

                    # STEP B: Apply it immediately to the active rendering object
                    if item.scatter is not None:
                        item.scatter.setSize(value)
                        if plot_name == "Weight":
                            item.scatter.setSize(value + 1)

    def handle_reset_zoom(self):
        """Resets the zoom, applying fixed min/max spec boundaries where defined,

        and falling back to autoRange elsewhere.
        """
        for plot_name, plot_data in self.plots.items():
            plot_item = plot_data['plot']
            plot_spec = spec.get(plot_name, {})

            y_min = plot_spec.get('y_min')
            y_max = plot_spec.get('y_max')

            # Safely check if limits are explicitly provided (even if they are 0)
            if y_min is not None and y_max is not None:
                # Explicitly lock the Y-axis to your specs
                plot_item.setYRange(y_min, y_max, padding=0)

                # If X-axis should still auto-fit data while Y is locked:
                plot_item.enableAutoRange(axis=pg.ViewBox.XAxis)
            else:
                # Fallback to pure auto-scaling for both axes if no specs exist
                plot_item.autoRange()

    def handle_toggle_plot(self, plot_name: str, checked: bool):
        """Shows or hides an entire PlotWidget panel inside the QSplitter layout."""
        if plot_name in self.plots:
            self.plots[plot_name]['plot'].setVisible(checked)

    def handle_toggle_bandwidth(self, plot_name: str, curve_name: str, checked: bool):
        """Shows or hides background shaded bandwidth fills and boundary lines."""
        if plot_name in self.plots:
            curve_obj = self.plots[plot_name]['curves'].get(curve_name, {})
            if curve_obj.get('has_bw', False):
                if 'fill_band' in curve_obj:
                    curve_obj['fill_band'].setVisible(checked)
                if 'bw_curve_min' in curve_obj:
                    curve_obj['bw_curve_min'].setVisible(checked)
                if 'bw_curve_max' in curve_obj:
                    curve_obj['bw_curve_max'].setVisible(checked)

    def handle_toggle_pixels(self, plot_name: str, curve_name: str, checked: bool):
        """Shows or hides an individual pixel/scatter point curve series."""
        if plot_name in self.plots:
            curve_obj = self.plots[plot_name]['curves'].get(curve_name, {})
            if 'curve' in curve_obj:
                curve_obj['curve'].setVisible(checked)

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
            from PlotsSpec import default_stretch, spec
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
            # Reset Plot Panel Visibility
            self.handle_toggle_plot(plot_key, True)
            if plot_key in self.menu_toggle_actions['plots']:
                self.menu_toggle_actions['plots'][plot_key].setChecked(True)

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

    def open_targets_dialog(self):
        """Displays a dialog box allowing the user to configure visual targets."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Set Targets")
        dialog.setMinimumWidth(400)

        layout = QtWidgets.QVBoxLayout(dialog)
        form_layout = QtWidgets.QGridLayout()
        layout.addLayout(form_layout)

        # Headers
        form_layout.addWidget(QtWidgets.QLabel("<b>Enable</b>"), 0, 0)
        form_layout.addWidget(QtWidgets.QLabel("<b>Plot</b>"), 0, 1)
        form_layout.addWidget(QtWidgets.QLabel("<b>Target min</b>"), 0, 2)
        form_layout.addWidget(QtWidgets.QLabel("<b>Target max</b>"), 0, 3)

        row = 1
        gui_elements = []

        for plot_name, targets in self.target_bands.items():
            for target_name, target_data in targets.items():
                cb = QtWidgets.QCheckBox()
                cb.setChecked(target_data['enabled'])

                # Format the label nicely
                lbl_text = f"{plot_name} - {target_name}" if plot_name != target_name else target_name
                lbl = QtWidgets.QLabel(lbl_text)

                # --- PyQtGraph SpinBox Setup ---
                # Handles scientific notation natively and limits display to 2 decimals
                min_spin = pg.SpinBox(
                    value=target_data['min'],
                    bounds=[-100000, 100000],
                    decimals=2
                )

                max_spin = pg.SpinBox(
                    value=target_data['max'],
                    bounds=[-100000, 100000],
                    decimals=2
                )
                # -------------------------------

                form_layout.addWidget(cb, row, 0)
                form_layout.addWidget(lbl, row, 1)
                form_layout.addWidget(min_spin, row, 2)
                form_layout.addWidget(max_spin, row, 3)

                gui_elements.append({
                    'plot': plot_name,
                    'target': target_name,
                    'cb': cb,
                    'min': min_spin,
                    'max': max_spin
                })
                row += 1

        btn_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Apply && Close")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        def on_save():
            for elem in gui_elements:
                p_name = elem['plot']
                t_name = elem['target']
                t_data = self.target_bands[p_name][t_name]

                t_data['enabled'] = elem['cb'].isChecked()
                t_data['min'] = elem['min'].value()
                t_data['max'] = elem['max'].value()

                if t_data['enabled']:
                    t_data['item'].setRegion((t_data['min'], t_data['max']))
                    t_data['item'].setVisible(True)
                else:
                    t_data['item'].setVisible(False)

                val_min = elem['min'].value()
                val_max = elem['max'].value()

                if t_name == 'F1_Pitch':
                    self.audioFeatureExtractor.target_config.f1_pitch_min = val_min
                    self.audioFeatureExtractor.target_config.f1_pitch_max = val_max
                elif t_name == 'F2_Pitch':
                    self.audioFeatureExtractor.target_config.f2_pitch_min = val_min
                    self.audioFeatureExtractor.target_config.f2_pitch_max = val_max
                elif t_name == 'F3_Pitch':
                    self.audioFeatureExtractor.target_config.f3_pitch_min = val_min
                    self.audioFeatureExtractor.target_config.f3_pitch_max = val_max

            self.analysedAudioFeatures = self.audioFeatureExtractor.recalculate_size()
            self.update_plots()

            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()

    def export_targets(self):
        """Dumps dictionary rules to a standard JSON configured txt file."""
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Targets", "", "Text Files (*.txt);;JSON Files (*.json);;All Files (*)"
        )
        if save_path:
            try:
                data_to_save = {}
                for plot_name, targets in self.target_bands.items():
                    data_to_save[plot_name] = {}
                    for target_name, target_data in targets.items():
                        data_to_save[plot_name][target_name] = {
                            'enabled': target_data['enabled'],
                            'min': target_data['min'],
                            'max': target_data['max']
                        }
                with open(save_path, 'w') as f:
                    json.dump(data_to_save, f, indent=4)
                print(f"Successfully saved targets to: {save_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving targets:\n{str(e)}")

    def import_targets(self):
        """Opens a file dialog to dynamically select and load a JSON configuration file."""
        open_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Targets", "", "Text/JSON Files (*.txt *.json);;All Files (*)"
        )
        if open_path:
            self._load_targets_from_path(open_path)

    def _load_targets_from_path(self, open_path):
        """Shared logic to read and parse target profiles from a specific file path location."""
        try:
            with open(open_path, 'r') as f:
                loaded_data = json.load(f)

            for plot_name, targets in loaded_data.items():
                if plot_name in self.target_bands:
                    for target_name, target_data in targets.items():
                        if target_name in self.target_bands[plot_name]:
                            t_obj = self.target_bands[plot_name][target_name]
                            t_obj['enabled'] = target_data.get('enabled', False)
                            t_obj['min'] = target_data.get('min', 0.0)
                            t_obj['max'] = target_data.get('max', 1.0)

                            if t_obj['enabled']:
                                t_obj['item'].setRegion((t_obj['min'], t_obj['max']))
                                t_obj['item'].setVisible(True)
                            else:
                                t_obj['item'].setVisible(False)

            targets_f1 = loaded_data.get('F1_Pitch', {}).get('F1_Pitch', {})
            self.audioFeatureExtractor.target_config.f1_pitch_min = targets_f1.get('min', 0.0)
            self.audioFeatureExtractor.target_config.f1_pitch_max = targets_f1.get('max', 1.0)

            targets_f2 = loaded_data.get('F2_Pitch', {}).get('F2_Pitch', {})
            self.audioFeatureExtractor.target_config.f2_pitch_min = targets_f2.get('min', 0.0)
            self.audioFeatureExtractor.target_config.f2_pitch_max = targets_f2.get('max', 1.0)

            targets_f3 = loaded_data.get('F3_Pitch', {}).get('F3_Pitch', {})
            self.audioFeatureExtractor.target_config.f3_pitch_min = targets_f3.get('min', 0.0)
            self.audioFeatureExtractor.target_config.f3_pitch_max = targets_f3.get('max', 1.0)

            self.analysedAudioFeatures = self.audioFeatureExtractor.recalculate_size()
            self.update_plots()
            print(f"Successfully loaded targets from: {open_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error",
                                           f"An error occurred while loading targets:\n{str(e)}")

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

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())