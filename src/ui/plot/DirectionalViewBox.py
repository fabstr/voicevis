"""A ViewBox with axis-locked rubber-band zoom and a measurement tool.

The axis lock is applied *inside the drag handler* rather than by overriding
``setRange``. The previous implementation overrode ``setRange`` and, whenever
``zoom_axis`` was ``'y'``, replaced any requested X range with the current one.
Since ``setXRange`` funnels through ``setRange``, that silently discarded every
programmatic X update -- axis synchronisation, the recording sliding window,
playback paging and reset-zoom -- for as long as the zoom-Y tool was active.
"""

import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

MODE_PAN = None
MODE_ZOOM_X = "zoom_x"
MODE_ZOOM_Y = "zoom_y"
MODE_MEASURE = "measure"
MODE_SELECT = "select"


def format_time_delta(dx: float) -> str:
    if dx >= 60:
        return f"{int(dx // 60):02d}:{dx % 60:06.2f}"
    return f"{dx:.3f}s"


def time_measure_formatter(x0: float, x1: float, y0: float, y1: float) -> str:
    return f"Δt: {format_time_delta(x1 - x0)}\nΔy: {y1 - y0:.3f}"


def transposed_time_measure_formatter(x0: float, x1: float, y0: float, y1: float) -> str:
    """For plots with time on the Y axis."""
    return f"Δx: {x1 - x0:.3f}\nΔt: {format_time_delta(y1 - y0)}"


def plain_measure_formatter(x0: float, x1: float, y0: float, y1: float) -> str:
    return f"Δx: {x1 - x0:.3f}\nΔy: {y1 - y0:.3f}"


def log_x_measure_formatter(x0: float, x1: float, y0: float, y1: float) -> str:
    """For axes holding log10 values -- report the delta in real units."""
    return f"Δx: {10 ** x1 - 10 ** x0:.1f}\nΔy: {y1 - y0:.3f}"


class DirectionalViewBox(pg.ViewBox):
    """Constrains rubber-band zoom to one axis, measures deltas, and selects."""

    #: The rectangle dragged out in select mode, in view coordinates. The cell
    #: takes whichever axis is time.
    sigSelectionDragged = QtCore.pyqtSignal(object)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.zoom_axis = None
        self.measure_mode = False
        self.select_mode = False
        self.select_start_pos = None
        self.measure_start_pos = None
        #: Callable (x0, x1, y0, y1) -> str used for the measurement readout.
        self.measure_formatter = time_measure_formatter

        self.measure_rect = QtWidgets.QGraphicsRectItem()
        self.measure_rect.setPen(pg.mkPen('y', width=2, style=QtCore.Qt.PenStyle.DashLine))
        self.addItem(self.measure_rect, ignoreBounds=True)
        self.measure_rect.setVisible(False)

        self.measure_text = pg.TextItem(color='y', anchor=(0, 1), fill=pg.mkBrush(0, 0, 0, 150))
        self.addItem(self.measure_text, ignoreBounds=True)
        self.measure_text.setVisible(False)

        #: Where the context menu was opened, in view coordinates. Menu actions
        #: are triggered long after the click, so the position has to be kept.
        self.last_context_point = None

    def raiseContextMenu(self, ev):
        self.last_context_point = self.mapSceneToView(ev.scenePos())
        return super().raiseContextMenu(ev)

    # --- Tool mode -------------------------------------------------------

    def set_tool_mode(self, mode):
        """Switch between pan, single-axis zoom, measure and select."""
        self.measure_mode = (mode == MODE_MEASURE)
        self.select_mode = (mode == MODE_SELECT)

        if mode == MODE_ZOOM_X:
            self.zoom_axis = 'x'
            self.setMouseMode(pg.ViewBox.RectMode)
        elif mode == MODE_ZOOM_Y:
            self.zoom_axis = 'y'
            self.setMouseMode(pg.ViewBox.RectMode)
        elif mode in (MODE_MEASURE, MODE_SELECT):
            self.zoom_axis = None
        else:
            self.zoom_axis = None
            self.setMouseMode(pg.ViewBox.PanMode)

        if not self.measure_mode:
            self.clear_measurement()

        # Measure and select suppress the default pan/zoom handlers while still
        # receiving drag events -- this ordering is what makes them work.
        interactive = not (self.measure_mode or self.select_mode)
        self.setMouseEnabled(x=interactive, y=interactive)

    def clear_measurement(self):
        self.measure_start_pos = None
        self.measure_rect.setVisible(False)
        self.measure_text.setVisible(False)

    # --- Mouse handling --------------------------------------------------

    def mouseDragEvent(self, ev, axis=None):
        if self.measure_mode:
            self._measure_drag(ev)
            return

        if self.select_mode:
            self._select_drag(ev)
            return

        if (self.zoom_axis is not None
                and axis is None
                and ev.button() == QtCore.Qt.MouseButton.LeftButton
                and self.state['mouseMode'] == pg.ViewBox.RectMode):
            ev.accept()
            if ev.isFinish():
                self.rbScaleBox.hide()
                rect = QtCore.QRectF(pg.Point(ev.buttonDownPos(ev.button())), pg.Point(ev.pos()))
                self._apply_locked_rect(self.childGroup.mapRectFromParent(rect).normalized())
            else:
                self.updateScaleBox(ev.buttonDownPos(), ev.pos())
            return

        super().mouseDragEvent(ev, axis)

    def wheelEvent(self, ev, axis=None):
        """Scroll-wheel zoom obeys the axis lock the same way rubber-band does.

        ``pg.ViewBox`` scales both axes unless it is told which one to use, so
        the locked axis is passed down as the axis index the base class expects.
        """
        if self.zoom_axis is not None and axis is None:
            axis = 0 if self.zoom_axis == 'x' else 1
        super().wheelEvent(ev, axis)

    def _apply_locked_rect(self, rect):
        """Zoom to ``rect`` along the locked axis only, leaving the other alone."""
        if self.zoom_axis == 'x' and rect.width() > 0:
            self.setRange(xRange=(rect.left(), rect.right()), padding=0)
        elif self.zoom_axis == 'y' and rect.height() > 0:
            self.setRange(yRange=(rect.top(), rect.bottom()), padding=0)

    def updateScaleBox(self, p1, p2):
        """Stretch the rubber band across the axis that is not being zoomed."""
        bounds = self.boundingRect()
        if self.zoom_axis == 'x':
            p1 = QtCore.QPointF(p1.x(), bounds.top())
            p2 = QtCore.QPointF(p2.x(), bounds.bottom())
        elif self.zoom_axis == 'y':
            p1 = QtCore.QPointF(bounds.left(), p1.y())
            p2 = QtCore.QPointF(bounds.right(), p2.y())
        super().updateScaleBox(p1, p2)

    def _select_drag(self, ev):
        """Drag out a time range. The cell decides which axis is time."""
        ev.accept()
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        if ev.isStart():
            self.select_start_pos = self.mapSceneToView(ev.buttonDownScenePos())
            return
        if self.select_start_pos is None:
            return

        current = self.mapSceneToView(ev.scenePos())
        left, right = sorted((self.select_start_pos.x(), current.x()))
        bottom, top = sorted((self.select_start_pos.y(), current.y()))
        # Emitted as it moves as well as at the end, so the highlight follows
        # the cursor rather than appearing only on release.
        self.sigSelectionDragged.emit(QtCore.QRectF(left, bottom, right - left, top - bottom))

        if ev.isFinish():
            self.select_start_pos = None

    def _measure_drag(self, ev):
        ev.accept()
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        if ev.isStart():
            self.measure_start_pos = self.mapSceneToView(ev.buttonDownScenePos())
            self.measure_rect.setVisible(True)
            self.measure_text.setVisible(True)
            return

        if ev.isFinish() or self.measure_start_pos is None:
            # Leave the readout on screen until the tool is switched off.
            return

        current = self.mapSceneToView(ev.scenePos())
        left, right = sorted((self.measure_start_pos.x(), current.x()))
        bottom, top = sorted((self.measure_start_pos.y(), current.y()))

        self.measure_rect.setRect(left, bottom, right - left, top - bottom)
        self.measure_text.setText(self.measure_formatter(left, right, bottom, top))
        self.measure_text.setPos(right, top)
