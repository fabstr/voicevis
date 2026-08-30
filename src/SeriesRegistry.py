"""Catalogue of everything that can be plotted.

This module is deliberately free of Qt and pyqtgraph imports: it is also
imported by ``mass_analyzer.py``, which renders with matplotlib.

It replaces the old ``PlotsSpec.py`` plot catalogue. Instead of describing whole
plots, it describes *series*; a plot is then any combination of series chosen
for the X axis, the Y axis and an optional colour dimension (see
``ui.plot.PlotConfig``). The named plots that used to live in ``PlotsSpec`` survive
only as :data:`PRESETS`, used to seed the default layout and to migrate old
layout files.
"""

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# --- Colours -------------------------------------------------------------
# Names kept identical to the old PlotsSpec module so external consumers
# (mass_analyzer.py) only have to change their import statement.

loudness = "#008b8b"
pitch = "#e9aad8"
f1 = "#dc143c"
f2 = "#006400"
f3 = "#ffd700"

f1_pitch = "#7588ff"
f2_pitch = "#ff8c00"
f3_pitch = "#9966cc"
size = "#32cd32"
weight = "#c71585"

h1_h2 = "#EF75F0"
h1_h3 = "#F07595"
h1_h4 = "#F0B175"
h1_a3 = "#C175F0"

jitter = "#85E0BF"
shimmer = "#85BCE0"
cpps = "#B8E085"

magnitude = "#9370DB"
neutral = "#88888888"

#: Fill for every target band: a neutral translucent grey, so the bands read as
#: background rather than competing with the series colours drawn over them.
target_band = "#88888833"

DEFAULT_POINT_SIZE = 2

#: Removes wild single-frame excursions in the harmonic series.
outliers_m = 5.0


class SeriesKind(Enum):
    """What kind of data a series holds, and therefore how it is read."""

    TIME = "time"            # synthetic: the shared frame timebase
    SIGNAL = "signal"        # a SignalTimeSeries attribute on AudioFeatures
    FREQUENCY = "frequency"  # synthetic: SpectrogramData.y
    MAGNITUDE = "magnitude"  # synthetic: a magnitude_db column at the playhead
    RADAR = "radar"          # synthetic: several series on spokes around a centre


@dataclass(frozen=True)
class SeriesSpec:
    """One plottable quantity."""

    key: str
    label: str
    unit: str = ""
    default_min: float = 0.0
    default_max: float = 1.0
    colour: str = "#FFFFFF"
    #: Name understood by ``TargetConfig.get_bounds``; None means no target band.
    target_key: Optional[str] = None
    kind: SeriesKind = SeriesKind.SIGNAL
    log_axis: bool = False
    #: True when the series cannot share an axis with any other series.
    exclusive: bool = True

    @property
    def axis_label(self) -> str:
        return f"{self.label} ({self.unit})" if self.unit else self.label

    @property
    def is_signal(self) -> bool:
        return self.kind is SeriesKind.SIGNAL


def _signal(key, label, lo, hi, colour, target=None, unit=""):
    return SeriesSpec(
        key=key, label=label, unit=unit,
        default_min=lo, default_max=hi,
        colour=colour, target_key=target,
        kind=SeriesKind.SIGNAL, exclusive=False,
    )


#: Every plottable series, in the order they should appear in the selectors.
SERIES = OrderedDict()

for _spec in (
    SeriesSpec("time", "Time", unit="s", default_min=0.0, default_max=10.0,
               colour=neutral, kind=SeriesKind.TIME),
    SeriesSpec("frequency", "Frequency", unit="Hz", default_min=10.0, default_max=10000.0,
               colour=neutral, kind=SeriesKind.FREQUENCY, log_axis=True),
    SeriesSpec("magnitude", "Magnitude", unit="dB", default_min=-90.0, default_max=0.0,
               colour=magnitude, kind=SeriesKind.MAGNITUDE),
    # The range is the unit disc the spokes are drawn in; what the plot is
    # actually scrolled to is RadarGeometry.VIEW_RANGE, which leaves room for
    # the spoke labels outside it.
    SeriesSpec("radar", "Radar", default_min=-1.0, default_max=1.0,
               colour=neutral, kind=SeriesKind.RADAR),

    _signal("pitch", "Pitch", 0, 350, pitch, "pitch", "Hz"),

    _signal("loudness", "Loudness", 0, 10, loudness, "loudness"),

    _signal("weight", "Weight", 0, 60, weight, "weight"),

    _signal("size", "Size", 0, 30, size, "size"),

    _signal("F1", "F1", 0, 3500, f1, "f1", "Hz"),
    _signal("F2", "F2", 0, 3500, f2, "f2", "Hz"),
    _signal("F3", "F3", 0, 3500, f3, "f3", "Hz"),

    _signal("F1_Pitch", "F1 / Pitch", 1, 15, f1_pitch, "f1_pitch"),
    _signal("F2_Pitch", "F2 / Pitch", 1, 30, f2_pitch, "f2_pitch"),
    _signal("F3_Pitch", "F3 / Pitch", 1, 50, f3_pitch, "f3_pitch"),

    _signal("H1_H2", "H1 - H2", -20, 50, h1_h2, "H1_H2", "dB"),
    _signal("H1_H3", "H1 - H3", -20, 50, h1_h3, "H1_H3", "dB"),
    _signal("H1_H4", "H1 - H4", -20, 50, h1_h4, "H1_H4", "dB"),
    _signal("H1_A3", "H1 - A3", -20, 50, h1_a3, "H1_A3", "dB"),

    _signal("jitter", "Jitter", 0, 0.2, jitter),
    _signal("shimmer", "Shimmer", 0, 7, shimmer, unit="dB"),
    _signal("cpps", "CPPS", 0, 20, cpps, "cpps", "dB"),
):
    SERIES[_spec.key] = _spec
del _spec

TIME_KEY = "time"
FREQUENCY_KEY = "frequency"
MAGNITUDE_KEY = "magnitude"
RADAR_KEY = "radar"


# --- Palette -------------------------------------------------------------
# ``SeriesSpec.colour`` is the colour a series *ships* with. The user can
# override any of them, so nothing should read ``spec.colour`` directly --
# call :func:`colour_of` instead.
#
# Overrides live here rather than on the cell or the plot because a series
# should look the same in every plot and every window.

_HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

FALLBACK_COLOUR = "#ffffff"


def normalise_colour(colour: str) -> str:
    """``#rrggbb`` (or ``#rrggbbaa``) in lower case. Raises on anything else.

    Everything is normalised on the way in so that colours can be compared as
    plain strings -- Qt reports them lower case, and the shipped constants are
    written mixed case.
    """
    text = str(colour).strip()
    if not text.startswith("#"):
        text = "#" + text
    if not _HEX_COLOUR.match(text):
        raise ValueError(f"Not a hex colour: {colour!r}")
    return text.lower()


#: The shipped colour of each series, by key.
DEFAULT_COLOURS = OrderedDict(
    (key, normalise_colour(spec.colour)) for key, spec in SERIES.items())

_colour_overrides = {}


def _key_of(series) -> str:
    return series.key if isinstance(series, SeriesSpec) else series


def colour_of(series) -> str:
    """The colour a series is currently drawn in."""
    key = _key_of(series)
    return _colour_overrides.get(key) or DEFAULT_COLOURS.get(key, FALLBACK_COLOUR)


def default_colour_of(series) -> str:
    """The colour a series ships with, ignoring any override."""
    return DEFAULT_COLOURS.get(_key_of(series), FALLBACK_COLOUR)


def set_colour(series, colour: Optional[str]):
    """Override a series' colour. ``None`` restores its default."""
    key = _key_of(series)
    if key not in SERIES:
        raise KeyError(f"Unknown series: {key!r}")

    if not colour:
        _colour_overrides.pop(key, None)
        return

    value = normalise_colour(colour)
    if value == DEFAULT_COLOURS[key]:
        _colour_overrides.pop(key, None)
    else:
        _colour_overrides[key] = value


def reset_colours():
    """Put every series back to its shipped colour."""
    _colour_overrides.clear()


def colour_overrides() -> dict:
    """Only the colours that differ from the defaults, for persistence."""
    return dict(_colour_overrides)


def apply_colour_overrides(mapping):
    """Replace all overrides. Unusable entries are skipped, not fatal."""
    reset_colours()
    for key, colour in (mapping or {}).items():
        try:
            set_colour(key, colour)
        except (KeyError, ValueError) as exc:
            logging.warning("Ignoring saved colour for %r: %s", key, exc)


def colourable_series():
    """Series that are actually drawn, and so have a colour worth choosing."""
    return [s for s in SERIES.values()
            if s.kind not in (SeriesKind.TIME, SeriesKind.FREQUENCY, SeriesKind.RADAR)]


def get(key: str) -> Optional[SeriesSpec]:
    """The spec for ``key``, or None when the key is unknown."""
    return SERIES.get(key)


def signal_series():
    """Every real (non-synthetic) series, in registry order."""
    return [s for s in SERIES.values() if s.is_signal]


def axis_candidates():
    """Series offerable on an axis: the real signals plus ``time``."""
    return [SERIES[TIME_KEY]] + signal_series()


def union_range(keys) -> Optional[Tuple[float, float]]:
    """The smallest range covering the default ranges of every key given."""
    specs = [SERIES[k] for k in keys if k in SERIES]
    if not specs:
        return None
    return (min(s.default_min for s in specs), max(s.default_max for s in specs))


# --- Presets -------------------------------------------------------------

@dataclass(frozen=True)
class PlotPreset:
    """A saved combination of series.

    ``name`` must match the corresponding key in the old ``PlotsSpec`` dict so
    that layout files written by earlier versions can be migrated.
    """

    name: str
    x: Tuple[str, ...]
    y: Tuple[str, ...]
    colour: Optional[str] = None
    trail_time: float = 3.0
    spectrogram: bool = False
    y_range: Optional[Tuple[float, float]] = None


PRESETS = (
    PlotPreset("Pitch", ("time",), ("pitch",)),
    PlotPreset("Size", ("time",), ("size",)),

    PlotPreset("Loudness", ("time",), ("loudness",)),
    PlotPreset("Weight", ("time",), ("weight",)),

    PlotPreset("Formants", ("time",), ("F1", "F2", "F3")),
    PlotPreset("F1", ("time",), ("F1",)),
    PlotPreset("F2", ("time",), ("F2",)),
    PlotPreset("F3", ("time",), ("F3",)),

    PlotPreset("F3/Pitch", ("time",), ("F3_Pitch",)),
    PlotPreset("F2/Pitch", ("time",), ("F2_Pitch",)),
    PlotPreset("F1/Pitch", ("time",), ("F1_Pitch",)),

    PlotPreset("Spectrogram", ("time",), (), spectrogram=True),
    PlotPreset("Frequency Analysis", ("frequency",), ("magnitude",)),

    PlotPreset("H1_H2", ("time",), ("H1_H2",)),
    PlotPreset("H1_H3", ("time",), ("H1_H3",)),
    PlotPreset("H1_H4", ("time",), ("H1_H4",)),
    PlotPreset("H1_A3", ("time",), ("H1_A3",)),

    PlotPreset("Jitter", ("time",), ("jitter",)),
    PlotPreset("Shimmer", ("time",), ("shimmer",)),
    PlotPreset("CPPS", ("time",), ("cpps",)),
)

PRESETS_BY_NAME = OrderedDict((p.name, p) for p in PRESETS)

DEFAULT_PRESET = "Pitch"

#: What a fresh session shows before any layout is restored.
DEFAULT_LAYOUT = ("Pitch", "Size", "Loudness")


def self_check():
    """Validate the registry against the data model. Raises on any mismatch."""
    from signal_processing.AudioFeatures import AudioFeatures

    features = AudioFeatures()
    problems = []

    for spec in signal_series():
        if not hasattr(features, spec.key):
            problems.append(f"series '{spec.key}' is not an AudioFeatures attribute")

    for preset in PRESETS:
        for key in preset.x + preset.y:
            if key not in SERIES:
                problems.append(f"preset '{preset.name}' references unknown series '{key}'")
        if preset.colour and preset.colour not in SERIES:
            problems.append(f"preset '{preset.name}' colours by unknown series '{preset.colour}'")

    if DEFAULT_PRESET not in PRESETS_BY_NAME:
        problems.append(f"DEFAULT_PRESET '{DEFAULT_PRESET}' is not a preset")

    if problems:
        raise AssertionError("SeriesRegistry self-check failed:\n  " + "\n  ".join(problems))

    return len(SERIES), len(PRESETS)


if __name__ == "__main__":
    n_series, n_presets = self_check()
    print(f"OK: {n_series} series, {n_presets} presets")
