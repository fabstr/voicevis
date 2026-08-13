"""One scale per series, instead of all of them sharing an axis.

A plot of F1, F2 and F3 against time normally puts all three on one axis, so
they have to share a range wide enough for the highest — which squashes the
lowest into a band at the bottom. Turning on separate axes gives each series its
own scale, drawn as an extra axis alongside the first.

The extra axes are ordinary pyqtgraph view boxes stacked over the plot's own,
linked on the *other* axis so panning and zooming time still moves everything
together.
"""

import numpy as np
import pyqtgraph as pg

import SeriesRegistry as Registry

#: Headroom left above and below a series when scaling its own axis.
RANGE_MARGIN = 0.05

#: Where extra axes go, given which axis was split.
_SIDE = {'y': 'right', 'x': 'top'}


def _move(item, source, target):
    """Move a plot item from one view box to another.

    Removing an item leaves it briefly without a parent, and pyqtgraph reacts to
    the reparenting by asking the item to redraw. With clipping or downsampling
    on it looks for its view box, finds the enclosing widget instead and raises
    ``AttributeError: autoRangeEnabled``. Both are switched off across the move
    and restored afterwards, when the item has a view box again.
    """
    clip = item.opts.get('clipToView') if hasattr(item, 'opts') else None
    downsample = item.opts.get('autoDownsample') if hasattr(item, 'opts') else None
    restore = hasattr(item, 'setClipToView') and (clip or downsample)

    if restore:
        item.setClipToView(False)
        item.setDownsampling(auto=False)

    source.removeItem(item)
    target.addItem(item)

    if restore:
        item.setClipToView(bool(clip))
        item.setDownsampling(auto=bool(downsample), method='peak')


class MultiAxisLayer:
    """Extra view boxes and axes for the second and later series."""

    def __init__(self, plot_item):
        self.plot_item = plot_item
        self._extras = []          # (view_box, axis_item)
        self._items = []           # the plot items moved out of the main box
        self._specs = []
        self._hub = None
        self._axis = None
        self.plot_item.getViewBox().sigResized.connect(self._follow_geometry)

    @property
    def active(self) -> bool:
        return bool(self._extras)

    # --- Building --------------------------------------------------------

    def apply(self, items, specs, axis, enabled, hub=None):
        """Give each item after the first its own axis, or undo that.

        ``items`` and ``specs`` are the renderer's plot items and the series
        they draw, in the same order. ``axis`` is the one holding several
        series -- 'y' normally, 'x' on a transposed plot.
        """
        self.clear()
        if not enabled or axis not in _SIDE or len(items) < 2:
            return

        self._axis = axis
        self._specs = list(specs)
        self._hub = hub
        main = self.plot_item.getViewBox()

        for offset, (item, spec) in enumerate(zip(items[1:], specs[1:]), start=1):
            view_box = pg.ViewBox()
            axis_item = pg.AxisItem(orientation=_SIDE[axis])
            axis_item.linkToView(view_box)
            axis_item.setLabel(spec.axis_label, color=Registry.colour_of(spec))

            # Stacked outwards from the plot: right of the first axis, or above.
            row, column = (2, 2 + offset) if axis == 'y' else (1 - offset, 1)
            self.plot_item.layout.addItem(axis_item, row, column)
            self.plot_item.scene().addItem(view_box)

            # Share the axis that is *not* being split, so the two boxes stay
            # aligned when time is panned or zoomed.
            if axis == 'y':
                view_box.setXLink(main)
            else:
                view_box.setYLink(main)

            _move(item, main, view_box)
            self._extras.append((view_box, axis_item))
            self._items.append(item)

        self.reset_ranges()
        self._follow_geometry()

    def reset_ranges(self):
        """Scale every axis to its own series.

        Sharing one axis means sharing one range, which is the thing separate
        axes exist to avoid -- and the registry ranges are often identical
        (F1, F2 and F3 all read 0-3500), so falling back to those would make
        the option look like it did nothing. The data wins where there is any.
        """
        if not self._extras:
            return

        main = self.plot_item.getViewBox()
        for view_box, spec in zip([main] + [vb for vb, _ in self._extras], self._specs):
            self._set_range(view_box, self._range_for(spec), self._axis)

    def clear(self):
        """Put every item back on the plot's own axes."""
        main = self.plot_item.getViewBox()

        for item, view_box in zip(self._items, [vb for vb, _ in self._extras]):
            _move(item, view_box, main)
        self._items = []

        for view_box, axis_item in self._extras:
            self.plot_item.layout.removeItem(axis_item)
            axis_item.setParentItem(None)
            scene = view_box.scene()
            if scene is not None:
                scene.removeItem(view_box)
        self._extras = []
        self._specs = []
        self._axis = None

    # --- Geometry --------------------------------------------------------

    def _follow_geometry(self):
        """Keep the extra boxes exactly over the plot's own."""
        if not self._extras:
            return
        rect = self.plot_item.getViewBox().sceneBoundingRect()
        for view_box, _ in self._extras:
            view_box.setGeometry(rect)
            view_box.linkedViewChanged(self.plot_item.getViewBox(),
                                       view_box.XAxis if self._axis == 'y' else view_box.YAxis)

    def _range_for(self, spec):
        """The span a series actually occupies, or its registry range."""
        if self._hub is not None:
            _, values = self._hub.get_xy(spec.key)
            if len(values):
                low, high = float(np.min(values)), float(np.max(values))
                if high > low:
                    margin = (high - low) * RANGE_MARGIN
                    return low - margin, high + margin
        return spec.default_min, spec.default_max

    @staticmethod
    def _set_range(view_box, span, axis):
        low, high = span
        if axis == 'y':
            view_box.setYRange(low, high, padding=0)
        else:
            view_box.setXRange(low, high, padding=0)

    # --- Appearance ------------------------------------------------------

    def apply_theme(self, theme):
        for _, axis_item in self._extras:
            axis_item.setPen(theme.text)
            axis_item.setTextPen(theme.text)
