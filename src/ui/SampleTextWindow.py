import os
import sys
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
                             QListWidget, QTextBrowser, QPushButton, QStackedWidget,
                             QPlainTextEdit, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt


class SampleTextWindow(QWidget):
    def __init__(self, sample_dir="sample_texts"):
        super().__init__()
        self.setWindowTitle("Sample Texts Editor")
        self.resize(850, 600)

        # --- Resolve Persistent Directory Path ---
        # Do not use sys._MEIPASS for saving files, as it is wiped on exit.
        if getattr(sys, 'frozen', False):
            # Running as bundled app: use the directory of the executable
            base_dir = os.path.dirname(sys.executable)
        else:
            # Running as script: use project root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_dir = os.path.join(base_dir, '..')

        self.sample_dir = os.path.abspath(os.path.join(base_dir, sample_dir))

        # Ensure the directory exists
        os.makedirs(self.sample_dir, exist_ok=True)

        self.current_file_path = None

        self.setup_ui()
        self.load_files()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # --- 1. Sidebar (List of Texts & New Button) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self.on_row_changed)

        self.btn_new = QPushButton("New Sample Text")
        self.btn_new.clicked.connect(self.create_new_file)

        left_layout.addWidget(self.file_list)
        left_layout.addWidget(self.btn_new)
        splitter.addWidget(left_widget)

        # --- 2. Main Area (Top Bar + View/Edit Stack) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Top Bar for Actions
        top_bar = QHBoxLayout()
        self.btn_edit = QPushButton("Edit")
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_edit.clicked.connect(self.enter_edit_mode)
        self.btn_save.clicked.connect(self.save_file)
        self.btn_cancel.clicked.connect(self.exit_edit_mode)

        # Hide save/cancel initially
        self.btn_save.hide()
        self.btn_cancel.hide()
        self.btn_edit.setEnabled(False)  # Disabled until a file is selected

        top_bar.addStretch()
        top_bar.addWidget(self.btn_edit)
        top_bar.addWidget(self.btn_save)
        top_bar.addWidget(self.btn_cancel)

        right_layout.addLayout(top_bar)

        # Stacked Widget to swap between Reader and Editor
        self.stack = QStackedWidget()

        self.viewer = QTextBrowser()
        self.viewer.setOpenLinks(False)

        self.editor = QPlainTextEdit()
        # Optional: Set a monospaced font for the markdown editor
        font = self.editor.font()
        font.setFamily("Courier")
        self.editor.setFont(font)

        self.stack.addWidget(self.viewer)
        self.stack.addWidget(self.editor)

        right_layout.addWidget(self.stack)
        splitter.addWidget(right_widget)

        splitter.setSizes([200, 650])

    def load_files(self, select_filename=None):
        """Scans the directory and populates the sidebar."""
        self.file_list.clear()

        if not os.path.exists(self.sample_dir):
            return

        files = [f for f in sorted(os.listdir(self.sample_dir)) if f.endswith(".md")]
        self.file_list.addItems(files)

        if select_filename and select_filename in files:
            # Select the newly created/saved file
            row = files.index(select_filename)
            self.file_list.setCurrentRow(row)
        elif files:
            # Default to the first file
            self.file_list.setCurrentRow(0)
        else:
            self.viewer.setMarkdown("# No sample texts found\nClick 'New Sample Text' to create one.")
            self.btn_edit.setEnabled(False)

    def on_row_changed(self, row):
        """Loads the selected file into the viewer and editor."""
        if row < 0:
            return

        filename = self.file_list.item(row).text()
        self.current_file_path = os.path.join(self.sample_dir, filename)

        try:
            with open(self.current_file_path, "r", encoding="utf-8") as f:
                markdown_text = f.read()

            self.viewer.setMarkdown(markdown_text)
            self.editor.setPlainText(markdown_text)
            self.btn_edit.setEnabled(True)
            self.exit_edit_mode()  # Ensure we are in reading mode when swapping files

        except Exception as e:
            self.viewer.setMarkdown(f"# Error\nCould not read file:\n`{e}`")

    def create_new_file(self):
        """Prompts the user for a filename and creates a blank markdown file."""
        text, ok = QInputDialog.getText(self, "New Sample Text", "Enter filename (without .md):")
        if ok and text:
            # Sanitize and format filename
            filename = text.strip()
            if not filename.endswith(".md"):
                filename += ".md"

            new_path = os.path.join(self.sample_dir, filename)

            if os.path.exists(new_path):
                QMessageBox.warning(self, "Error", "A file with that name already exists.")
                return

            # Create the blank file
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(f"# {text}\n\nStart typing here...")

            self.load_files(select_filename=filename)
            self.enter_edit_mode()

    def enter_edit_mode(self):
        """Switches the UI to markdown editing mode."""
        if not self.current_file_path:
            return

        self.stack.setCurrentWidget(self.editor)
        self.btn_edit.hide()
        self.file_list.setEnabled(False)  # Prevent changing files while editing
        self.btn_new.setEnabled(False)
        self.btn_save.show()
        self.btn_cancel.show()

    def exit_edit_mode(self):
        """Reverts the UI back to markdown viewing mode without saving."""
        self.stack.setCurrentWidget(self.viewer)
        self.btn_save.hide()
        self.btn_cancel.hide()
        self.file_list.setEnabled(True)
        self.btn_new.setEnabled(True)
        self.btn_edit.show()

        # Reset editor text back to whatever is currently saved
        if self.current_file_path and os.path.exists(self.current_file_path):
            with open(self.current_file_path, "r", encoding="utf-8") as f:
                self.editor.setPlainText(f.read())

    def save_file(self):
        """Saves the contents of the editor to the current file."""
        if not self.current_file_path:
            return

        new_text = self.editor.toPlainText()
        try:
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(new_text)

            # Update viewer
            self.viewer.setMarkdown(new_text)
            self.exit_edit_mode()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file:\n{e}")