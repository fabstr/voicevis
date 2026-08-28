"""Mapping a third data dimension onto a colour map.

``pg.ColorMap.map`` expects values in 0..1. The previous code passed raw feature
values straight in, so any series whose values exceed 1 -- weight, for instance --
saturated to the top colour and the plot came out a single flat shade. Everything
here normalises first, and reports the range it used so a colour bar can be
labelled to match.

Which map a plot runs its colour dimension through is part of its configuration,
so every function taking colour takes the map's name. The spectrogram background
is not a colour dimension and keeps viridis whatever the plot is set to.
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pyqtgraph as pg

#: Selectable maps, in menu order: (key, label). All three ship inside
#: pyqtgraph (``colors/maps/``), so nothing here needs matplotlib at runtime.
COLOUR_MAPS = (("viridis", "Viridis"), ("plasma", "Plasma"), ("turbo", "Turbo"))
COLOUR_MAP_KEYS = tuple(key for key, _ in COLOUR_MAPS)
DEFAULT_COLOUR_MAP = "viridis"

_COLOURMAPS = {}


def colour_map(name: str = DEFAULT_COLOUR_MAP) -> pg.ColorMap:
    """The colour map called ``name``, cached.

    An unrecognised name falls back to the default rather than raising: a name
    reaches here from a layout file, and one bad string should not cost the user
    their plot.
    """
    if name not in COLOUR_MAP_KEYS:
        logging.warning("Unknown colour map %r; using %r", name, DEFAULT_COLOUR_MAP)
        name = DEFAULT_COLOUR_MAP
    if name not in _COLOURMAPS:
        _COLOURMAPS[name] = pg.colormap.get(name)
    return _COLOURMAPS[name]


def viridis() -> pg.ColorMap:
    """The default map, for the things that are not a plot's colour dimension."""
    return colour_map(DEFAULT_COLOUR_MAP)


def normalise(values: np.ndarray, reference: Optional[np.ndarray] = None
              ) -> Tuple[np.ndarray, float, float]:
    """Scale ``values`` into 0..1 using the span of ``reference``.

    ``reference`` defaults to ``values``. Passing the whole series while
    ``values`` is a moving window keeps colours stable as the window slides.
    Returns the normalised array plus the (low, high) span it was scaled by.
    """
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values, 0.0, 1.0

    source = np.asarray(reference if reference is not None else values, dtype=float)
    source = source[np.isfinite(source)]
    if source.size == 0:
        return np.zeros_like(values), 0.0, 1.0

    lo, hi = float(np.min(source)), float(np.max(source))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(values), lo, lo + 1.0

    normalised = (np.nan_to_num(values, nan=lo) - lo) / (hi - lo)
    return np.clip(normalised, 0.0, 1.0), lo, hi


def rgba(normalised: np.ndarray, name: str = DEFAULT_COLOUR_MAP) -> np.ndarray:
    """An (N, 4) uint8 colour array for values already scaled to 0..1."""
    if np.size(normalised) == 0:
        return np.zeros((0, 4), dtype=np.uint8)
    return colour_map(name).map(normalised, mode='byte')


def brushes(colours: np.ndarray, alpha=None):
    """Per-point brushes, optionally overriding the alpha channel."""
    if alpha is None:
        return [pg.mkBrush(int(r), int(g), int(b), int(a)) for r, g, b, a in colours]
    return [pg.mkBrush(int(r), int(g), int(b), int(a))
            for (r, g, b, _), a in zip(colours, alpha)]


def solid_brushes(colour, alpha: np.ndarray):
    """Per-point brushes of one colour with varying alpha (trail fading)."""
    base = pg.mkColor(colour)
    return [pg.mkBrush(base.red(), base.green(), base.blue(), int(a)) for a in alpha]


def make_colour_bar(plot_item, label: str = "",
                    name: str = DEFAULT_COLOUR_MAP) -> pg.ColorBarItem:
    """Attach a colour bar to the right of ``plot_item``.

    The label goes on the axis rather than through ``ColorBarItem(label=...)``:
    the constructor draws its own, so setting both leaves the bar labelled
    twice as soon as anything relabels it.
    """
    bar = pg.ColorBarItem(values=(0.0, 1.0), colorMap=colour_map(name), width=15,
                          interactive=False)
    plot_item.layout.addItem(bar, 2, 4)
    set_colour_bar_label(bar, label)
    return bar


def set_colour_bar_label(bar: pg.ColorBarItem, label: str):
    bar.getAxis('right').setLabel(label)


def set_colour_bar_map(bar: pg.ColorBarItem, name: str):
    """Repaint an existing bar in another map.

    A bar outlives a change of colour map -- ``_sync_colour_bar`` reuses it --
    so without this the gradient in the legend would disagree with the points.
    """
    bar.setColorMap(colour_map(name))
