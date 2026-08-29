"""Mapping a third data dimension onto a colour map.

``pg.ColorMap.map`` expects values in 0..1. The previous code passed raw feature
values straight in, so any series whose values exceed 1 -- weight, for instance --
saturated to the top colour and the plot came out a single flat shade. Everything
here normalises first, across the span the colour bar is labelled with.

Which map a plot runs its colour dimension through is part of its configuration,
so every function taking colour takes the map's name. The spectrogram background
is not a colour dimension and keeps viridis whatever the plot is set to.
"""

import logging
from typing import Tuple

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


def normalise_to(values: np.ndarray, low: float, high: float) -> np.ndarray:
    """Scale ``values`` into 0..1 across an explicit span, clamping outside it.

    The span is the colour source's registry range, not the range its data
    happens to cover. That is what makes a colour mean the same thing from one
    recording to the next, and from one plot to another -- the same reason a
    radar spoke is scaled by the registry range rather than by its data. It
    also lets a colour bar be labelled before any audio is loaded, since the
    scale no longer depends on what has been analysed.
    """
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values

    low, high = float(low), float(high)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros_like(values)

    normalised = (np.nan_to_num(values, nan=low) - low) / (high - low)
    return np.clip(normalised, 0.0, 1.0)


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


#: Layout column the first colour bar goes in, with later ones to its right.
#:
#: Well clear of ``MultiAxisLayer``, which stacks an extra Y axis per series
#: from column 3 outwards. The two could not previously collide -- a colour
#: dimension needed a single series and separate axes needed several -- but a
#: colour dimension per series means one plot can now want both at once.
COLOUR_BAR_COLUMN = 30


def make_colour_bar(plot_item, label: str = "",
                    name: str = DEFAULT_COLOUR_MAP,
                    position: int = 0,
                    span: Tuple[float, float] = (0.0, 1.0)) -> pg.ColorBarItem:
    """Attach a colour bar to the right of ``plot_item``.

    ``position`` is its place in the row of bars, one per coloured series, and
    ``span`` the range its ticks are labelled over -- the colour source's
    registry range, fixed, so the bar is right from the moment it appears
    rather than reading 0..1 until some data turns up.

    The label goes on the axis rather than through ``ColorBarItem(label=...)``:
    the constructor draws its own, so setting both leaves the bar labelled
    twice as soon as anything relabels it.
    """
    bar = pg.ColorBarItem(values=span, colorMap=colour_map(name), width=15,
                          interactive=False)
    plot_item.layout.addItem(bar, 2, COLOUR_BAR_COLUMN + position)
    set_colour_bar_label(bar, label)
    _fit_axis_to_its_ticks(bar)
    return bar


def _fit_axis_to_its_ticks(bar: pg.ColorBarItem):
    """Let the bar's axis be as wide as it needs, rather than always 45px.

    ``ColorBarItem`` fixes the axis width at 45 whatever the ticks read. The
    label is then placed against the right edge of that fixed width, so a bar
    labelled 0..10 carries 16px of nothing between its numbers and its label,
    while one labelled 0..3500 is left with barely any -- the same number is
    too generous and too mean depending on the colour source. Releasing the
    fixed width sizes the axis to its own tick text, which closes the gap to
    about 4px and widens the crowded case instead of squeezing it.

    The label item's 4px document margin is padding on top of that gap, and is
    dropped for the same reason. It survives a later ``setHtml``, so setting it
    once here holds for every relabelling.
    """
    axis = bar.getAxis('right')
    axis.label.document().setDocumentMargin(0)
    axis.setWidth(None)


def set_colour_bar_label(bar: pg.ColorBarItem, label: str):
    bar.getAxis('right').setLabel(label)


def set_colour_bar_map(bar: pg.ColorBarItem, name: str):
    """Repaint an existing bar in another map, leaving its place in the row."""
    bar.setColorMap(colour_map(name))
