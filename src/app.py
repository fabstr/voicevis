import sys
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

from AudioFeatureExtractor import AudioFeatureExtractor

from os import path

class LiveMultiPlotWidget(QtWidgets.QWidget):

    timepoints = []
    pitch = []
    F1_ratio = []
    A3_ratio = []
    F1 = []
    F2 = []
    F3 = []
    weight_data_0_500 = []
    weight_data_500_1500 = []

    def __init__(self):
        super().__init__()

        self.audioFeatureExtractor = AudioFeatureExtractor()

        # Window setup
        self.setWindowTitle("Real-Time Voice Analysis")
        self.resize(800, 800)

        self.setAcceptDrops(True)

        # Main vertical layout
        layout = QtWidgets.QVBoxLayout(self)

        # --------------------------------------------------
        # FILE BROWSER SECTION
        # --------------------------------------------------
        file_layout = QtWidgets.QHBoxLayout()

        # Text box to show the selected file path
        self.file_path_display = QtWidgets.QLineEdit()
        self.file_path_display.setPlaceholderText("Select a file to analyze...")
        self.file_path_display.setReadOnly(True)  # Prevent manual typing, force browsing
        file_layout.addWidget(self.file_path_display)

        # Browse button
        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(self.browse_button)

        # Add the horizontal file layout to the top of the main vertical layout
        layout.addLayout(file_layout)

        # --------------------------------------------------
        # 1. PITCH PLOT
        # --------------------------------------------------
        self.pitch_plot = pg.PlotWidget(title="Pitch (Hz)")
        self.pitch_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pitch_plot.setLabel('bottom', "Time", units="s")  # [NEW] X-axis label
        layout.addWidget(self.pitch_plot)

        self.pitch_curve = self.pitch_plot.plot(self.pitch, pen=None, symbol='o', symbolSize=6, symbolBrush='c')  # Cyan
        self.f1_ratio_curve = self.pitch_plot.plot(self.F1_ratio, pen=None, symbol='o', symbolSize=6, symbolBrush='y')  # Yellow
        self.a3_ratio_curve = self.pitch_plot.plot(self.A3_ratio, pen=None, symbol='o', symbolSize=6, symbolBrush='r')  # Red


        # --------------------------------------------------
        # 2. FORMANTS PLOT (F1, F2, F3)
        # --------------------------------------------------
        self.formants_plot = pg.PlotWidget(title="Formants (Hz)")
        self.formants_plot.showGrid(x=True, y=True, alpha=0.3)
        self.formants_plot.addLegend()  # Enable legend to identify F1, F2, F3
        self.formants_plot.setLabel('bottom', "Time", units="s")  # [NEW] X-axis label
        layout.addWidget(self.formants_plot)



        # Assign different colors and names for the legend
        self.f1_curve = self.formants_plot.plot(self.F1, pen=None, symbol='o', symbolSize=5, symbolBrush='r', name="F1")  # Red
        self.f2_curve = self.formants_plot.plot(self.F2, pen=None, symbol='t', symbolSize=5, symbolBrush='g', name="F2")  # Green
        self.f3_curve = self.formants_plot.plot(self.F3, pen=None, symbol='s', symbolSize=5, symbolBrush='y', name="F3")  # Yellow

        # --------------------------------------------------
        # 3. WEIGHT PLOT
        # --------------------------------------------------
        self.weight_plot = pg.PlotWidget(title="Weight")
        self.weight_plot.showGrid(x=True, y=True, alpha=0.3)
        self.weight_plot.setLabel('bottom', "Time", units="s")  # [NEW] X-axis label
        layout.addWidget(self.weight_plot)

        self.weight_curve_0_500 = self.weight_plot.plot(self.weight_data_0_500, pen=None, symbol='o', symbolSize=6, symbolBrush='m')  # Magenta
        self.weight_curve_500_1500 = self.weight_plot.plot(self.weight_data_500_1500, pen=None, symbol='o', symbolSize=6, symbolBrush='w')  # white (?)

        # --------------------------------------------------
        # [NEW] SYNCHRONIZE X-AXES
        # --------------------------------------------------
        # Link the X-axis of Formants and Weight to the Pitch plot
        self.formants_plot.setXLink(self.pitch_plot)
        self.weight_plot.setXLink(self.pitch_plot)

        # --------------------------------------------------
        # TIMER SETUP
        # -------------------------------------------------->
        self.timer = QtCore.QTimer()
        self.timer.setInterval(30)  # ~33 FPS
        self.timer.timeout.connect(self.update_plots)
        self.timer.start()

    def browse_file(self):
        # Open a file dialog. The filter limits it to specific file types if desired.
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.wav *.mp3);;All Files (*)"
        )

        # If the user selected a file (didn't hit cancel), update the text box
        if file_name:
            self.file_path_display.setText(file_name)
            self.selectAnalysisFile(file_name)

    def selectAnalysisFile(self, file_name):
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

        self.update_plots()

    def update_plots(self):
            self.pitch_curve.setData(x=self.timepoints, y=self.pitch)
            self.f1_ratio_curve.setData(x=self.timepoints, y=self.F1_ratio)
            self.a3_ratio_curve.setData(x=self.timepoints, y=self.A3_ratio)
            self.f1_curve.setData(x=self.timepoints, y=self.F1)
            self.f2_curve.setData(x=self.timepoints, y=self.F2)
            self.f3_curve.setData(x=self.timepoints, y=self.F3)
            self.weight_curve_0_500.setData(x=self.timepoints, y=self.weight_data_0_500)
            self.weight_curve_500_1500.setData(x=self.timepoints, y=self.weight_data_500_1500)

    def dragEnterEvent(self, event):
        # Check if the dragged object contains URLs (which represent file paths)
        if event.mimeData().hasUrls():
            event.accept()  # Tell the OS we accept this type of drop
        else:
            event.ignore()

    def dropEvent(self, event):
        # Extract the list of URLs from the drop event
        urls = event.mimeData().urls()
        if urls:
            # Get the local file path of the first dropped item
            file_path = urls[0].toLocalFile()

            # Optional: You can filter by extension here just like in the browse dialog
            if file_path.lower().endswith(('.wav')) or file_path.lower().endswith(('.mp3')):
                self.file_path_display.setText(file_path)
                self.selectAnalysisFile(file_path)
                self.update_plots()
            else:
                self.file_path_display.setText("Error: Unsupported file format.")

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())