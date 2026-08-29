"""Where a radar plot's axes point, and how far out along one a value sits.

A radar plot draws several series at once, each on its own spoke radiating from
a common centre. Two separate objects have to agree on that geometry exactly --
:class:`~ui.plot.renderers.RadarRenderer.RadarRenderer` draws the points and
:class:`~ui.plot.layers.RadarLayer.RadarLayer` draws the rings, the spokes and
the target boxes -- so the arithmetic lives here rather than in either of them.

Everything is in a unit disc centred on the origin: the maths never has to know
what the series are measured in, and the view range is the same whatever is
plotted. No Qt, no pyqtgraph.
"""

import numpy as np

#: Where a value at the top of its range sits.
OUTER_RADIUS = 1.0

#: Where a value at the bottom of its range sits. Not zero, so the spokes stay
#: distinguishable near the centre instead of piling into a single blob.
INNER_RADIUS = 0.08

#: Half the width of a target box, measured across its spoke. Every other
#: crosswise measurement here is derived from it, so this one number sets how
#: wide an axis is -- and therefore how many of them fit round the circle
#: before the neighbouring scales start to touch.
TARGET_HALF_WIDTH = 0.045

#: How much of the target box's width a value stroke spans.
VALUE_TICK_FRACTION = 0.75

#: Where a scale tick starts and ends, measured across the spoke: it begins at
#: the edge of the target box and reaches a little further out, so the scale
#: frames the box rather than crossing the values drawn inside it.
SCALE_TICK_INNER = TARGET_HALF_WIDTH
SCALE_TICK_OUTER = TARGET_HALF_WIDTH + 0.03

#: Where a scale label sits, measured across the spoke.
SCALE_LABEL_OFFSET = SCALE_TICK_OUTER + 0.015

#: Roughly how many divisions a spoke's scale is cut into.
SCALE_DIVISIONS = 5

#: How far outside the outer ring a spoke's label is placed.
LABEL_MARGIN = 0.10

#: The axis range a radar plot is drawn in, with room for the labels. Both
#: axes use it, and the view box is aspect-locked so the rings stay circular.
VIEW_RANGE = (-(OUTER_RADIUS + 3 * LABEL_MARGIN), OUTER_RADIUS + 3 * LABEL_MARGIN)


def angles(count: int) -> np.ndarray:
    """The direction of each spoke, evenly spaced.

    The first points straight up and the rest follow clockwise, so a plot reads
    the way a compass does and adding a series rotates the others predictably.
    """
    if count <= 0:
        return np.empty(0)
    return np.pi / 2 - 2 * np.pi * np.arange(count) / count


def radius(values, spec) -> np.ndarray:
    """Map values of one series onto ``INNER_RADIUS``..``OUTER_RADIUS``.

    The scale is the series' registry range, which is what reset-zoom uses
    everywhere else, so a spoke means the same thing on every radar plot.
    Values outside it are clamped to the ring rather than escaping the frame.
    """
    values = np.asarray(values, dtype=float)
    low, high = float(spec.default_min), float(spec.default_max)
    span = high - low
    fraction = np.zeros_like(values) if span <= 0 else (values - low) / span
    return INNER_RADIUS + np.clip(fraction, 0.0, 1.0) * (OUTER_RADIUS - INNER_RADIUS)


def to_xy(radii, angle: float):
    """Polar to cartesian, for one spoke's worth of radii."""
    radii = np.asarray(radii, dtype=float)
    return radii * np.cos(angle), radii * np.sin(angle)


def ring(radius_value: float, segments: int = 180):
    """A closed circle at ``radius_value``, as an (x, y) pair."""
    theta = np.linspace(0.0, 2 * np.pi, segments + 1)
    return radius_value * np.cos(theta), radius_value * np.sin(theta)


def spoke(angle: float):
    """The line from the centre to the outer ring, as an (x, y) pair."""
    return (np.array([0.0, OUTER_RADIUS * np.cos(angle)]),
            np.array([0.0, OUTER_RADIUS * np.sin(angle)]))


def label_point(angle: float):
    """Where a spoke's series name goes: just beyond the outer ring."""
    reach = OUTER_RADIUS + LABEL_MARGIN
    return reach * np.cos(angle), reach * np.sin(angle)


def value_ticks(radii, angle: float, fraction: float = VALUE_TICK_FRACTION):
    """A stroke across the spoke at each radius, as (x0, y0, x1, y1) arrays.

    A value is marked with a line rather than a dot so that it reads against
    the target box it sits in: same orientation, a fixed fraction of the box's
    width, so whether it falls inside is a matter of height alone.
    """
    radii = np.asarray(radii, dtype=float)
    along, across = _axes(angle, TARGET_HALF_WIDTH * fraction)
    centres = radii[:, None] * along
    return (centres[:, 0] - across[0], centres[:, 1] - across[1],
            centres[:, 0] + across[0], centres[:, 1] + across[1])


def scale_ticks(spec, divisions: int = SCALE_DIVISIONS):
    """The values a spoke's scale is marked at, and the step between them.

    Steps come off the 1/2/5 ladder, so the numbers printed are ones a reader
    recognises. The tick that would land on the centre is dropped: every spoke
    meets there, so all of them would print their minimum on top of each other.
    """
    low, high = float(spec.default_min), float(spec.default_max)
    span = high - low
    if span <= 0 or divisions < 1:
        return [], 1.0

    step = _nice_step(span / divisions)
    first = np.ceil((low + step / 2.0) / step) * step
    values = np.arange(first, high + step * 1e-6, step)
    return [float(v) for v in values if low < v <= high + step * 1e-6], step


def scale_tick_marks(radius: float, angle: float):
    """The pair of strokes marking one scale value, one either side of the spoke.

    Returned as (x0, y0, x1, y1) arrays of length two, ready for a segment item.
    """
    along, _ = _axes(angle, 1.0)
    centre = radius * along
    inner = _across(angle, SCALE_TICK_INNER)
    outer = _across(angle, SCALE_TICK_OUTER)
    starts = np.array([centre + inner, centre - inner])
    ends = np.array([centre + outer, centre - outer])
    return starts[:, 0], starts[:, 1], ends[:, 0], ends[:, 1]


def scale_label_points(radius: float, angle: float):
    """Where one scale value is printed, one point either side of the spoke."""
    along, _ = _axes(angle, 1.0)
    centre = radius * along
    offset = _across(angle, SCALE_LABEL_OFFSET)
    return (centre + offset), (centre - offset)


def format_tick(value: float, step: float) -> str:
    """A scale value printed to whatever precision its step actually needs."""
    decimals = max(0, int(-np.floor(np.log10(step))))
    if value == 0:
        value = 0.0        # the arithmetic can land on -0.0, which prints as "-0"
    return f"{value:.{decimals}f}"


def _axes(angle: float, reach: float):
    """The unit vector along a spoke, and one of length ``reach`` across it."""
    return (np.array([np.cos(angle), np.sin(angle)]),
            np.array([-np.sin(angle), np.cos(angle)]) * reach)


def _across(angle: float, reach: float) -> np.ndarray:
    return _axes(angle, reach)[1]


def _nice_step(raw: float) -> float:
    """``raw`` rounded up to the next 1, 2 or 5 times a power of ten."""
    if raw <= 0:
        return 1.0
    exponent = np.floor(np.log10(raw))
    base = raw / 10.0 ** exponent
    for candidate in (1.0, 2.0, 5.0):
        if base <= candidate:
            return float(candidate * 10.0 ** exponent)
    return float(10.0 ** (exponent + 1))


def target_box(low_radius: float, high_radius: float, angle: float,
               half_width: float = TARGET_HALF_WIDTH):
    """The corners of the box marking one spoke's target range.

    A rectangle rather than an annular segment: it is the same shape whichever
    spoke it is on, so two targets can be compared by eye without allowing for
    the wedge's spread.
    """
    along, across = _axes(angle, half_width)
    corners = np.array([
        along * low_radius - across,
        along * high_radius - across,
        along * high_radius + across,
        along * low_radius + across,
    ])
    return corners[:, 0], corners[:, 1]
