"""A scatter item that survives PlotItem's curve-wide settings.

``PlotItem`` tracks everything implementing the ``plotData`` interface in
``self.curves`` -- which includes ``ScatterPlotItem`` -- and then calls
``setDownsampling`` and ``setClipToView`` on all of them. ``ScatterPlotItem`` has
neither method, so a plain one raises ``AttributeError`` the moment anything
touches those plot-wide settings.

Both are no-ops here. A scatter is never subsetted for display, which is exactly
why per-point brushes belong on one: ``PlotDataItem`` clips and downsamples its
x/y arrays but passes the brush list through whole, and the scatter underneath
then rejects the mismatched lengths.
"""

import pyqtgraph as pg


class ScatterItem(pg.ScatterPlotItem):

    def setDownsampling(self, ds=None, auto=None, method=None):
        """Ignored: a scatter draws every point it is given."""

    def setClipToView(self, clip=None):
        """Ignored: a scatter draws every point it is given."""
