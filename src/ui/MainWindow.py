import logging
import os
import sys
import traceback

from PyQt6 import QtCore, QtWidgets

from ui.AnalysisWidget import AnalysisWidget

# Try to safely read the auto-generated version file
try:
    from _version import __version__
except ImportError:
    __version__ = "Dev-Snapshot"

BASE_TITLE = f"VoiceVis {__version__}"

#: Pixels a new window is offset from the one it was opened from.
CASCADE_OFFSET = 30


def report_exception(exc_type, exc_value, exc_traceback):
    """Route an uncaught exception to a dialog on the main thread."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    window = MainWindow.active_window()
    if window is None:
        logging.critical("No window available to report the exception in.")
        return

    # Emitting rather than constructing the dialog here guarantees it is drawn
    # on the GUI thread even when the exception came from a worker.
    window.show_error_signal.emit(exc_type, exc_value, exc_traceback)


class MainWindow(QtWidgets.QMainWindow):
    """One analysis session. File > New opens another window."""

    show_error_signal = QtCore.pyqtSignal(object, object, object)

    #: Every window currently open. This list is also what keeps them alive --
    #: a top-level window with no parent is garbage collected once the last
    #: Python reference to it goes away.
    _open_windows = []

    def __init__(self):
        super().__init__()
        self.setWindowTitle(BASE_TITLE)
        self.resize(800, 900)

        self.show_error_signal.connect(self.show_error_dialog)
        sys.excepthook = report_exception

        self.session = AnalysisWidget()
        self.setCentralWidget(self.session)

        self.session.new_session_signal.connect(self.open_new_window)
        self.session.close_session_signal.connect(self.close)
        self.session.file_loaded_signal.connect(self._update_title)
        self.session.series_colours_changed.connect(self.refresh_series_colours)

        self._cascade()
        MainWindow._open_windows.append(self)

    # --- Window management -----------------------------------------------

    @classmethod
    def open_new_window(cls) -> "MainWindow":
        window = cls()
        window.show()
        return window

    @classmethod
    def refresh_series_colours(cls):
        """The palette is application-wide, so repaint every open session."""
        for window in cls._open_windows:
            window.session.refresh_series_colours()

    @classmethod
    def active_window(cls):
        """The window an exception should be reported in."""
        app = QtWidgets.QApplication.instance()
        active = app.activeWindow() if app else None
        if isinstance(active, cls):
            return active
        return cls._open_windows[-1] if cls._open_windows else None

    def _cascade(self):
        """Offset from the most recently opened window so the new one is visible."""
        if not MainWindow._open_windows:
            return
        previous = MainWindow._open_windows[-1]
        self.move(previous.pos() + QtCore.QPoint(CASCADE_OFFSET, CASCADE_OFFSET))

    def _update_title(self, file_path):
        name = os.path.basename(file_path) if file_path else ""
        self.setWindowTitle(f"{name} - {BASE_TITLE}" if name else BASE_TITLE)

    def closeEvent(self, event):
        self.session.shutdown()

        if self in MainWindow._open_windows:
            MainWindow._open_windows.remove(self)

        super().closeEvent(event)
        self.deleteLater()

    # --- Error reporting --------------------------------------------------

    def show_error_dialog(self, exc_type, exc_value, exc_traceback):
        tb_string = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        ExceptionDialog(exc_value, tb_string, self).exec()


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
