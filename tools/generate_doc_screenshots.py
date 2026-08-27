#!/usr/bin/env python3
"""Render the screenshots used by resources/docs/10_usage.md and
resources/docs/15_analyzed_features.md.

Drives a real (but off-screen) instance of VoiceVis through the "General
workflow", "Working with targets" and "Audio editing" walkthroughs and grabs
a PNG at each step, so the docs stay in sync with the actual UI instead of
going stale the next time something in the toolbar or a dialog changes shape.
It also grabs one single-pane screenshot per row of the "Analyzed Features"
table (README.md / 15_analyzed_features.md), each showing just that
feature's own series on an otherwise empty grid.

Runs headless (Qt's "offscreen" platform plugin -- no window ever appears),
against an isolated QSettings location (never touches whichever layout/
target/colours you have saved from actually using the app) and loads the
bundled "simple" layout explicitly, so the result does not depend on
whatever this machine happens to have saved. Because of that it is safe to
re-run any time the UI changes.

Usage:
    .venv/Scripts/python tools/generate_doc_screenshots.py

Regenerate after any change to the toolbar, the menus, a dialog, the
"simple" layout preset, a target file the docs reference, or the set of
analyzed features (SeriesRegistry.py).
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Must happen before Qt reads the platform plugin, i.e. before the PyQt6
# import below.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402  (see above)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

OUT_DIR = REPO_ROOT / "resources" / "docs" / "img" / "workflow"
FEATURES_OUT_DIR = REPO_ROOT / "resources" / "docs" / "img" / "features"
EXAMPLE_AUDIO = (REPO_ROOT / "examples" / "accent_gmu_edu" / "swedish"
                 / "F_swedish10.mp3")

WINDOW_SIZE = (900, 600)
ANALYSIS_TIMEOUT_MS = 60_000

#: One single-pane screenshot per feature shown in
#: resources/docs/15_analyzed_features.md: (output filename stem, series
#: shown on Y, spectrogram toggle). Rows that group several series in one
#: README table cell (the formants, the formant/pitch ratios) show them
#: together on one shared axis, the same way the table groups them -- except
#: H1-H2/H1-H3/H1-H4, which despite being one table row each get their own
#: plot, since they're independent measurements best compared one at a time.
FEATURE_ROWS = [
    ("pitch", ["pitch"], False),
    ("loudness", ["loudness"], False),
    ("formants", ["F1", "F2", "F3"], False),
    ("jitter", ["jitter"], False),
    ("shimmer", ["shimmer"], False),
    ("h1_h2", ["H1_H2"], False),
    ("h1_h3", ["H1_H3"], False),
    ("h1_h4", ["H1_H4"], False),
    ("h1_a3", ["H1_A3"], False),
    ("formant_pitch_ratios", ["F1_Pitch", "F2_Pitch", "F3_Pitch"], False),
    ("size", ["size"], False),
    ("spectrogram", [], True),
]


def main():
    if not EXAMPLE_AUDIO.exists():
        sys.exit(f"Example file not found: {EXAMPLE_AUDIO}\n"
                 "(it lives outside git -- see examples/accent_gmu_edu/swedish/fetch.sh)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_OUT_DIR.mkdir(parents=True, exist_ok=True)

    settings_dir = tempfile.mkdtemp(prefix="voicevis_docshots_settings_")
    try:
        _isolate_qsettings(settings_dir)

        app = QtWidgets.QApplication(sys.argv)
        _apply_dark_palette(app)
        _apply_real_font(app)

        from ui.MainWindow import MainWindow
        window = MainWindow()
        window.resize(*WINDOW_SIZE)
        window.show()
        session = window.session

        # The shipped default grid duplicates Loudness; "simple" gives four
        # distinct plots and is the layout this walkthrough asks readers to
        # follow along with, so the screenshots should show it rather than
        # whatever a fresh install happens to seed the grid with.
        simple_layout = session.resource_manager.get_absolute_path("layouts/layout_simple.json")
        session.load_layout_from_file(simple_layout)

        shots = _Shots(app, window, session)
        shots.launch()
        shots.open_file_menu()
        shots.load_and_analyse()
        shots.feature_screenshots()
        # feature_screenshots() swaps in a single-pane layout per feature;
        # every later step assumes the four-plot "simple" grid is back.
        session.load_layout_from_file(simple_layout)
        shots.playback()
        shots.axis_picker()
        shots.targets()
        shots.set_targets_dialog()
        shots.zoom()
        shots.annotation()
        shots.gain()
        shots.audio_editing()

        window.close()
    finally:
        shutil.rmtree(settings_dir, ignore_errors=True)

    print(f"Wrote {len(list(OUT_DIR.glob('*.png')))} screenshot(s) to {OUT_DIR}")
    print(f"Wrote {len(list(FEATURES_OUT_DIR.glob('*.png')))} screenshot(s) to {FEATURES_OUT_DIR}")


def _isolate_qsettings(settings_dir):
    """Redirect ``QSettings("AudioAnalyzer", "LiveMultiPlotWidget")`` to a temp file.

    ``AnalysisWidget`` always constructs its QSettings with that two
    positional-argument form. Per Qt's docs that convenience constructor is
    hardcoded to ``QSettings.Format.NativeFormat`` -- the Windows registry on
    Windows -- so ``QSettings.setDefaultFormat()``/``setPath()`` alone have no
    effect on it; only the explicit ``QSettings(format, scope, org, app)`` form
    respects a redirected path. Swapping in a subclass that rewrites the
    two-string-argument call into that explicit form is the only way to get an
    isolated run without editing the app itself, so this run never touches --
    and is never affected by -- whichever layout/target/colours are actually
    saved on this machine.
    """
    class _IsolatedQSettings(QtCore.QSettings):
        def __init__(self, *args, **kwargs):
            if len(args) == 2 and all(isinstance(a, str) for a in args):
                super().__init__(QtCore.QSettings.Format.IniFormat,
                                 QtCore.QSettings.Scope.UserScope, *args)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = _IsolatedQSettings
    QtCore.QSettings.setPath(QtCore.QSettings.Format.IniFormat,
                             QtCore.QSettings.Scope.UserScope, settings_dir)


#: (font file, family name) tried in order, first one found on disk wins.
_CANDIDATE_FONTS = [
    (r"C:\Windows\Fonts\segoeui.ttf", "Segoe UI"),  # Windows 10/11's UI font
]


def _apply_real_font(app):
    """Load an actual system font file rather than trust Qt's fallback.

    Under the offscreen platform plugin, ``QApplication.font()`` resolves to
    a generic "Sans Serif" alias that -- at least in this environment -- maps
    to whatever incomplete fallback font Qt finds first, which rendered
    every letter as its uppercase glyph. Loading a real TrueType file with
    ``QFontDatabase.addApplicationFont`` and setting it explicitly sidesteps
    that resolution step entirely, so the screenshots use the same font a
    real window on this machine does. If none of the candidates exist (e.g.
    running this on Linux/macOS), it falls back to whatever Qt finds and
    says so, rather than failing the whole run over a cosmetic mismatch.
    """
    for path, family in _CANDIDATE_FONTS:
        if os.path.exists(path):
            QtGui.QFontDatabase.addApplicationFont(path)
            app.setFont(QtGui.QFont(family, 9))
            return
    print(f"  (none of the candidate font files exist; "
         f"using Qt's fallback -- {app.font().family()!r})")


def _apply_dark_palette(app):
    """A style-independent dark palette.

    QGuiApplication.styleHints().setColorScheme() depends on OS integration
    that the offscreen platform plugin does not provide, so it silently does
    nothing there. Setting the palette directly works regardless of platform,
    and it is what every palette-derived colour in the app (plot background,
    menu icons -- see PlotTheme.py) actually reads from.
    """
    app.setStyle("Fusion")

    palette = QtGui.QPalette()
    Role = QtGui.QPalette.ColorRole
    window = QtGui.QColor(45, 45, 48)
    base = QtGui.QColor(30, 30, 32)
    text = QtGui.QColor(225, 225, 225)
    highlight = QtGui.QColor(42, 130, 218)

    palette.setColor(Role.Window, window)
    palette.setColor(Role.WindowText, text)
    palette.setColor(Role.Base, base)
    palette.setColor(Role.AlternateBase, window)
    palette.setColor(Role.ToolTipBase, text)
    palette.setColor(Role.ToolTipText, text)
    palette.setColor(Role.Text, text)
    palette.setColor(Role.Button, window)
    palette.setColor(Role.ButtonText, text)
    palette.setColor(Role.BrightText, QtGui.QColor(255, 90, 90))
    palette.setColor(Role.Link, highlight)
    palette.setColor(Role.Highlight, highlight)
    palette.setColor(Role.HighlightedText, QtGui.QColor(20, 20, 20))
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, Role.Text,
                     QtGui.QColor(120, 120, 120))
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled, Role.WindowText,
                     QtGui.QColor(120, 120, 120))
    app.setPalette(palette)


class _Shots:
    """One method per workflow step. Each writes one or two numbered PNGs.

    Where a step in the docs is more than a single click -- opening a menu
    and picking something, opening a dialog and filling it in -- the method
    writes both the "doing it" screenshot and the "result" screenshot, so
    the docs can show both rather than asking the reader to imagine the step
    in between.
    """

    def __init__(self, app, window, session):
        self.app = app
        self.window = window
        self.session = session

    # --- Plumbing ----------------------------------------------------------

    def _cell_showing(self, y_keys):
        return next(c for c in self.session.plot_cells
                   if c.config.y == list(y_keys))

    def _pump(self, ms=50):
        deadline = QtCore.QElapsedTimer()
        deadline.start()
        while deadline.elapsed() < ms:
            self.app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)

    def _wait_until(self, predicate, timeout_ms):
        deadline = QtCore.QElapsedTimer()
        deadline.start()
        while not predicate() and deadline.elapsed() < timeout_ms:
            self.app.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.WaitForMoreEvents, 100)
        return predicate()

    def _wait_for_analysis(self):
        """Wait for whichever AnalysisWorker is currently in flight."""
        state = {"done": False, "error": None}
        worker = self.session.worker
        if worker is None:
            return
        worker.result_ready.connect(lambda _: state.__setitem__("done", True))
        worker.error_occurred.connect(lambda msg: state.__setitem__("error", msg))

        ok = self._wait_until(lambda: state["done"] or state["error"],
                              ANALYSIS_TIMEOUT_MS)
        if state["error"]:
            sys.exit(f"Analysis failed: {state['error']}")
        if not ok:
            sys.exit("Analysis timed out")

    def _save(self, name, out_dir=OUT_DIR):
        self._pump()
        path = out_dir / name
        ok = self.window.grab().save(str(path))
        if not ok:
            sys.exit(f"Failed to save {path}")
        print(f"  wrote {name}")

    def _save_composed(self, name, overlay):
        """Grab the window with ``overlay`` (already shown) composited on top.

        A popup menu or a dialog is its own top-level window, so grabbing the
        main window alone would not include it -- the two are grabbed
        separately and composited at the overlay's real screen position.
        """
        window_pix = self.window.grab()
        overlay_pix = overlay.grab()
        origin = self.window.mapToGlobal(QtCore.QPoint(0, 0))
        offset = overlay.pos() - origin

        composed = QtGui.QPixmap(window_pix)
        painter = QtGui.QPainter(composed)
        painter.drawPixmap(offset, overlay_pix)
        painter.end()

        path = OUT_DIR / name
        if not composed.save(str(path)):
            sys.exit(f"Failed to save {path}")
        print(f"  wrote {name}")

    def _save_with_popup(self, name, menu, global_pos):
        menu.popup(global_pos)
        # popup() repositions to stay within the *virtual* screen, which under
        # the offscreen platform plugin is not the same size as our window --
        # so a popup anchored low in a tall window can get moved somewhere
        # that no longer reads as "belonging" to the button that opened it.
        # Pin it back to the position we actually wanted, now that it exists
        # and popup() is done adjusting it.
        menu.move(global_pos)
        self._pump(150)
        self._save_composed(name, menu)
        menu.close()
        self._pump()

    def _save_with_dialog(self, name, open_dialog, before_grab=None):
        """Open a modal dialog, grab it in context, then close it (Reject).

        ``dialog.exec()`` blocks, so the grab has to happen from a zero-delay
        timer that fires once ``exec()``'s own nested event loop is running.
        """
        def fire():
            dialog = self._active_dialog()
            if dialog is None:
                return
            if before_grab is not None:
                before_grab(dialog)
            self._pump(50)
            self._save_composed(name, dialog)
            dialog.reject()

        QtCore.QTimer.singleShot(100, fire)
        open_dialog()

    def _active_dialog(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget, QtWidgets.QDialog) and widget.isVisible():
                return widget
        return None

    # --- General workflow ------------------------------------------------

    def launch(self):
        print("launch")
        self._save("01_launch.png")

    def open_file_menu(self):
        print("file menu")
        file_action = next(a for a in self.session.menu_bar.actions()
                           if "File" in a.text())
        rect = self.session.menu_bar.actionGeometry(file_action)
        pos = self.session.menu_bar.mapToGlobal(rect.bottomLeft())
        self._save_with_popup("02_open_menu.png", file_action.menu(), pos)

    def load_and_analyse(self):
        print("loaded & analysed")
        self.session.load_audio_to_memory(str(EXAMPLE_AUDIO))
        self._wait_for_analysis()
        self._save("03_loaded.png")

    def feature_screenshots(self):
        """One single-pane grid per row of the Analyzed Features table.

        Window size is untouched (still ``WINDOW_SIZE``); only the plot grid
        is swapped, one column/one row at a time, so each shot shows exactly
        the series that table row describes and nothing else.
        """
        print("feature screenshots")
        for slug, y_keys, spectrogram in FEATURE_ROWS:
            layout = {
                "version": 2,
                "global_size": 3,
                "main_splitter_sizes": [],
                "columns": [
                    {
                        "plots": [
                            {
                                "x": ["time"],
                                "y": y_keys,
                                "colour": None,
                                "trail_time": 3.0,
                                "spectrogram": spectrogram,
                                "separate_axes": False,
                                "local_size": 3,
                            }
                        ],
                        "sizes": [],
                    }
                ],
            }
            self.session.apply_layout_data(layout)
            self._save(f"{slug}.png", out_dir=FEATURES_OUT_DIR)

    def playback(self):
        print("playback")
        # A simulated mid-playback state, not a real one: engaging the actual
        # audio backend would need a working output device, which a headless
        # box generating docs offscreen may not have. Only the visuals matter
        # here.
        session = self.session
        target_time = min(6.5, session.hub.length_seconds / 2)
        # update_playhead() -> _advance_transport() recomputes
        # current_playback_time from playback_start_time while is_playing, the
        # same way a real seek_and_play() does -- setting current_playback_time
        # directly would just be overwritten (and, with playback_start_time
        # still at its 0.0 default, overwritten with a huge bogus value that
        # trips the "past the end of the recording" stop check).
        session.playback_start_time = time.time() - target_time
        session.is_playing = True
        session.action_play.setIcon(session.pause_icon)
        session.action_play.setText("&Pause\tSpace")
        session.action_play.setToolTip("Pause (Space)")
        session.update_playhead()

        self._save("04_playback.png")

        session.is_playing = False
        session.action_play.setIcon(session.play_icon)
        session.action_play.setText("&Play\tSpace")
        session.action_play.setToolTip("Play (Space)")

    def axis_picker(self):
        print("axis picker: menu + result")
        # "simple" has no formants plot; turning the Loudness cell into one
        # both demonstrates the picker and leaves something with a target on
        # screen for the targets step right after this.
        cell = self._cell_showing(["loudness"])
        selector = cell.controls.y_selector
        pos = selector.mapToGlobal(QtCore.QPoint(0, selector.height()))
        self._save_with_popup("05_axis_picker_menu.png", selector.menu(), pos)

        # Same effect as checking F1/F2/F3 in that menu: PlotControls._apply
        # normalises the config, refreshes its own widgets, and emits
        # config_changed, which is what PlotCell listens to.
        cell.controls._apply(y=["F1", "F2", "F3"])
        self._save("06_axis_picker_result.png")

    def targets(self):
        print("targets: menu + result")
        targets_action = next(a for a in self.session.menu_bar.actions()
                              if "Targets" in a.text())
        rect = self.session.menu_bar.actionGeometry(targets_action)
        pos = self.session.menu_bar.mapToGlobal(rect.bottomLeft())
        self._save_with_popup("07_targets_menu.png", targets_action.menu(), pos)

        self.session.load_targets_from_path("targets/target_female.json")
        self._save("08_targets_result.png")

        # A second shot with Male loaded, so "Working with targets" can show
        # the two presets side by side rather than asserting they differ.
        # Reload Female straight after: every later step (the Set Targets
        # dialog, the audio-editing shots) assumes Female is the active
        # target, matching what they were captured against before.
        self.session.load_targets_from_path("targets/target_male.json")
        self._save("08b_targets_result_male.png")
        self.session.load_targets_from_path("targets/target_female.json")

    def set_targets_dialog(self):
        print("set targets dialog")
        self._save_with_dialog("12_set_targets_dialog.png",
                               self.session.open_targets_dialog)

    def zoom(self):
        print("zoom")
        session = self.session
        pitch_cell = self._cell_showing(["pitch"])
        pitch_cell.view_box.setXRange(2.0, 8.0, padding=0)
        session.btn_zoom_x.setChecked(True)

        self._save("09_zoom.png")

        session.btn_zoom_x.setChecked(False)
        session.handle_reset_zoom()

    def annotation(self):
        print("annotation: dialog + result")
        session = self.session
        pitch_cell = self._cell_showing(["pitch"])

        def type_note(dialog):
            text_edit = dialog.findChild(QtWidgets.QTextEdit)
            if text_edit is not None:
                text_edit.setPlainText("Pitch is 200 Hz here.")

        self._save_with_dialog(
            "10_annotation_dialog.png",
            lambda: session.add_annotation(pitch_cell, 5.0, 200.0),
            before_grab=type_note)

        # The dialog above was rejected (see _save_with_dialog), so nothing
        # was actually saved -- add the real one the same way a Save click
        session._attach_annotation(pitch_cell, 5.0, 200.0,
                                   "Pitch is 200 Hz here.")
        # would, to get a marker on screen for the result shot.
        self._save("11_annotation_result.png")

    # --- Audio editing -----------------------------------------------------

    def gain(self):
        """The Gain dialog, and what a gain does to the analysis.

        6 dB *off* rather than on: this clip peaks at -3.7 dBFS, so adding 6 dB
        would clip it, and a clipping warning is not what this step is showing.
        The gain is taken back off at the end, so every later step sees the
        audio as it was loaded.
        """
        print("gain: dialog + result")
        session = self.session
        # Finishing an analysis rewinds the playhead; the steps after this one
        # were captured with it where playback left it, so put it back.
        playhead = session.current_playback_time

        def type_gain(dialog):
            box = dialog.findChild(QtWidgets.QDoubleSpinBox)
            if box is not None:
                box.setValue(-6.0)

        self._save_with_dialog("15_gain_dialog.png", session.handle_set_gain,
                               before_grab=type_gain)

        # The dialog above was rejected, so apply the same figure directly to
        # get the result shot -- the whole recording, as no selection is up.
        session.apply_gain(0.0, float('inf'), -6.0)
        self._wait_for_analysis()
        self._save("16_gain_result.png")

        session.apply_gain(0.0, float('inf'), 0.0)
        self._wait_for_analysis()
        session.current_playback_time = playhead
        session.update_playhead()

    def audio_editing(self):
        """Last on purpose: silencing destructively edits the audio buffer."""
        print("audio editing: selection + silence result")
        session = self.session
        session.hub.selection.set_range(8.0, 10.0)
        session.action_select.setChecked(True)
        self._save("13_select_band.png")

        session.handle_silence_selection()
        self._wait_for_analysis()
        self._save("14_silence_result.png")


if __name__ == "__main__":
    main()
