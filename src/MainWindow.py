import sys

from PyQt6 import QtWidgets, QtCore
import qtawesome as qta

from LiveMultiPlotWidget import LiveMultiPlotWidget


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VoiceVis")
        self.resize(800, 900)

        # Create the Tab Widget
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)

        # Add the "+" button to the corner for new sessions using QtAwesome
        self.add_tab_btn = QtWidgets.QPushButton()
        self.add_tab_btn.setIcon(qta.icon('fa5s.plus'))

        # Slightly smaller size fits the tab bar better
        self.add_tab_btn.setFixedSize(28, 28)
        self.add_tab_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

        # --- NEW STYLING ---
        # Remove the blocky background, add padding, and give it a modern hover effect
        # --- ADJUSTED STYLING ---
        self.add_tab_btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        /* Pull the button UP by using a negative top margin */
                        margin-top: 8px; 
                        /* Ensure it doesn't clip the bottom by adding bottom margin */
                        margin-bottom: 8px; 
                        margin-right: 6px; 
                        
                        padding: 4px;
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
        self.tabs.setCornerWidget(self.add_tab_btn, QtCore.Qt.Corner.TopRightCorner)

        # Start with one default tab
        self.add_new_session()

    def add_new_session(self):
        new_session = LiveMultiPlotWidget()
        tab_name = f"Session {self.tabs.count() + 1}"

        # Add an icon to the tab itself
        tab_icon = qta.icon('fa5s.file-audio')
        index = self.tabs.addTab(new_session, tab_icon, tab_name)
        self.tabs.setCurrentIndex(index)

        # Optional: Rename tab when a file is loaded
        new_session.file_path_display.textChanged.connect(
            lambda text, idx=index: self.update_tab_name(idx, text)
        )

    def update_tab_name(self, index, text):
        if text and text != "Select or drag & drop a file to analyze...":
            import os
            filename = os.path.basename(text)
            self.tabs.setTabText(index, filename)

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        if widget:
            if widget.is_playing:
                widget.stop_playback()
            if widget.is_recording:
                widget.handle_record_stop()
            widget.deleteLater()
        self.tabs.removeTab(index)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()  # Changed from LiveMultiPlotWidget()
    w.show()
    sys.exit(app.exec())