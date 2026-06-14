import sys
from PyQt6 import QtWidgets, QtCore
import qtawesome as qta

from ui.LiveMultiPlotWidget import LiveMultiPlotWidget


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
        self.setWindowTitle("VoiceVis")
        self.resize(800, 900)

        # --- DOCK WIDGET SETUP ---
        # Allow docks to be tabbed together and animate their snapping
        self.setDockOptions(
            QtWidgets.QMainWindow.DockOption.AllowTabbedDocks |
            QtWidgets.QMainWindow.DockOption.AnimatedDocks
        )
        # Force the dock tabs to appear at the top (imitating a QTabWidget)
        self.setTabPosition(QtCore.Qt.DockWidgetArea.AllDockWidgetAreas,
                            QtWidgets.QTabWidget.TabPosition.North)

        # Hide the central widget entirely. This allows our dock widgets
        # to consume the entire window area without borders.
        dummy_central = QtWidgets.QWidget()
        self.setCentralWidget(dummy_central)
        dummy_central.hide()

        self.dock_widgets = []

        # --- TOOLBAR & ADD BUTTON ---
        # Because we aren't using QTabWidget, we place the "+" button in a toolbar.
        self.toolbar = QtWidgets.QToolBar("Session Controls")
        self.toolbar.setMovable(False)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.add_tab_btn = QtWidgets.QPushButton(" New Session")
        self.add_tab_btn.setIcon(qta.icon('fa5s.plus'))
        self.add_tab_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        # Styling adjusted: negative margins removed as they are no longer
        # needed for corner-widget fitting.
        self.add_tab_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 6px;
                margin: 2px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 0.2);
                border-radius: 4px;
            }
            QPushButton:pressed {
                background-color: rgba(128, 128, 128, 0.4);
            }
        """)
        self.add_tab_btn.clicked.connect(self.add_new_session)
        self.toolbar.addWidget(self.add_tab_btn)

        # Start with one default session
        self.add_new_session()

    def add_new_session(self):
        new_session = LiveMultiPlotWidget()
        session_num = len(self.dock_widgets) + 1
        tab_name = f"Session {session_num}"

        # Create our custom dock widget
        dock = SessionDockWidget(tab_name, self)
        dock.setWidget(new_session)

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


