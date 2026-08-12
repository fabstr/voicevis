"""Picking the colour each data series is drawn in.

Only affects the colour a series is drawn in as *itself*. When a series is used
as a plot's colour dimension it still maps through viridis, because there the
colour carries a value rather than an identity.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

import SeriesRegistry as Registry

SWATCH_SIZE = QtCore.QSize(64, 22)

NOTE = ("These are the colours series are drawn in. A series used as a plot's "
        "colour dimension is always mapped through viridis instead.")


class _SwatchButton(QtWidgets.QPushButton):
    """A button showing one colour, which opens a colour picker when clicked."""

    colour_picked = QtCore.pyqtSignal(str)

    def __init__(self, colour: str, title: str, parent=None):
        super().__init__(parent)
        self._colour = colour
        self.setFixedSize(SWATCH_SIZE)
        self.setToolTip(f"Choose a colour for {title}")
        self._title = title
        self.clicked.connect(self._pick)
        self._repaint()

    @property
    def colour(self) -> str:
        return self._colour

    def set_colour(self, colour: str):
        self._colour = Registry.normalise_colour(colour)
        self._repaint()

    def _repaint(self):
        colour = QtGui.QColor(self._colour)
        # Keep the label readable whichever colour was chosen.
        text = "#000000" if colour.lightnessF() > 0.55 else "#ffffff"
        self.setText(self._colour[:7])
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._colour}; color: {text}; "
            f"border: 1px solid gray; font-family: monospace; }}"
        )

    def _pick(self):
        chosen = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._colour), self, f"Colour for {self._title}")
        if chosen.isValid():
            self.set_colour(chosen.name())
            self.colour_picked.emit(self._colour)


class SeriesColourDialog(QtWidgets.QDialog):
    """Edits the series palette. Changes apply live; Cancel puts them back."""

    colours_changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Series Colours")
        self.setMinimumWidth(360)

        self._original = Registry.colour_overrides()
        self._swatches = {}

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        note = QtWidgets.QLabel(NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(line)

        grid = QtWidgets.QGridLayout()
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)

        for row, spec in enumerate(Registry.colourable_series()):
            grid.addWidget(QtWidgets.QLabel(spec.label), row, 0)

            swatch = _SwatchButton(Registry.colour_of(spec), spec.label)
            swatch.colour_picked.connect(
                lambda colour, key=spec.key: self._set_colour(key, colour))
            grid.addWidget(swatch, row, 1)
            self._swatches[spec.key] = swatch

            revert = QtWidgets.QPushButton("Default")
            revert.setToolTip(f"Back to {Registry.default_colour_of(spec)}")
            revert.clicked.connect(lambda _, key=spec.key: self._reset_one(key))
            grid.addWidget(revert, row, 2)

        layout.addStretch()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
                       ).clicked.connect(self._reset_all)
        layout.addWidget(buttons)

    # --- Editing ---------------------------------------------------------

    def _set_colour(self, key: str, colour: str):
        Registry.set_colour(key, colour)
        self.colours_changed.emit()

    def _reset_one(self, key: str):
        Registry.set_colour(key, None)
        self._swatches[key].set_colour(Registry.colour_of(key))
        self.colours_changed.emit()

    def _reset_all(self):
        Registry.reset_colours()
        for key, swatch in self._swatches.items():
            swatch.set_colour(Registry.colour_of(key))
        self.colours_changed.emit()

    def reject(self):
        """Cancel: put the palette back the way it was."""
        Registry.apply_colour_overrides(self._original)
        self.colours_changed.emit()
        super().reject()
