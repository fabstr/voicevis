"""Base class for the drawing strategies a plot cell can swap between.

A renderer owns the pyqtgraph items inside one plot and knows how to fill them
from the data hub. Which renderer a cell uses follows from its
:class:`~ui.plot.PlotConfig.PlotConfig`, so changing what a plot shows never
requires rebuilding the cell around it.
"""

import abc

import numpy as np
import pyqtgraph as pg

from ui.plot.ColourMapping import make_colour_bar, normalise, rgba, set_colour_bar_label
from ui.plot.DirectionalViewBox import plain_measure_formatter


class PlotRenderer(abc.ABC):
    """Draws one plot's data. Subclasses decide what the items are."""

    #: Whether this plot's X axis is time and should join the sync group.
    follows_time_axis = False
    #: Whether a playhead line makes sense here.
    shows_playhead = False
    #: Whether clicking should seek the transport.
    supports_seek = False
    #: Whether a spectrogram background can be drawn behind this plot.
    supports_spectrogram = False

    def __init__(self, plot_item, config, hub):
        self.plot_item = plot_item
        self.config = config
        self.hub = hub
        self.items = []
        self.colour_bar = None
        self._seen_revision = -1

    # --- Lifecycle -------------------------------------------------------

    def attach(self):
        self._build_items()
        self._sync_colour_bar()
        self.on_data_changed(force=True)

    def detach(self):
        self._clear_items()
        self._remove_colour_bar()

    def set_config(self, config):
        """Adopt a new config of the same kind, rebuilding items in place."""
        self.config = config
        self.rebuild()

    def rebuild(self):
        """Recreate the items, e.g. after the series palette changed."""
        self._clear_items()
        self._build_items()
        self._sync_colour_bar()
        self.on_data_changed(force=True)

    # --- Updates ---------------------------------------------------------

    def on_data_changed(self, force=False):
        """Re-read everything from the hub. Cheap when nothing has changed."""
        if not force and self._seen_revision == self.hub.revision:
            return
        self._seen_revision = self.hub.revision
        self._refresh(self.hub.current_time)

    def on_time_changed(self, current_time: float):
        """Called every frame. Must stay cheap."""

    def set_point_size(self, size: int):
        for item in self.items:
            self._apply_point_size(item, size)

    def apply_theme(self, theme):
        if self.colour_bar is not None:
            axis = self.colour_bar.getAxis('right')
            axis.setPen(theme.text)
            axis.setTextPen(theme.text)

    # --- Axis / interaction hooks ---------------------------------------

    def axis_items(self) -> dict:
        """The axis items this plot needs, keyed by side.

        Both sides are always returned so that swapping renderers -- or moving
        time from one axis to the other -- replaces every axis that was
        specialised by the previous configuration.
        """
        return {'bottom': pg.AxisItem(orientation='bottom'),
                'left': pg.AxisItem(orientation='left')}

    @staticmethod
    def x_transform(values):
        """Map data-space X values into view-space. Identity by default."""
        return values

    @staticmethod
    def x_inverse(values):
        """The inverse of :meth:`x_transform`."""
        return values

    measure_formatter = staticmethod(plain_measure_formatter)

    # --- To implement ----------------------------------------------------

    @abc.abstractmethod
    def _build_items(self):
        """Create the pyqtgraph items and append them to ``self.items``."""

    @abc.abstractmethod
    def _refresh(self, current_time: float):
        """Push current hub data into the items."""

    def _apply_point_size(self, item, size: int):
        """Resize one item's markers."""

    # --- Helpers for subclasses -----------------------------------------

    def _add(self, item):
        self.plot_item.addItem(item)
        self.items.append(item)
        return item

    def _clear_items(self):
        for item in self.items:
            self.plot_item.removeItem(item)
        self.items = []

    def _sync_colour_bar(self):
        spec = self.config.colour_spec()
        if spec is None:
            self._remove_colour_bar()
            return
        if self.colour_bar is None:
            self.colour_bar = make_colour_bar(self.plot_item, spec.label)
        else:
            set_colour_bar_label(self.colour_bar, spec.label)

    def _remove_colour_bar(self):
        if self.colour_bar is None:
            return
        self.plot_item.layout.removeItem(self.colour_bar)
        scene = self.colour_bar.scene()
        if scene is not None:
            scene.removeItem(self.colour_bar)
        self.colour_bar = None

    def _colour_values(self, times: np.ndarray):
        """Viridis colours for ``times``, sampled from the colour series.

        Returns None when this plot has no colour dimension. Normalisation uses
        the whole colour series so colours do not shift as a window slides.
        """
        spec = self.config.colour_spec()
        if spec is None or len(times) == 0:
            return None

        z_x, z_y = self.hub.get_xy(spec.key)
        if len(z_x) == 0:
            return None

        sampled = np.interp(times, z_x, z_y)
        normalised, low, high = normalise(sampled, z_y)
        if self.colour_bar is not None:
            self.colour_bar.setLevels((low, high))
        return rgba(normalised)
