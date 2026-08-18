from datetime import datetime
import logging
import os
import sys
import traceback

from pathlib import Path

from PyQt6 import QtWidgets
from PyQt6.QtCore import QStandardPaths, QThread
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMessageBox, QApplication

from ResourceManager import ResourceManager


#: Where this run is logging to, so a crash dialogue can point at it.
LOG_FILE = None


class SyncFileHandler(logging.FileHandler):
    """A FileHandler that forces the OS to immediately write to disk."""
    def emit(self, record):
        super().emit(record)
        try:
            os.fsync(self.stream.fileno())
        except OSError:
            pass


class ConsecutiveDuplicateFilter(logging.Filter):
    """Filters out consecutive identical log messages after a certain threshold."""

    def __init__(self, max_repeats=10):
        super().__init__()
        self.max_repeats = max_repeats
        self.last_message = None
        self.repeat_count = 0

    def filter(self, record):
        # .getMessage() safely resolves any variable injections (like %s) into the final string
        current_message = record.getMessage()

        if current_message == self.last_message:
            self.repeat_count += 1
            # If we've hit the limit (10th consecutive repeat), suppress this and future identical logs
            if self.repeat_count >= self.max_repeats:
                return False
        else:
            # New message arrived! Reset the tracking variables.
            self.last_message = current_message
            self.repeat_count = 0

        return True


def setup_logging():
    app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    log_path = os.path.join(app_data_path, "VoiceVis")
    log_dir = Path(log_path)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat().replace(":", "_")
    log_file = log_dir / f"voicevis.log"
    print("Logging to {}".format(log_file))

    # 1. Instantiate your handlers explicitly
    file_handler = SyncFileHandler(log_file)
    stream_handler = logging.StreamHandler(sys.stdout)

    # 2. Instantiate and attach the filter to both handlers
    duplicate_filter = ConsecutiveDuplicateFilter(max_repeats=10)
    file_handler.addFilter(duplicate_filter)
    stream_handler.addFilter(duplicate_filter)

    # 3. Pass the configured handlers into basicConfig
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(filename)s:%(funcName)s:%(lineno)s %(message)s",
        handlers=[file_handler, stream_handler],
        force=True,
    )
    logging.captureWarnings(True)

    return log_file


def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Catches unhandled exceptions, logs them, and shows a GUI error dialogue safely."""
    # Let keyboard interrupts exit gracefully
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the error with the full traceback to ensure it's recorded somewhere
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # 1. Check if the QApplication instance exists
    app = QApplication.instance()
    if not app:
        # A crash during start-up -- a failed import, most likely. A windowed
        # build has no console to print to, so without a dialogue here the
        # application simply vanishes with no sign of what went wrong. Start Qt
        # just far enough to say so.
        logging.critical("Fatal error before QApplication initialization.")
        try:
            app = QApplication(sys.argv)
        except Exception:
            logging.critical("Could not start Qt to report the error.", exc_info=True)
            sys.exit(1)

    # 2. Check if we are executing in the main GUI thread
    if QThread.currentThread() != app.thread():
        logging.critical("Exception caught in a background thread. Cannot display QMessageBox.")
        # Optional: You would need to emit a custom Signal here to tell the main thread to show the box.
        return

    # Format the traceback for the user message box
    tb_string = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # 3. Show the error dialogue (Safe because we are in the main thread with an active app)
    error_box = QMessageBox()
    error_box.setIcon(QMessageBox.Icon.Critical)
    error_box.setWindowTitle("Fatal Error")
    error_box.setText("An unexpected error occurred.")
    informative = str(exc_value)
    if LOG_FILE is not None:
        informative += f"\n\nThe full log is at:\n{LOG_FILE}"
    error_box.setInformativeText(informative)
    error_box.setDetailedText(tb_string)

    # Process pending events to ensure the UI isn't stuck before showing the dialogue
    app.processEvents()

    error_box.exec()


def set_application_icon(app: QtWidgets.QApplication):
    """
    Applies OS-specific workarounds to ensure taskbar and window icons
    display correctly across Windows, Linux, and macOS.
    """

    if sys.platform == 'win32':
        # Windows: Set AppUserModelID so the taskbar recognizes the unique app
        # rather than grouping it under a generic "Python" executable.
        import ctypes
        try:
            myappid = 'voicevis.voicevis.app.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    elif sys.platform.startswith('linux'):
        # Linux: Set application and desktop file name so Wayland/X11
        # can map the running process to your voicevis.desktop file.
        app.setApplicationName("VoiceVis")
        app.setDesktopFileName("voicevis")

    elif sys.platform == 'darwin':
        # macOS: Sets the correct internal app name for the menu bar.
        # (Note: Dock icons are still primarily handled via the .app bundle's .icns file).
        app.setApplicationName("VoiceVis")

    rm = ResourceManager()
    icon_path = rm.get_absolute_path("icon.ico")
    app.setWindowIcon(QIcon(icon_path))



if __name__ == '__main__':
    LOG_FILE = setup_logging()
    sys.excepthook = global_exception_handler

    # use OpenGl
    # pg.setConfigOptions(useOpenGL=True)

    # imported here to avoid import order problems which makes the logging break
    from ui.MainWindow import MainWindow




    app = QtWidgets.QApplication(sys.argv)
    set_application_icon(app)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())