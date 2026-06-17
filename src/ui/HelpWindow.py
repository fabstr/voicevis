import os
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QListWidget, QTextBrowser
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices


class HelpWindow(QWidget):
    def __init__(self, docs_dir="docs"):
        super().__init__()
        self.setWindowTitle("VoiceVis Help")
        self.resize(850, 600)
        self.docs_dir = docs_dir

        # Set up the main layout and a splitter for resizable panes
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # --- 1. Sidebar (Table of Contents) ---
        self.toc_list = QListWidget()
        self.toc_list.setMinimumWidth(150)
        splitter.addWidget(self.toc_list)

        # --- 2. Markdown Viewer ---
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenLinks(False)  # Turn off automatic handling
        self.text_browser.anchorClicked.connect(self.handle_link_click)  # Intercept clicks
        splitter.addWidget(self.text_browser)

        splitter.setSizes([200, 650])

        # --- 3. Dynamically Generate Help Content ---
        self.help_data = self._scan_docs_directory()

        # --- 4. Populate and Connect ---
        if self.help_data:
            # Extract titles and populate the list
            titles = [item["title"] for item in self.help_data]
            self.toc_list.addItems(titles)

            # Connect and select the first item
            self.toc_list.currentRowChanged.connect(self.on_row_changed)
            self.toc_list.setCurrentRow(0)
        else:
            # Fallback if the docs directory is empty or missing
            self.toc_list.addItem("No documentation found")
            self.text_browser.setMarkdown(
                f"# Error\nCould not find any `.md` files in the `{self.docs_dir}` directory.")

    def _scan_docs_directory(self):
        """Scans the docs directory for .md files, prioritizing main.md."""
        help_items = []
        main_item = None

        if not os.path.exists(self.docs_dir) or not os.path.isdir(self.docs_dir):
            return help_items

        # Sort files alphabetically so the sidebar is predictable
        for filename in sorted(os.listdir(self.docs_dir)):
            if filename.endswith(".md"):
                file_path = os.path.join(self.docs_dir, filename)
                title = self._extract_title_from_md(file_path)

                item = {
                    "title": title,
                    "file_name": file_path
                }

                # Check if this is our main file
                if filename.lower() == "README.md":
                    main_item = item
                else:
                    help_items.append(item)

        # If main.md was found, insert it at the very top (index 0)
        if main_item:
            help_items.insert(0, main_item)

        return help_items

    def _extract_title_from_md(self, file_path):
        """Reads a file to find the first Level 1 header (# Title)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    # Look for a top-level markdown header
                    if line.startswith("# "):
                        return line[2:].strip()
        except Exception as e:
            print(f"Could not read {file_path}: {e}")

        # Fallback: if no # header is found, use the filename formatted nicely
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        return base_name.replace("_", " ").title()

    def on_row_changed(self, row):
        """Fires when the user clicks a different topic in the sidebar."""
        if 0 <= row < len(self.help_data):
            file_name = self.help_data[row]["file_name"]

            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    markdown_text = f.read()
                self.text_browser.setMarkdown(markdown_text)
            except FileNotFoundError:
                error_msg = f"# Error\nCould not find documentation file:\n`{file_name}`"
                self.text_browser.setMarkdown(error_msg)

    def handle_link_click(self, url: QUrl):
        """Intercepts link clicks to sync the sidebar or open web browsers."""
        # 1. Handle external web links
        if url.scheme() in ['http', 'https', 'mailto']:
            QDesktopServices.openUrl(url)
            return

        # 2. Handle internal Markdown links
        # Extract just the filename (e.g., from "./docs/data_extraction.md" to "data_extraction.md")
        target_filename = os.path.basename(url.toString())

        # Search our help_data for a matching filename
        for index, item in enumerate(self.help_data):
            if os.path.basename(item["file_name"]) == target_filename:
                # Update the sidebar selection.
                # This automatically triggers on_row_changed() and loads the document!
                self.toc_list.setCurrentRow(index)
                return

        print(f"Could not resolve internal link: {url.toString()}")