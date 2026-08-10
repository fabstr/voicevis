"""Palette-derived colours for plots.

Uses only public pyqtgraph API. The previous implementation wrote
``axis._gridPen`` and ``axis.picture = None`` directly; both are redundant
because ``AxisItem.setPen()`` already invalidates the cached picture and the
grid is drawn with the axis pen.
"""

from dataclasses import dataclass

import pyqtgraph as pg
from PyQt6 import QtGui, QtWidgets

GRID_ALPHA = 0.3
TITLE_SIZE = "12pt"


@dataclass(frozen=True)
class PlotTheme:
    background: QtGui.QColor
    text: QtGui.QColor
    base: QtGui.QColor
    highlight: QtGui.QColor

    @classmethod
    def from_palette(cls, palette=None) -> "PlotTheme":
        palette = palette or QtWidgets.QApplication.palette()
        role = QtGui.QPalette.ColorRole
        return cls(
            background=palette.color(role.Window),
            text=palette.color(role.WindowText),
            base=palette.color(role.Base),
            highlight=palette.color(role.Highlight),
        )

    # --- Derived pens ----------------------------------------------------

    def playhead_pen(self):
        return pg.mkPen(self.text, width=2)

    def accent_pen(self, width=1.0):
        return pg.mkPen(self.highlight, width=width)

    @staticmethod
    def marker_edge_pen():
        """The faint outline drawn around every scatter point."""
        return pg.mkPen(color=(128, 128, 128, 128), width=0.5)

    # --- Application -----------------------------------------------------

    def apply_to_plot(self, plot_widget, title: str = None):
        plot_widget.setBackground(self.background)

        plot_item = plot_widget.getPlotItem()
        for axis_name in ("bottom", "left"):
            axis = plot_item.getAxis(axis_name)
            if axis is None:
                continue
            axis.setPen(self.text)
            axis.setTextPen(self.text)

        plot_widget.showGrid(x=True, y=True, alpha=GRID_ALPHA)
        if title is not None:
            plot_item.setTitle(title, color=self.text.name(), size=TITLE_SIZE)

    def container_stylesheet(self, object_name: str) -> str:
        return (f"#{object_name} {{ border: 1px solid gray; margin: 2px; "
                f"background-color: {self.background.name()}; }}")

    def input_stylesheet(self) -> str:
        """Shared styling for the combo boxes and buttons in a plot's top bar."""
        return f"""
            QToolButton, QComboBox, QLineEdit {{
                border: 1px solid gray; padding: 2px;
                background-color: {self.background.name()}; color: {self.text.name()};
            }}
            QToolButton:disabled, QComboBox:disabled, QCheckBox:disabled {{ color: gray; }}
            QCheckBox {{ color: {self.text.name()}; }}
            QMenu {{
                background-color: {self.base.name()}; color: {self.text.name()};
            }}
            QMenu::item:selected {{ background-color: {self.highlight.name()}; }}
        """
