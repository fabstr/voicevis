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
weight = "#c71585"
size = "#32cd32"

h1_h2 = "#EF75F0"
h1_h3 = "#F07595"
h1_h4 = "#F0B175"
h1_a3 = "#C175F0"

jitter = "#85E0BF"
shimmer = "#85BCE0"

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

    _signal("pitch", "Pitch", 0, 350, pitch, "pitch", "Hz"),
    _signal("pitch_5s_mean", "Pitch (5 s mean)", 0, 300, pitch, "pitch", "Hz"),

    _signal("loudness", "Loudness", 0, 10, loudness, "loudness"),

    _signal("weight_instantaneous", "Weight (softness)", 0, 2.5, weight, "weight"),
    _signal("weight_333ms_max", "Weight (333 ms max)", 0, 40, weight, "weight"),

    _signal("size", "Size", 0, 30, size, "size"),
    _signal("size_5s_mean", "Size (5 s mean)", 0, 30, size, "size"),

    _signal("slopes", "Spectral slope", -1e-6, 1e-6, "#ff0000", "slopes"),

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
):
    SERIES[_spec.key] = _spec
del _spec

TIME_KEY = "time"
FREQUENCY_KEY = "frequency"
MAGNITUDE_KEY = "magnitude"


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
    PlotPreset("Weight", ("time",), ("weight_instantaneous",)),
    PlotPreset("Size vs Weight", ("weight_instantaneous",), ("size",),
               colour="loudness", trail_time=3.0),

    PlotPreset("5s average pitch", ("time",), ("pitch_5s_mean",)),
    PlotPreset("5s average size", ("time",), ("size_5s_mean",)),
    PlotPreset("5s average weight", ("time",), ("weight_333ms_max",)),

    PlotPreset("Loudness", ("time",), ("loudness",)),
    PlotPreset("Spectral slopes", ("time",), ("slopes",)),

    PlotPreset("Formants", ("time",), ("F1", "F2", "F3")),
    PlotPreset("F1", ("time",), ("F1",)),
    PlotPreset("F2", ("time",), ("F2",)),
    PlotPreset("F3", ("time",), ("F3",)),

    PlotPreset("F3/Pitch", ("time",), ("F3_Pitch",)),
    PlotPreset("F2/Pitch", ("time",), ("F2_Pitch",)),
    PlotPreset("F1/Pitch", ("time",), ("F1_Pitch",)),

    PlotPreset("Fullness", ("time",), ("size",),
               colour="weight_instantaneous", y_range=(-15.0, 25.0)),

    PlotPreset("Spectrogram", ("time",), (), spectrogram=True),
    PlotPreset("Frequency Analysis", ("frequency",), ("magnitude",)),

    PlotPreset("H1_H2", ("time",), ("H1_H2",)),
    PlotPreset("H1_H3", ("time",), ("H1_H3",)),
    PlotPreset("H1_H4", ("time",), ("H1_H4",)),
    PlotPreset("H1_A3", ("time",), ("H1_A3",)),

    PlotPreset("Jitter", ("time",), ("jitter",)),
    PlotPreset("Shimmer", ("time",), ("shimmer",)),
)

PRESETS_BY_NAME = OrderedDict((p.name, p) for p in PRESETS)

DEFAULT_PRESET = "Pitch"

#: What a fresh session shows before any layout is restored.
DEFAULT_LAYOUT = ("Pitch", "Size", "Weight", "Size vs Weight")


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
