"""Base class for the drawing strategies a plot cell can swap between.

A renderer owns the pyqtgraph items inside one plot and knows how to fill them
from the data hub. Which renderer a cell uses follows from its
:class:`~ui.plot.PlotConfig.PlotConfig`, so changing what a plot shows never
requires rebuilding the cell around it.
"""

import abc

import numpy as np
import pyqtgraph as pg

import SeriesRegistry as Registry
from ui.plot.ColourMapping import make_colour_bar, normalise_to, rgba
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
    #: Whether the X and Y axis items -- and the grid -- are worth showing.
    shows_axes = True
    #: Whether one data unit must be the same length on both axes, so that a
    #: circle stays a circle however the cell is resized.
    locks_aspect = False
    #: Whether target ranges are drawn as bands across the axes. A plot whose
    #: axes are not the quantities themselves draws its own instead.
    supports_target_bands = True

    def __init__(self, plot_item, config, hub):
        self.plot_item = plot_item
        self.config = config
        self.hub = hub
        self.items = []
        #: One bar per drawn series that has a colour dimension, by series key.
        self.colour_bars = {}
        self._seen_revision = -1

    # --- Lifecycle -------------------------------------------------------

    def attach(self):
        self._build_items()
        self._sync_colour_bars()
        self.on_data_changed(force=True)

    def detach(self):
        self._clear_items()
        self._remove_colour_bars()

    def set_config(self, config):
        """Adopt a new config of the same kind, rebuilding items in place."""
        self.config = config
        self.rebuild()

    def rebuild(self):
        """Recreate the items, e.g. after the series palette changed."""
        self._clear_items()
        self._build_items()
        self._sync_colour_bars()
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
        for bar in self.colour_bars.values():
            axis = bar.getAxis('right')
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

    @staticmethod
    def trail_alpha(times: np.ndarray, current_time: float, trail_time: float):
        """Opacity per point, fading linearly to nothing at the trail's age."""
        if trail_time <= 0:
            return np.full(len(times), 255, dtype=int)
        age = np.clip((current_time - times) / trail_time, 0.0, 1.0)
        return (255 * (1.0 - age)).astype(int)

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

    def _sync_colour_bars(self):
        """One bar per coloured series, in item order, rebuilt from scratch.

        Rebuilt rather than reused: every drawn series has a map of its own
        now, so a bar's gradient, its label, its span and its place in the row
        can all change at once -- and the items it belongs to are being
        recreated around it anyway.

        Each bar is labelled over its source's registry range and never
        touched again: nothing about the scale depends on the data, so there
        is no moment at which it is out of date.
        """
        self._remove_colour_bars()
        if not self.config.colour_scales:
            return

        for key in self.config.drawn_keys():
            source = self.config.colour_source_spec(key)
            if source is None:
                continue
            self.colour_bars[key] = make_colour_bar(
                self.plot_item, self._colour_bar_label(key, source),
                self.config.colour_map_of(key), position=len(self.colour_bars),
                span=(source.default_min, source.default_max))

    def _colour_bar_label(self, key: str, source) -> str:
        """What a bar measures, and which series it colours when that could be
        in doubt. On a plot drawing one thing there is nothing to disambiguate.
        """
        if len(self.config.drawn_keys()) < 2:
            return source.label
        drawn = Registry.get(key)
        return f"{drawn.label}: {source.label}" if drawn else source.label

    def _remove_colour_bars(self):
        for bar in self.colour_bars.values():
            self.plot_item.layout.removeItem(bar)
            scene = bar.scene()
            if scene is not None:
                scene.removeItem(bar)
        self.colour_bars = {}

    def _colour_values(self, times: np.ndarray, key: str):
        """Colours for ``times``, sampled from whatever colours ``key``.

        Returns None when that series has no colour dimension. Values are
        scaled across the source's registry range -- not across the data's own
        span -- so a colour means the same thing in every plot and in every
        recording, and the bar's ticks stay true whatever has been analysed.
        """
        spec = self.config.colour_source_spec(key)
        if spec is None or len(times) == 0:
            return None

        z_x, z_y = self.hub.get_xy(spec.key)
        if len(z_x) == 0:
            return None

        sampled = np.interp(times, z_x, z_y)
        normalised = normalise_to(sampled, spec.default_min, spec.default_max)
        return rgba(normalised, self.config.colour_map_of(key))
