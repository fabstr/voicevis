import queue
import sys
import tempfile
import wave

import numpy as np
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
import pyqtgraph as pg
import time
import miniaudio
import os
import qtawesome as qta

from AnalysisWorker import AnalysisWorker
from PlotsSpec import spec
from utils import save_to_file, load_from_file, save_to_temp_wav
from AnnotationMarker import AnnotationMarker
from AudioFeatureExtractor import AudioFeatureExtractor
from RealTimeAnalysisWorker import RealTimeAnalysisWorker



class LiveMultiPlotWidget(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()

        self.analysis_results = {}
        self.annotations = []
        self.plots = {}

        self.is_recording = False
        self.is_playing = False
        self.playback_start_time = 0.0

        self.current_playback_time = 0

        self.audio_device = None
        self.audio_stream = None
        self.file_path = None
        self.sampling_rate = 44100

        self.audioFeatureExtractor = AudioFeatureExtractor()

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
        layout = QtWidgets.QVBoxLayout(self)

        # --------------------------------------------------
        # 1. CONTROL BUTTONS SECTION
        # --------------------------------------------------
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
        top_buttons_layout.addStretch()
        layout.addLayout(top_buttons_layout)

        # --------------------------------------------------
        # 2. GRAPHS SECTION
        # --------------------------------------------------


        for plot_name, plot_spec in spec.items():
            plot = pg.PlotWidget(title=plot_spec['title'])
            plot.showGrid(x=True, y=True, alpha=0.3)
            layout.addWidget(plot, stretch=plot_spec['stretch'])

            mouseX = True
            if plot_spec['mouse_enabled_x'] is not None:
                mouseX = plot_spec['mouse_enabled_x']

            mouseY = True
            if plot_spec['mouse_enabled_y'] is not None:
                mouseY = plot_spec['mouse_enabled_y']

            plot.setMouseEnabled(x=mouseX, y=mouseY)

            self.plots[plot_name] = {
                'plot': plot,
                'playhead': pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2)),
                'curves': {},
            }
            for curveName, curveSpec in plot_spec['curves'].items():
                print(curveName)
                print(curveSpec)
                self.plots[plot_name]['curves'][curveName] = {
                    'curve':  self.plots[plot_name]['plot'].plot(
                        [],
                        pen=None,
                        symbol=curveSpec['symbol'],
                        symbolSize=curveSpec['symbolSize'],
                        symbolBrush=curveSpec['symbolBrush']
                    ),
                    'analysisResult': curveSpec['analysisResult']
                }
            self.plots[plot_name]['plot'].addItem(self.plots[plot_name]['playhead'])

            if plot_spec['linkX'] is not None:
                targetPlot = self.plots[plot_spec['linkX']]['plot']
                self.plots[plot_name]['plot'].setXLink(targetPlot)

            self.plots[plot_name]['plot'].scene().sigMouseClicked.connect(
                lambda event: self.on_mouse_clicked(event, self.plots[plot_name]['plot'], "plot_name"))

        layout.addSpacing(10)

        # --------------------------------------------------
        # 3. FILE BROWSER SECTION (Moved to bottom)
        # --------------------------------------------------
        file_layout = QtWidgets.QHBoxLayout()
        self.file_path_display = QtWidgets.QLineEdit()
        self.file_path_display.setPlaceholderText("Select or drag & drop a file to analyze...")
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setMinimumHeight(35)
        file_layout.addWidget(self.file_path_display)

        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.setMinimumHeight(35)
        self.browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(self.browse_button)

        layout.addLayout(file_layout)

        self.timer = QtCore.QTimer()
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.update_plots)


    # --- File Handling Methods ---

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
                self.file_path_display.setText(file_name)
                self.file_path = file_name
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
        self.analysis_results = results
        self.current_playback_time = 0
        self.update_plots()

    def on_analysis_error(self, error_msg):
        """Called automatically if the worker thread encounters an error."""
        QtWidgets.QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis:\n{error_msg}")

    # --- Drag & Drop Methods ---

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
                self.file_path_display.setText(file_path)
                self.file_path = file_path
                self.clear_annotations()
                self.selectAnalysisFile(file_path)
            else:
                self.file_path_display.setText("Error: Unsupported file format.")

    def keyPressEvent(self, event):
        # Check if the pressed key is the Spacebar
        if event.key() == QtCore.Qt.Key.Key_Space:
            if self.is_playing:
                # --- PAUSE AUDIO ---
                self.is_playing = False
                if self.audio_device and self.audio_device.running:
                    self.audio_device.stop()
            else:
                if self.file_path:
                    self.playback_btn.setIcon(self.pause_icon)
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
                # if plot_name == "Pitch":
                #     self.pitch_plot.removeItem(marker)
                # elif plot_name == "Formants":
                #     self.formants_plot.removeItem(marker)
                # elif plot_name == "Weight":
                #     self.weight_plot.removeItem(marker)

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
            self.file_path_display.setText(active_audio_path)
            self.file_path = active_audio_path
            self.selectAnalysisFile(active_audio_path)

            # 3. Parse annotations (skip headers: lines 0, 1, and 2)
            for annotation in annotations:
                    # Determine which plot widget to draw on
                    plot_widget = None
                    if annotation['plot'] == "Pitch":
                        plot_widget = self.pitch_plot
                    elif annotation['plot'] == "Formants":
                        plot_widget = self.formants_plot
                    elif annotation['plot'] == "Weight":
                        plot_widget = self.weight_plot

                    # Recreate the marker and save it to memory
                    if plot_widget:
                        marker = AnnotationMarker(annotation['time'], annotation['y'], annotation['text'], annotation['plot'], plot_widget, self)
                        plot_widget.addItem(marker)
                        annotation['marker'] = marker
                        self.annotations.append(annotation)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error",
                                           f"An error occurred while loading annotations:\n{str(e)}")
    # --- UI Control Methods ---

    def handle_record_stop(self):
        if self.is_playing:
            self.stop_playback()

        self.is_recording = not self.is_recording

        if self.is_recording:
            # --- UI Updates ---
            self.record_stop_btn.setIcon(self.stop_icon)
            self.record_stop_btn.setToolTip("Stop Recording")  # Use tooltip instead of text

            # 1. Initialize self.analysis_results with empty arrays
            self.analysis_results = {
                "timepoints": [], "pitch": [], "F1": [], "F2": [], "F3": [],
                "F1_ratio": [], "A3_ratio": [], "slope_0_500": [], "slope_500_1500": [],
                "sample_rate": self.sampling_rate, "length_seconds": 0.0
            }

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



        else:
            # --- UI Updates ---
            self.record_stop_btn.setIcon(self.record_icon)
            self.record_stop_btn.setToolTip("Record")  # Use tooltip instead of text
            # Make sure border-radius matches the new 40x40 size (20px)
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
                # This flags the loop to stop, but our new logic lets it empty the queue first
                self.rt_worker.stop()
                # wait() safely blocks the main thread for a tiny fraction of a second
                # until the worker finishes its last chunk
                self.rt_worker.wait()

                # --- Save to WAV for Playback ---
            pcm_bytes = self.audio_data.data()
            temp_wav_path = save_to_temp_wav(pcm_bytes, self.sampling_rate)

            self.file_path = temp_wav_path
            self.file_path_display.setText(self.file_path)

            self.current_playback_time = 0
            self.update_playhead()

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
        """Receives a single processed data point and appends it."""
        self.analysis_results["timepoints"].append(latest_point["time"])
        self.analysis_results["pitch"].append(latest_point["pitch"])
        self.analysis_results["F1"].append(latest_point["F1"])
        self.analysis_results["F2"].append(latest_point["F2"])
        self.analysis_results["F3"].append(latest_point["F3"])

        f1_val = latest_point["F1"] if latest_point["F1"] > 0 else 1.0
        self.analysis_results["F1_ratio"].append(latest_point["F2"] / f1_val)
        self.analysis_results["A3_ratio"].append(latest_point["F3"] / f1_val)

        self.analysis_results["slope_0_500"].append(latest_point["slope_0_500"])
        self.analysis_results["slope_500_1500"].append(latest_point["slope_500_1500"])


    def handle_playback(self):
        if self.is_recording:
            print("Cannot start playback while recording.")
            return

        self.is_playing = not self.is_playing

        if self.is_playing:
            # Change icon to Pause
            self.playback_btn.setIcon(self.pause_icon)

            self.seek_and_play()
            print("Playback started...")
        else:
            self.stop_playback()

    def stop_playback(self):
        self.is_playing = False

        # Swap back to Play icon
        self.playback_btn.setIcon(self.play_icon)

        if self.audio_device is not None:
            self.audio_device.stop()
        self.timer.stop()
        print("Playback paused.")

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
        # Pause audio automatically
        if self.is_playing:
            self.is_playing = False
            if self.audio_device and self.audio_device.running:
                self.audio_device.stop()
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
        # Prevent seeking to negative times if the user clicks out of bounds
        target_time = max(0.0, self.current_playback_time)

        # Calculate the exact frame based on the audio's sample rate
        seek_frame = int(target_time * self.analysis_results['sample_rate'])

        # Stop existing playback
        if self.audio_device and self.audio_device.running:
            self.audio_device.stop()

        # Start a new miniaudio stream, passing in the offset
        self.audio_stream = miniaudio.stream_file(
            self.file_path,
            seek_frame=seek_frame
        )
        self.audio_device = miniaudio.PlaybackDevice()
        self.audio_device.start(self.audio_stream)

        # Offset the master timer by the target time so the playhead continues smoothly
        self.playback_start_time = time.time() - target_time
        self.is_playing = True

        for plot_name, plot in self.plots.items():
            plot['playhead'].setValue(target_time)

        self.timer.start()

    def update_plots(self):
        # Prevent errors if update_plots is called before data is loaded
        if not self.analysis_results:
            return

        for plot_name, plot in self.plots.items():
            for curve_name, curve in plot['curves'].items():
                data = self.analysis_results[curve['analysisResult']]
                self.plots[plot_name]['curves'][curve_name]['curve'].setData(x=self.analysis_results['timepoints'], y=data)

        self.update_playhead()


    def update_playhead(self):
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time if self.is_playing else 0
            if self.current_playback_time > self.analysis_results['length_seconds']:
                self.stop_playback()
                self.current_playback_time = 0
        elif self.is_recording:
            # Calculate time based on raw bytes recorded
            # 16-bit Mono = 2 bytes per sample
            self.current_playback_time = self.audio_data.size() / (2 * self.sampling_rate)

            # Update the max length so playback works correctly later even with trailing silence
            self.analysis_results['length_seconds'] = self.current_playback_time

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


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())