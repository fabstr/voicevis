from PyQt6 import QtCore


class AnalysisWorker(QtCore.QThread):
    # Signals to communicate back to the main GUI thread safely
    result_ready = QtCore.pyqtSignal(dict)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, extractor, file_path):
        super().__init__()
        self.extractor = extractor
        self.file_path = file_path

    def run(self):
        """This runs in a separate background thread."""
        try:
            # Perform the heavy opensmile calculation
            results = self.extractor.analyzeFile(self.file_path)
            # Emit the results back to the GUI
            self.result_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))