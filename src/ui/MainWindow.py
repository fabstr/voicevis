import sys
from PyQt6 import QtWidgets, QtCore
import qtawesome as qta

from ui.LiveMultiPlotWidget import LiveMultiPlotWidget

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
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"VoiceVis {__version__}")
        self.resize(800, 900)

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

    def add_new_session(self):
        new_session = LiveMultiPlotWidget()
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


