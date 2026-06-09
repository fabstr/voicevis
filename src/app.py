import sys
import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg


class LiveMultiPlotWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        # Window setup
        self.setWindowTitle("Real-Time Voice Analysis")
        self.resize(800, 800)

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
        layout.addWidget(self.pitch_plot)

        self.pitch_data = np.zeros(100)
        self.pitch_curve = self.pitch_plot.plot(self.pitch_data, pen=pg.mkPen('c', width=2))  # Cyan

        # --------------------------------------------------
        # 2. FORMANTS PLOT (F1, F2, F3)
        # --------------------------------------------------
        self.formants_plot = pg.PlotWidget(title="Formants")
        self.formants_plot.showGrid(x=True, y=True, alpha=0.3)
        self.formants_plot.addLegend()  # Enable legend to identify F1, F2, F3
        layout.addWidget(self.formants_plot)

        self.f1_data = np.zeros(100)
        self.f2_data = np.zeros(100)
        self.f3_data = np.zeros(100)

        # Assign different colors and names for the legend
        self.f1_curve = self.formants_plot.plot(self.f1_data, pen=pg.mkPen('r', width=2), name="F1")  # Red
        self.f2_curve = self.formants_plot.plot(self.f2_data, pen=pg.mkPen('g', width=2), name="F2")  # Green
        self.f3_curve = self.formants_plot.plot(self.f3_data, pen=pg.mkPen('y', width=2), name="F3")  # Yellow

        # --------------------------------------------------
        # 3. WEIGHT PLOT
        # --------------------------------------------------
        self.weight_plot = pg.PlotWidget(title="Weight")
        self.weight_plot.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.weight_plot)

        self.weight_data = np.zeros(100)
        self.weight_curve = self.weight_plot.plot(self.weight_data, pen=pg.mkPen('m', width=2))  # Magenta

        # --------------------------------------------------
        # TIMER SETUP
        # --------------------------------------------------
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
            "Audio Files (*.wav *.mp3 *.flac);;All Files (*)"
        )

        # If the user selected a file (didn't hit cancel), update the text box
        if file_name:
            self.file_path_display.setText(file_name)
            # You could also add logic here to reset your plots or stop/start the timer
            # based on the newly loaded file.

    def update_plots(self):
        # Update Pitch (Centered around 120 for visual clarity)
        self.pitch_data = np.roll(self.pitch_data, -1)
        self.pitch_data[-1] = np.random.normal(120, 5)
        self.pitch_curve.setData(self.pitch_data)

        # Update Formants (Giving them different base values so they separate on the graph)
        self.f1_data = np.roll(self.f1_data, -1)
        self.f1_data[-1] = np.random.normal(500, 20)
        self.f1_curve.setData(self.f1_data)

        self.f2_data = np.roll(self.f2_data, -1)
        self.f2_data[-1] = np.random.normal(1500, 40)
        self.f2_curve.setData(self.f2_data)

        self.f3_data = np.roll(self.f3_data, -1)
        self.f3_data[-1] = np.random.normal(2500, 50)
        self.f3_curve.setData(self.f3_data)

        # Update Weight (Centered around 1.0)
        self.weight_data = np.roll(self.weight_data, -1)
        self.weight_data[-1] = np.random.normal(1.0, 0.1)
        self.weight_curve.setData(self.weight_data)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())