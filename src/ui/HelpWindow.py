import logging
import os
import re
import sys
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QListWidget, QTextBrowser
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QImageReader, QTextCursor
from ResourceManager import ResourceManager

# --- Try to safely read the auto-generated version file ---
try:
    from _version import __version__
except ImportError:
    __version__ = "Dev-Snapshot"

_ATX_HEADING_RE = re.compile(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$')
_SLUG_STRIP_RE = re.compile(r'[^\w\- ]')


def _heading_slugs(markdown_text):
    """GitHub-style anchor slugs for every ATX heading, in document order.

    Table-of-contents links written into the docs (``[Foo](#foo)``) use
    GitHub's slug rules, since that's what renders them correctly on
    GitHub itself. Reproducing the same rules here -- lowercase, strip
    anything that isn't a word character/hyphen/space, spaces to hyphens,
    and a "-1", "-2", ... suffix for each repeat of an already-seen slug --
    is what lets the in-app viewer resolve the exact same links.
    """
    seen = {}
    slugs = []
    for line in markdown_text.splitlines():
        match = _ATX_HEADING_RE.match(line)
        if not match:
            continue
        slug = _SLUG_STRIP_RE.sub('', match.group(2).lower()).replace(' ', '-')
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        slugs.append(slug)
    return slugs


class _ScalingTextBrowser(QTextBrowser):
    """A QTextBrowser whose embedded images never exceed its own width.

    ``setMarkdown()`` inserts images at their native pixel size, which for a
    full-window screenshot is a lot wider than a help pane a few hundred
    pixels across -- Qt's rich-text HTML subset doesn't reliably honour CSS
    like ``max-width``, so the fix is to give each image an explicit
    width/height scaled to fit. That has to be redone whenever the pane's
    width changes -- on a window resize, or the splitter beside it being
    dragged -- not just once after loading the text.
    """

    def setMarkdown(self, text):
        super().setMarkdown(text)
        self._rescale_images()
        self._add_heading_anchors(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Not a direct call: rewriting image formats mid-resize, before Qt's
        # own layout pass for the *new* size has settled, leaves the
        # document's internal size bookkeeping stale -- the scrollbar range
        # ends up computed against neither the old geometry nor the new one.
        # That doesn't show up as a resize to *this* width, it shows up on
        # the *next* one: shrink the window, then widen it back, and the
        # document is laid out shorter than it actually is, so the scrollbar
        # can no longer reach content that is genuinely still there.
        # Deferring to the next event-loop turn runs this once Qt's own
        # resize handling -- and the geometry it produces -- has finished.
        QTimer.singleShot(0, self._rescale_images)

    def _rescale_images(self):
        doc = self.document()
        available = self.viewport().width() - 2 * doc.documentMargin()
        if available <= 0:
            return

        # Two passes, deliberately not one: walking QTextBlock/fragment
        # handles obtained from doc.begin() while *also* editing the
        # document through a QTextCursor -- as an earlier version of this
        # method did -- corrupts the walk partway through. It doesn't raise
        # or stop cleanly; every image still gets *visited* (no exception,
        # no early return), but blocks after wherever the corruption starts
        # silently never get laid out, so the document reports a height
        # far short of its real one and the scrollbar can't reach content
        # that's genuinely still there. A character position is still valid
        # after a format-only edit (nothing is inserted or removed), so
        # collecting every edit as (position, length, format) first and
        # applying them by position in a second, read-only-safe pass avoids
        # the problem entirely rather than working around its symptom.
        edits = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                it += 1
                if not fragment.isValid():
                    continue

                char_format = fragment.charFormat()
                if not char_format.isImageFormat():
                    continue
                image_format = char_format.toImageFormat()

                natural = self._natural_size(image_format.name())
                if natural is None or natural.width() <= 0:
                    continue

                # Never upscale past the file's own resolution -- a smaller
                # image just keeps its size instead of blurring outward.
                new_width = min(available, natural.width())
                new_height = new_width * natural.height() / natural.width()
                if abs(image_format.width() - new_width) < 1:
                    continue  # already the right size; nothing to edit

                image_format.setWidth(new_width)
                image_format.setHeight(new_height)
                edits.append((fragment.position(), fragment.length(), image_format))
            block = block.next()

        if not edits:
            return

        cursor = QTextCursor(doc)
        for position, length, image_format in edits:
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(image_format)

        # A belt-and-braces relayout: with a dozen-plus large inline images,
        # the document's own dirty-tracking after several scattered
        # setCharFormat() calls has been observed to under-report the total
        # height (measured directly: the sum of the images' own heights
        # alone exceeded document().size().height()), so the scrollbar ends
        # up unable to reach content that is genuinely still there. Marking
        # the whole document dirty forces Qt to recompute it from scratch
        # rather than trust whatever partial update the edits above produced.
        doc.markContentsDirty(0, doc.characterCount())

    def _natural_size(self, name):
        """The image's true pixel size, read straight from disk.

        Deliberately not ``document().resource(...)``: whether that goes
        through this browser's own search-path-aware loading, or just the
        document's own (which knows nothing of ``setSearchPaths()``), is not
        something to depend on. Reading the file directly, through the same
        search paths the browser was given, is unambiguous.
        """
        candidates = [os.path.join(d, name) for d in self.searchPaths()]
        candidates.append(name)  # already absolute, or resolvable as-is

        for path in candidates:
            if os.path.exists(path):
                size = QImageReader(path).size()
                if size.isValid():
                    return size
        return None

    def _add_heading_anchors(self, source_text):
        """Stamp each rendered heading with its GitHub-style slug as a named anchor.

        ``setMarkdown()`` renders '#'-headings as heading blocks but, unlike
        GitHub, gives them no id of their own -- so a table-of-contents link
        like ``[Foo](#foo)`` has nothing to jump to, even though the same
        link works fine on GitHub. Recomputing the slugs from the source
        markdown (in document order, so repeated headings also get GitHub's
        "-1", "-2", ... suffixes) and setting each one as a
        ``QTextCharFormat`` anchor on the matching rendered block is what
        lets ``scrollToAnchor()`` find it.
        """
        slugs = iter(_heading_slugs(source_text))
        doc = self.document()
        cursor = QTextCursor(doc)

        block = doc.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                slug = next(slugs, None)
                if slug is None:
                    break
                length = max(block.length() - 1, 0)  # exclude the block separator
                if length > 0:
                    cursor.setPosition(block.position())
                    cursor.setPosition(block.position() + length,
                                       QTextCursor.MoveMode.KeepAnchor)
                    char_format = cursor.charFormat()
                    char_format.setAnchor(True)
                    char_format.setAnchorNames([slug])
                    cursor.setCharFormat(char_format)
            block = block.next()


class HelpWindow(QWidget):
    def __init__(self, resource_manager: ResourceManager, docs_dir="docs"):
        super().__init__()
        # --- Update the window title to include the version ---
        self.setWindowTitle(f"VoiceVis Help")
        self.resize(850, 600)

        self.docs_dir = resource_manager.get_absolute_path(docs_dir)

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
        self.text_browser = _ScalingTextBrowser()
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

        logging.info(f"Scanning for help files: {self.docs_dir}")

        # Sort files alphabetically so the sidebar is predictable
        for filename in sorted(os.listdir(self.docs_dir)):
            if filename.endswith(".md"):
                file_path = os.path.join(self.docs_dir, filename)
                title = self._extract_title_from_md(file_path)

                item = {
                    "title": title,
                    "file_name": file_path
                }
                logging.debug(f"scanning for help files, found {filename}")
                # Check if this is our main file
                if filename.lower() == "readme.md":
                    main_item = item
                else:
                    help_items.append(item)

        # If readme.md was found, insert it at the very top (index 0)
        if main_item:
            help_items.insert(0, main_item)
        logging.debug(f"help main: {main_item}")
        logging.debug(f"help_items: {help_items}")

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
            logging.error(f"Could not read {file_path}: {e}")

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

                markdown_text = markdown_text.replace("{{VERSION}}", __version__)

                # setMarkdown() has no notion of "where this came from", so
                # relative image references (![](img/x.png)) would otherwise
                # fail to resolve. Search from the doc's own directory first,
                # then the docs root, so images work whether a doc sits at the
                # top level or in a subfolder.
                self.text_browser.setSearchPaths(
                    [os.path.dirname(file_name), self.docs_dir])
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

        # 2. Handle a same-document anchor, e.g. a table-of-contents entry
        # like "#general-workflow" -- no scheme, no path, just a fragment.
        if url.fragment() and not url.path():
            self.text_browser.scrollToAnchor(url.fragment())
            return

        # 3. Handle internal Markdown links
        target_filename = os.path.basename(url.toString())

        # Search our help_data for a matching filename
        for index, item in enumerate(self.help_data):
            if os.path.basename(item["file_name"]) == target_filename:
                # Update the sidebar selection.
                self.toc_list.setCurrentRow(index)
                return

        logging.error(f"Could not resolve internal link: {url.toString()}")