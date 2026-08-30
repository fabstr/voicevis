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

#: Colour steps a colour dimension is quantised to before it becomes brushes.
#: A brush is cached per distinct colour and pyqtgraph caches a rendered marker
#: per distinct brush, so both caches only pay off if the colours repeat --
#: straight off a continuous map, a few thousand points are a few thousand
#: one-use colours. The maps ship 256 stops of their own, so rounding to as
#: many cannot be seen.
COLOUR_LEVELS = 256

#: Steps a trail's fade is quantised to, for the same reason. The fade is a
#: ramp over a couple of seconds and nobody can see 32 steps in it.
ALPHA_LEVELS = 32

_COLOURMAPS = {}

#: Brushes and pens by (r, g, b, a), so a colour is only built once.
_BRUSHES = {}
_PENS = {}


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
    """An (N, 4) uint8 colour array for values already scaled to 0..1.

    Quantised to :data:`COLOUR_LEVELS` first, so that however many points are
    coloured, they come out in a small set of repeated colours.
    """
    if np.size(normalised) == 0:
        return np.zeros((0, 4), dtype=np.uint8)
    return colour_map(name).map(_quantise(normalised, COLOUR_LEVELS), mode='byte')


def brushes(colours: np.ndarray, alpha=None):
    """Per-point brushes, optionally overriding the alpha channel.

    Points of the same colour share one brush rather than each getting a fresh
    one. A live recording rebuilds these lists many times a second, and
    building a QBrush per point was the most expensive thing the GUI thread
    did: at a hundred frames of audio a second, a minute of recording came to
    six thousand of them per redraw. Nothing here mutates a brush, so sharing
    is safe, and pyqtgraph's own marker cache is keyed by brush -- so the
    repeats pay off a second time when the points are drawn.
    """
    if alpha is None:
        return [_brush(r, g, b, a) for r, g, b, a in colours]
    return [_brush(r, g, b, a)
            for (r, g, b, _), a in zip(colours, _quantise_alpha(alpha))]


def solid_brushes(colour, alpha: np.ndarray):
    """Per-point brushes of one colour with varying alpha (trail fading)."""
    base = pg.mkColor(colour)
    return [_brush(base.red(), base.green(), base.blue(), a)
            for a in _quantise_alpha(alpha)]


def fade_pens(colour, alpha: np.ndarray, width: float = 0.5):
    """Per-point pens of one colour with varying alpha, cached like brushes."""
    base = pg.mkColor(colour)
    return [_pen(base.red(), base.green(), base.blue(), a, width)
            for a in _quantise_alpha(alpha)]


def _quantise(values: np.ndarray, levels: int) -> np.ndarray:
    """``values`` in 0..1 rounded to ``levels`` evenly spaced steps."""
    steps = float(levels - 1)
    return np.round(np.asarray(values, dtype=float) * steps) / steps


def _quantise_alpha(alpha) -> np.ndarray:
    """Opacities in 0..255 rounded to :data:`ALPHA_LEVELS` steps."""
    step = 255.0 / (ALPHA_LEVELS - 1)
    return np.round(np.asarray(alpha, dtype=float) / step) * step


def _brush(r, g, b, a):
    key = (int(r), int(g), int(b), int(a))
    brush = _BRUSHES.get(key)
    if brush is None:
        brush = _BRUSHES[key] = pg.mkBrush(*key)
    return brush


def _pen(r, g, b, a, width: float):
    key = (int(r), int(g), int(b), int(a), float(width))
    pen = _PENS.get(key)
    if pen is None:
        pen = _PENS[key] = pg.mkPen(color=key[:4], width=width)
    return pen


#: Layout column the first colour bar goes in, with later ones to its right.
#:
#: Well clear of ``MultiAxisLayer``, which stacks an extra Y axis per series
#: from column 3 outwards. The two could not previously collide -- a colour
#: dimension needed a single series and separate axes needed several -- but a
#: colour dimension per series means one plot can now want both at once.
COLOUR_BAR_COLUMN = 30

#: Width held open in that column for a plot that draws no colour bar at all.
#:
#: With nothing to its right the data area runs to the cell's own frame: the
#: last tick label is cut off by the border and the grid ends flush against it.
#: Deliberately much narrower than a bar and its axis -- turning the scales off
#: is how a plot buys that width back, so reserving all of it would make the
#: option do nothing. This is only enough for the overhanging tick label and
#: the options button in the corner.
BAR_CLEARANCE = 30


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


def reserve_bar_clearance(plot_item, reserve: bool):
    """Hold the first bar's column open at ``BAR_CLEARANCE``, or release it.

    A bar and its axis need more than this, so the reservation makes no
    difference while one is there. It is released anyway rather than left to be
    reasoned about the next time either number changes.
    """
    plot_item.layout.setColumnMinimumWidth(COLOUR_BAR_COLUMN,
                                           BAR_CLEARANCE if reserve else 0)


def set_colour_bar_label(bar: pg.ColorBarItem, label: str):
    bar.getAxis('right').setLabel(label)


def set_colour_bar_map(bar: pg.ColorBarItem, name: str):
    """Repaint an existing bar in another map, leaving its place in the row."""
    bar.setColorMap(colour_map(name))
