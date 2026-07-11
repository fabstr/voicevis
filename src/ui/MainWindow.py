import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore
import qtawesome as qta

from ui.AnalysisWidget import AnalysisWidget

# Try to safely read the auto-generated version file
try:
    from _version import __version__
except ImportError:
    __version__ = "Dev-Snapshot"

# --- NEW: Subclass to catch the close event properly ---
class SessionDockWidget(QtWidgets.QDockWidget):
    closed = QtCore.pyqtSignal(object)

    def closeEvent(self, event):
        # Emit our custom signal before proceeding with the standard close
        self.closed.emit(self)
        super().closeEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    show_error_signal = QtCore.pyqtSignal(object, object, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"VoiceVis {__version__}")
        self.resize(800, 900)

        self.show_error_signal.connect(self.show_error_dialog)
        sys.excepthook = self.handle_exception

        # --- DOCK WIDGET SETUP ---
        self.setDockOptions(
            QtWidgets.QMainWindow.DockOption.AllowTabbedDocks |
            QtWidgets.QMainWindow.DockOption.AnimatedDocks
        )
        self.setTabPosition(QtCore.Qt.DockWidgetArea.AllDockWidgetAreas,
                            QtWidgets.QTabWidget.TabPosition.North)

        dummy_central = QtWidgets.QWidget()
        self.setCentralWidget(dummy_central)
        dummy_central.hide()

        self.dock_widgets = []

        # Start with one default session
        self.add_new_session()

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Catches global exceptions and routes them to the main thread."""
        # Let keyboard interrupts exit gracefully
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Log the error
        logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

        # Emit the signal instead of directly creating a QMessageBox.
        # This guarantees the dialog is drawn in the main GUI thread safely.
        self.show_error_signal.emit(exc_type, exc_value, exc_traceback)

    def show_error_dialog(self, exc_type, exc_value, exc_traceback):
        tb_string = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

        # Launch our custom dialog instead of standard QMessageBox
        error_dialog = ExceptionDialog(exc_value, tb_string, self)
        error_dialog.exec()

    def add_new_session(self):
        new_session = AnalysisWidget()
        session_num = len(self.dock_widgets) + 1
        tab_name = f"Session {session_num}"

        new_session.new_session_signal.connect(self.add_new_session)

        # Create our custom dock widget
        dock = SessionDockWidget(tab_name, self)
        dock.setWidget(new_session)

        # --- NEW: Connect the widget's close signal to the dock's close slot ---
        new_session.close_session_signal.connect(dock.close)

        # Adding the window icon here automatically places it in the Tab
        dock.setWindowIcon(qta.icon('fa5s.file-audio'))

        # Allow it to be closed, moved, and floated (torn off)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        # Connect the close signal for cleanup
        dock.closed.connect(self.close_dock)

        # Docking Logic:
        # If it's the first dock, drop it into the main area.
        # Otherwise, stack it behind the most recently added dock (creating a tab).
        if not self.dock_widgets:
            self.addDockWidget(QtCore.Qt.DockWidgetArea.TopDockWidgetArea, dock)
        else:
            self.tabifyDockWidget(self.dock_widgets[-1], dock)

        self.dock_widgets.append(dock)

        # Bring the new tab to the front
        dock.raise_()

        # Rename dock when a file is loaded
        new_session.file_loaded_signal.connect(
            lambda file_path, d=dock: self.update_dock_name(d, file_path)
        )

    def update_dock_name(self, dock, file_path):
        if file_path:
            import os
            filename = os.path.basename(file_path)
            dock.setWindowTitle(filename)

    def close_dock(self, dock):
        # Extract the LiveMultiPlotWidget from the dock
        widget = dock.widget()
        if widget:
            # Using hasattr() acts as a safety net in case the widget isn't fully initialized
            if hasattr(widget, 'is_playing') and widget.is_playing:
                widget.stop_playback()
            if hasattr(widget, 'is_recording') and widget.is_recording:
                widget.handle_record_stop()
            widget.deleteLater()

        # Remove from our tracking list and memory
        if dock in self.dock_widgets:
            self.dock_widgets.remove(dock)
        dock.deleteLater()

        if len(self.dock_widgets) == 0:
            sys.exit(0)


class ExceptionDialog(QtWidgets.QDialog):
    def __init__(self, exc_value, tb_string, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unhandled error")
        self.setMinimumSize(600, 400)  # Give it enough space for the traceback

        layout = QtWidgets.QVBoxLayout(self)

        # --- Header Section (Icon + Messages) ---
        header_layout = QtWidgets.QHBoxLayout()

        # Fetch the system's standard critical error icon
        icon_label = QtWidgets.QLabel()
        icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical)
        icon_label.setPixmap(icon.pixmap(48, 48))
        header_layout.addWidget(icon_label)

        msg_layout = QtWidgets.QVBoxLayout()
        title_label = QtWidgets.QLabel("<b>An uncaught exception:</b>")
        info_label = QtWidgets.QLabel(str(exc_value))
        info_label.setWordWrap(True)

        msg_layout.addWidget(title_label)
        msg_layout.addWidget(info_label)
        header_layout.addLayout(msg_layout)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # --- Traceback Section (Always Visible) ---
        tb_edit = QtWidgets.QTextEdit()
        tb_edit.setReadOnly(True)
        tb_edit.setPlainText(tb_string)

        # Set a monospace font so the traceback aligns nicely
        font = tb_edit.font()
        font.setFamily("Courier")
        tb_edit.setFont(font)

        layout.addWidget(tb_edit)

        # --- OK Button ---
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)