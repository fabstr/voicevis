"""Mapping a third data dimension onto the viridis colour map.

``pg.ColorMap.map`` expects values in 0..1. The previous code passed raw feature
values straight in, so any series whose values exceed 1 -- weight, for instance --
saturated to the top colour and the plot came out a single flat shade. Everything
here normalises first, and reports the range it used so a colour bar can be
labelled to match.
"""

from typing import Optional, Tuple

import numpy as np
import pyqtgraph as pg

_COLOURMAP = None


def viridis():
    global _COLOURMAP
    if _COLOURMAP is None:
        _COLOURMAP = pg.colormap.get('viridis')
    return _COLOURMAP


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


def rgba(normalised: np.ndarray) -> np.ndarray:
    """An (N, 4) uint8 colour array for values already scaled to 0..1."""
    if np.size(normalised) == 0:
        return np.zeros((0, 4), dtype=np.uint8)
    return viridis().map(normalised, mode='byte')


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


def make_colour_bar(plot_item, label: str = "") -> pg.ColorBarItem:
    """Attach a viridis colour bar to the right of ``plot_item``."""
    bar = pg.ColorBarItem(values=(0.0, 1.0), colorMap=viridis(), width=15,
                          interactive=False, label=label)
    plot_item.layout.addItem(bar, 2, 4)
    return bar
