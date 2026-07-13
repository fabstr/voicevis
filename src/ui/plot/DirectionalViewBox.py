from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

class DirectionalViewBox(pg.ViewBox):
    """
    A custom ViewBox that intercepts the RectMode scaling to force
    true 1D visual selection and 1D zooming. Also supports a measurement
    mode to calculate delta X and delta Y without Pythagorean distances.
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.zoom_axis = None
        self.measure_mode = False
        self.measure_start_pos = None

        # Measurement Visuals
        self.measure_rect = QtWidgets.QGraphicsRectItem()
        pen = pg.mkPen('y', width=2, style=QtCore.Qt.PenStyle.DashLine)
        self.measure_rect.setPen(pen)
        self.addItem(self.measure_rect, ignoreBounds=True)
        self.measure_rect.setVisible(False)

        self.measure_text = pg.TextItem(color='y', anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 150))
        self.addItem(self.measure_text, ignoreBounds=True)
        self.measure_text.setVisible(False)

    def mouseDragEvent(self, ev, axis=None):
        if self.measure_mode:
            ev.accept()
            if ev.button() == QtCore.Qt.MouseButton.LeftButton:
                if ev.isStart():
                    self.measure_start_pos = self.mapSceneToView(ev.buttonDownScenePos())
                    self.measure_rect.setVisible(True)
                    self.measure_text.setVisible(True)
                elif ev.isFinish():
                    # Leave the measurement visuals on screen until tool is disabled or a new drag starts
                    pass
                else:
                    if self.measure_start_pos is None:
                        return

                    current_pos = self.mapSceneToView(ev.scenePos())
                    x1, y1 = self.measure_start_pos.x(), self.measure_start_pos.y()
                    x2, y2 = current_pos.x(), current_pos.y()

                    left, right = min(x1, x2), max(x1, x2)
                    bottom, top = min(y1, y2), max(y1, y2)

                    self.measure_rect.setRect(left, bottom, right - left, top - bottom)

                    dx = right - left
                    dy = top - bottom

                    # Format delta X as mm:ss or raw seconds
                    mins = int(dx // 60)
                    secs = dx % 60
                    time_str = f"{mins:02d}:{secs:06.2f}" if dx >= 60 else f"{dx:.3f}s"

                    self.measure_text.setText(f"Δt: {time_str}\nΔy: {dy:.3f}")
                    # Keep the text in the top-right corner of the drag box
                    self.measure_text.setPos(right, top)
            return

        super().mouseDragEvent(ev, axis)

    def updateScaleBox(self, p1, p2):
        """Visually stretch the yellow selection box to span the locked axis."""
        if self.zoom_axis == 'x':
            y_min, y_max = self.boundingRect().top(), self.boundingRect().bottom()
            p1 = QtCore.QPointF(p1.x(), y_min)
            p2 = QtCore.QPointF(p2.x(), y_max)
        elif self.zoom_axis == 'y':
            x_min, x_max = self.boundingRect().left(), self.boundingRect().right()
            p1 = QtCore.QPointF(x_min, p1.y())
            p2 = QtCore.QPointF(x_max, p2.y())
        super().updateScaleBox(p1, p2)

    def setRange(self, rect=None, xRange=None, yRange=None, *args, **kwds):
        """Intercept the zoom application to only apply to the selected axis."""
        if self.zoom_axis is not None:
            if rect is not None:
                current_rect = self.viewRect()

                if self.zoom_axis == 'x':
                    rect = QtCore.QRectF(
                        rect.left(), current_rect.top(),
                        rect.width(), current_rect.height()
                    )
                elif self.zoom_axis == 'y':
                    rect = QtCore.QRectF(
                        current_rect.left(), rect.top(),
                        current_rect.width(), rect.height()
                    )
            else:
                if self.zoom_axis == 'x':
                    yRange = self.viewRange()[1]
                elif self.zoom_axis == 'y':
                    xRange = self.viewRange()[0]

        super().setRange(rect=rect, xRange=xRange, yRange=yRange, *args, **kwds)