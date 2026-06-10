import sys
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import time
import miniaudio

from AnnotationMarker import AnnotationMarker
# Ensure this module is in the same directory or in your Python path
from AudioFeatureExtractor import AudioFeatureExtractor


class LiveMultiPlotWidget(QtWidgets.QWidget):

    analysis_results = {}
    annotations = []

    is_recording = False
    is_playing = False
    playback_start_time = 0.0

    current_playback_time = 0

    audio_device = None
    audio_stream = None
    file_path = None

    def __init__(self):
        super().__init__()

        self.audioFeatureExtractor = AudioFeatureExtractor()

        # Window Setup
        self.setWindowTitle("VoiceVis")
        self.resize(800, 800)

        self.setAcceptDrops(True)

        # Main vertical layout
        layout = QtWidgets.QVBoxLayout(self)

        # --------------------------------------------------
        # 1. GRAPHS SECTION
        # --------------------------------------------------

        # Plot 1: Pitch
        self.pitch_plot = pg.PlotWidget(title="Pitch (Hz)")
        self.pitch_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pitch_plot.setLabel('bottom', "Time", units="s")
        layout.addWidget(self.pitch_plot, stretch=3)

        self.pitch_curve = self.pitch_plot.plot([], pen=None, symbol='o', symbolSize=6, symbolBrush='c')  # Cyan
        self.f1_ratio_curve = self.pitch_plot.plot([], pen=None, symbol='o', symbolSize=6,
                                                   symbolBrush='y')  # Yellow
        self.a3_ratio_curve = self.pitch_plot.plot([], pen=None, symbol='o', symbolSize=6,
                                                   symbolBrush='r')  # Red
        # Add this after setting up self.pitch_plot
        self.playhead_pitch = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2))
        self.pitch_plot.addItem(self.playhead_pitch)



        # Plot 2: Formants (F1, F2, F3)
        self.formants_plot = pg.PlotWidget(title="Formants (Hz)")
        self.formants_plot.showGrid(x=True, y=True, alpha=0.3)
        self.formants_plot.addLegend()
        self.formants_plot.setLabel('bottom', "Time", units="s")
        layout.addWidget(self.formants_plot, stretch=2)

        self.f1_curve = self.formants_plot.plot([], pen=None, symbol='o', symbolSize=5, symbolBrush='r',
                                                name="F1")  # Red
        self.f2_curve = self.formants_plot.plot([], pen=None, symbol='t', symbolSize=5, symbolBrush='g',
                                                name="F2")  # Green
        self.f3_curve = self.formants_plot.plot([], pen=None, symbol='s', symbolSize=5, symbolBrush='y',
                                                name="F3")  # Yellow
        # Add this after setting up self.formants_plot
        self.playhead_formants = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2))
        self.formants_plot.addItem(self.playhead_formants)

        # Plot 3: Weight
        self.weight_plot = pg.PlotWidget(title="Weight")
        self.weight_plot.showGrid(x=True, y=True, alpha=0.3)
        self.weight_plot.setLabel('bottom', "Time", units="s")
        layout.addWidget(self.weight_plot, stretch=2)

        self.weight_curve_0_500 = self.weight_plot.plot([], pen=None, symbol='o', symbolSize=6,
                                                        symbolBrush='m')  # Magenta
        self.weight_curve_500_1500 = self.weight_plot.plot([], pen=None, symbol='o',
                                                           symbolSize=6, symbolBrush='w')  # White

        # Add this after setting up self.weight_plot
        self.playhead_weight = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2))
        self.weight_plot.addItem(self.playhead_weight)

        # Synchronize X-Axes
        self.formants_plot.setXLink(self.pitch_plot)
        self.weight_plot.setXLink(self.pitch_plot)

        # Add spacing between graphs and controls
        layout.addSpacing(10)

        # --------------------------------------------------
        # 2. FILE BROWSER SECTION
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

        # --------------------------------------------------
        # 3. CONTROL BUTTONS SECTION
        # --------------------------------------------------
        bottom_buttons_layout = QtWidgets.QHBoxLayout()

        self.record_stop_btn = QtWidgets.QPushButton("Record")
        self.record_stop_btn.setMinimumHeight(50)
        self.record_stop_btn.clicked.connect(self.handle_record_stop)

        self.playback_btn = QtWidgets.QPushButton("Start Playback")
        self.playback_btn.setMinimumHeight(50)
        self.playback_btn.clicked.connect(self.handle_playback)

        # [NEW] Add the Save button
        self.save_btn = QtWidgets.QPushButton("Save Annotations")
        self.save_btn.setMinimumHeight(50)
        self.save_btn.clicked.connect(self.save_annotations)

        bottom_buttons_layout.addWidget(self.record_stop_btn, stretch=1)
        bottom_buttons_layout.addWidget(self.playback_btn, stretch=1)
        bottom_buttons_layout.addWidget(self.save_btn, stretch=1)

        layout.addLayout(bottom_buttons_layout)


        self.pitch_plot.scene().sigMouseClicked.connect(
            lambda event: self.on_mouse_clicked(event, self.pitch_plot, "Pitch")
        )
        self.formants_plot.scene().sigMouseClicked.connect(
            lambda event: self.on_mouse_clicked(event, self.formants_plot, "Formants")
        )
        self.weight_plot.scene().sigMouseClicked.connect(
            lambda event: self.on_mouse_clicked(event, self.weight_plot, "Weight")
        )

        # --------------------------------------------------
        # TIMER SETUP
        # --------------------------------------------------
        self.timer = QtCore.QTimer()
        self.timer.setInterval(30)  # ~33 FPS
        self.timer.timeout.connect(self.update_plots)
        # Note: Timer is no longer auto-started here. It is triggered by the Playback button.

    # --- File Handling Methods ---

    def browse_file(self):
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.wav *.mp3);;All Files (*)"
        )

        if file_name:
            self.file_path_display.setText(file_name)
            self.file_path = file_name
            self.selectAnalysisFile(file_name)

    def selectAnalysisFile(self, file_name):
        # 1. Setup and show the loading dialog
        loading_dialog = QtWidgets.QProgressDialog("Analyzing audio file...", None, 0, 0, self)
        loading_dialog.setWindowTitle("Please Wait")
        loading_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        loading_dialog.setMinimumDuration(0)  # Ensure it shows immediately
        loading_dialog.show()

        # Force Qt to draw the dialog before the blocking computation begins
        QtWidgets.QApplication.processEvents()

        try:
            self.analysis_results = self.audioFeatureExtractor.analyze(file_name)
            self.current_playback_time = 0
            self.update_plots()

        finally:
            # 3. Ensure the dialog closes even if an error occurs during analysis
            loading_dialog.close()

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
            if file_path.lower().endswith(('.wav', '.mp3')):
                self.file_path_display.setText(file_path)
                self.file_path = file_path
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

               # # Calculate and save exactly where we paused
               # self.paused_time = time.time() - self.playback_start_time
           # else:
                # --- RESUME AUDIO ---
                # Only attempt to play if a file has actually been loaded
              #  if self.file_path:
                  #  self.seek_and_play(self.paused_time)
            else:
                if self.file_path:
                    self.seek_and_play()

            event.accept()  # Tell Qt we handled this key press
        else:
            # Pass any other keys (like arrows, etc.) back to the standard Qt handler
            super().keyPressEvent(event)


    # --- UI Control Methods ---

    def handle_record_stop(self):
        self.is_recording = not self.is_recording

        if self.is_recording:
            self.record_stop_btn.setText("Stop Recording")
            self.record_stop_btn.setStyleSheet("background-color: #ffcccc;")
            print("Recording started...")
        else:
            self.record_stop_btn.setText("Record")
            self.record_stop_btn.setStyleSheet("")
            print("Recording stopped.")

    def handle_playback(self):
        if self.is_recording:
            print("Cannot start playback while recording.")
            return

        self.is_playing = not self.is_playing

        if self.is_playing:
            self.playback_btn.setText("Pause Playback")
            self.playback_btn.setStyleSheet("background-color: #ccffcc;")
            self.seek_and_play()
            print("Playback started...")
        else:
            self.stop_playback()

    def stop_playback(self):
        self.playback_btn.setText("Start Playback")
        self.playback_btn.setStyleSheet("")
        if self.audio_device is not None:
            self.audio_device.stop()
        self.timer.stop()  # Stop the plot updating timer
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

        # Instantly snap the playhead markers to the new click position
        self.playhead_pitch.setValue(target_time)
        self.playhead_formants.setValue(target_time)
        self.playhead_weight.setValue(target_time)

        self.timer.start()

    def update_plots(self):
        # Prevent errors if update_plots is called before data is loaded
        if not self.analysis_results:
            return

        self.pitch_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['pitch'])
        self.f1_ratio_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['F1_ratio'])
        self.a3_ratio_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['A3_ratio'])
        self.f1_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['F1'])
        self.f2_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['F2'])
        self.f3_curve.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['F3'])
        self.weight_curve_0_500.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['slope_0_500'])
        self.weight_curve_500_1500.setData(x=self.analysis_results['timepoints'], y=self.analysis_results['slope_500_1500'])

        self.update_playhead()


    def update_playhead(self):
        if self.is_playing:
            self.current_playback_time = time.time() - self.playback_start_time if self.is_playing else 0
            if self.current_playback_time > self.analysis_results['length_seconds']:
                self.stop_playback()
                self.current_playback_time = 0

        # Move the vertical lines to the new X position
        self.playhead_pitch.setValue(self.current_playback_time)
        self.playhead_formants.setValue(self.current_playback_time)
        self.playhead_weight.setValue(self.current_playback_time)


    def save_annotations(self):
        """Saves the self.annotations list of AnnotationMarker objects to a text file."""
        if not hasattr(self, 'annotations') or not self.annotations:
            QtWidgets.QMessageBox.warning(self, "No Annotations", "There are no annotations to save yet.")
            return

        # Open a save file dialog
        save_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Annotations",
            "",
            "Text Files (*.txt);;All Files (*)"
        )

        if save_path:
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    # Write header
                    source_file = getattr(self, 'file_path', 'No file loaded')
                    f.write(f"Source: {source_file}\n")
                    f.write("-" * 80 + "\n")

                    # Column headers
                    f.write("Time\tFeature\tY-Value\tText\n")

                    for annotation in self.annotations:
                        try:
                            # Extract attributes directly from your AnnotationMarker class
                            time_val = annotation.get('time', 0.0)
                            y_val = annotation.get('y', 0.0)
                            text_val = annotation.get('text', '')
                            plot_name = annotation.get('plot', '')

                            # Format time to 2 decimals
                            formatted_time = f"{float(time_val):.2f}"

                            # Format y to 4 figures (using .4g for 4 significant figures)
                            formatted_y = f"{float(y_val):.4g}"

                            # Write to file separated by tabs
                            f.write(f"{formatted_time}\t{plot_name}\t{formatted_y}\t{text_val}\n")

                        except (ValueError, TypeError, AttributeError) as item_error:
                            # Skip this specific marker if it's somehow malformed,
                            # but continue processing the rest.
                            print(f"Skipping malformed annotation marker: {item_error}")

                print(f"Successfully saved annotations to: {save_path}")

            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Save Error", f"An error occurred while saving:\n{str(e)}")


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())