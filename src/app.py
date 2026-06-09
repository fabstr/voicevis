import sys
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import time
import miniaudio

# Ensure this module is in the same directory or in your Python path
from AudioFeatureExtractor import AudioFeatureExtractor


class LiveMultiPlotWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.audioFeatureExtractor = AudioFeatureExtractor()

        # --- Data Variables ---
        self.timepoints = []
        self.pitch = []
        self.F1_ratio = []
        self.A3_ratio = []
        self.F1 = []
        self.F2 = []
        self.F3 = []
        self.weight_data_0_500 = []
        self.weight_data_500_1500 = []



        # --- State Variables ---
        self.is_recording = False
        self.is_playing = False
        self.playback_start_time = 0.0

        # Keep references to prevent garbage collection
        self.audio_device = None
        self.audio_stream = None
        self.file_path = None

        # --- Window Setup ---
        self.setWindowTitle("Real-Time Voice Analysis Dashboard")
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

        self.pitch_curve = self.pitch_plot.plot(self.pitch, pen=None, symbol='o', symbolSize=6, symbolBrush='c')  # Cyan
        self.f1_ratio_curve = self.pitch_plot.plot(self.F1_ratio, pen=None, symbol='o', symbolSize=6,
                                                   symbolBrush='y')  # Yellow
        self.a3_ratio_curve = self.pitch_plot.plot(self.A3_ratio, pen=None, symbol='o', symbolSize=6,
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

        self.f1_curve = self.formants_plot.plot(self.F1, pen=None, symbol='o', symbolSize=5, symbolBrush='r',
                                                name="F1")  # Red
        self.f2_curve = self.formants_plot.plot(self.F2, pen=None, symbol='t', symbolSize=5, symbolBrush='g',
                                                name="F2")  # Green
        self.f3_curve = self.formants_plot.plot(self.F3, pen=None, symbol='s', symbolSize=5, symbolBrush='y',
                                                name="F3")  # Yellow
        # Add this after setting up self.formants_plot
        self.playhead_formants = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=2))
        self.formants_plot.addItem(self.playhead_formants)

        # Plot 3: Weight
        self.weight_plot = pg.PlotWidget(title="Weight")
        self.weight_plot.showGrid(x=True, y=True, alpha=0.3)
        self.weight_plot.setLabel('bottom', "Time", units="s")
        layout.addWidget(self.weight_plot, stretch=2)

        self.weight_curve_0_500 = self.weight_plot.plot(self.weight_data_0_500, pen=None, symbol='o', symbolSize=6,
                                                        symbolBrush='m')  # Magenta
        self.weight_curve_500_1500 = self.weight_plot.plot(self.weight_data_500_1500, pen=None, symbol='o',
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

        bottom_buttons_layout.addWidget(self.record_stop_btn, stretch=1)
        bottom_buttons_layout.addWidget(self.playback_btn, stretch=2)

        layout.addLayout(bottom_buttons_layout)

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
            # 2. Perform the heavy computation
            audio_features = self.audioFeatureExtractor.analyze(file_name)

            self.timepoints = audio_features['timepoints']
            self.pitch = audio_features['pitch']
            self.F1_ratio = audio_features['F1_ratio']
            self.A3_ratio = audio_features['A3_ratio']
            self.F1 = audio_features['F1']
            self.F2 = audio_features['F2']
            self.F3 = audio_features['F3']
            self.weight_data_0_500 = audio_features['slope_0_500']
            self.weight_data_500_1500 = audio_features['slope_500_1500']

            # Update plots immediately when a file is loaded
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

            self.audio_stream = miniaudio.stream_file(self.file_path)
            self.audio_device = miniaudio.PlaybackDevice()
            self.audio_device.start(self.audio_stream)

            # [NEW] Mark the start time and set state
            self.playback_start_time = time.time()
            self.is_playing = True

            self.timer.start()  # Start the plot updating timer



            print("Playback started...")
        else:
            self.playback_btn.setText("Start Playback")
            self.playback_btn.setStyleSheet("")
            self.audio_device.stop()
            self.timer.stop()  # Stop the plot updating timer
            print("Playback paused.")

    # --- Plotting Method ---

    def update_plots(self):
        # Prevent errors if update_plots is called before data is loaded
        if not self.timepoints:
            return

        self.pitch_curve.setData(x=self.timepoints, y=self.pitch)
        self.f1_ratio_curve.setData(x=self.timepoints, y=self.F1_ratio)
        self.a3_ratio_curve.setData(x=self.timepoints, y=self.A3_ratio)
        self.f1_curve.setData(x=self.timepoints, y=self.F1)
        self.f2_curve.setData(x=self.timepoints, y=self.F2)
        self.f3_curve.setData(x=self.timepoints, y=self.F3)
        self.weight_curve_0_500.setData(x=self.timepoints, y=self.weight_data_0_500)
        self.weight_curve_500_1500.setData(x=self.timepoints, y=self.weight_data_500_1500)

        # Calculate elapsed time in seconds
        current_playback_time = time.time() - self.playback_start_time

        # Move the vertical lines to the new X position
        self.playhead_pitch.setValue(current_playback_time)
        self.playhead_formants.setValue(current_playback_time)
        self.playhead_weight.setValue(current_playback_time)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())