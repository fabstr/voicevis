from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

class AnnotationMarker(pg.ScatterPlotItem):
    def __init__(self, x, y, text, plot_name, plot_widget, app_ref):
        # Draw a yellow star at the exact coordinates
        super().__init__(
            x=[x], y=[y],
            symbol='star', size=20, pen=pg.mkPen('k'), brush=pg.mkBrush('w')
        )
        self.x_val = x
        self.y_val = y
        self.text_val = text
        self.plot_name = plot_name
        self.plot_widget = plot_widget
        self.app_ref = app_ref

        # Native Qt ToolTip: Automatically displays text when hovered!
        self.setToolTip(text)
