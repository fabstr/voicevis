"""The serialisable description of what a single plot cell shows.

A :class:`PlotConfig` is just a choice of series for each axis plus a few
display options. The *kind* of plot is derived from that choice rather than
stored, so switching a cell from a time series to an XY trail is a data change,
not a class change.
"""

import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import List, Optional, Tuple

import SeriesRegistry as Registry
from SeriesRegistry import DEFAULT_POINT_SIZE, SeriesSpec

MIN_TRAIL_TIME = 0.0
MAX_TRAIL_TIME = 60.0

#: Y range used by a spectrogram-only plot, matching the old 'Spectrogram' spec.
SPECTROGRAM_ONLY_RANGE = (0.0, 8000.0)


class PlotKind(Enum):
    """How a plot renders, derived from its X series."""

    TIME_SCATTER = "time_scatter"      # x is time
    SPECTRUM_SLICE = "spectrum_slice"  # x is frequency
    TRAIL = "trail"                    # neither axis is time


@dataclass
class PlotConfig:
    x: List[str] = field(default_factory=lambda: [Registry.TIME_KEY])
    y: List[str] = field(default_factory=lambda: ["pitch"])
    #: Third dimension mapped to viridis. Only honoured when both axes hold
    #: exactly one series.
    colour: Optional[str] = None
    #: Seconds of history shown by a TRAIL plot.
    trail_time: float = 3.0
    #: Draw the spectrogram behind the curves. TIME_SCATTER only.
    spectrogram: bool = False
    point_size: int = DEFAULT_POINT_SIZE
    #: Explicit axis ranges; None means "use the series' default range".
    x_range: Optional[Tuple[float, float]] = None
    y_range: Optional[Tuple[float, float]] = None

    # --- Derived properties ---------------------------------------------

    @property
    def kind(self) -> PlotKind:
        head = self.x[0] if self.x else None
        if head == Registry.TIME_KEY:
            return PlotKind.TIME_SCATTER
        if head == Registry.FREQUENCY_KEY:
            return PlotKind.SPECTRUM_SLICE
        return PlotKind.TRAIL

    @property
    def is_time_domain(self) -> bool:
        return self.kind is PlotKind.TIME_SCATTER

    def x_specs(self) -> List[SeriesSpec]:
        return [Registry.SERIES[k] for k in self.x if k in Registry.SERIES]

    def y_specs(self) -> List[SeriesSpec]:
        return [Registry.SERIES[k] for k in self.y if k in Registry.SERIES]

    def colour_spec(self) -> Optional[SeriesSpec]:
        return Registry.get(self.colour) if self.colour else None

    def effective_x_range(self) -> Optional[Tuple[float, float]]:
        if self.x_range is not None:
            return tuple(self.x_range)
        return Registry.union_range(self.x)

    def effective_y_range(self) -> Optional[Tuple[float, float]]:
        if self.y_range is not None:
            return tuple(self.y_range)
        if not self.y:
            return SPECTROGRAM_ONLY_RANGE if self.spectrogram else None
        return Registry.union_range(self.y)

    def x_axis_label(self) -> str:
        specs = self.x_specs()
        return specs[0].axis_label if len(specs) == 1 else self._joined_label(specs)

    def y_axis_label(self) -> str:
        specs = self.y_specs()
        if not specs:
            return Registry.SERIES[Registry.FREQUENCY_KEY].axis_label if self.spectrogram else ""
        return specs[0].axis_label if len(specs) == 1 else self._joined_label(specs)

    @staticmethod
    def _joined_label(specs: List[SeriesSpec]) -> str:
        if not specs:
            return ""
        names = ", ".join(s.label for s in specs)
        units = {s.unit for s in specs if s.unit}
        return f"{names} ({units.pop()})" if len(units) == 1 else names

    def title(self) -> str:
        x_specs, y_specs = self.x_specs(), self.y_specs()

        if not y_specs:
            return "Spectrogram" if self.spectrogram else "Empty plot"

        y_names = ", ".join(s.label for s in y_specs)
        if self.kind is PlotKind.TIME_SCATTER:
            title = f"{y_names} + spectrogram" if self.spectrogram else y_names
        else:
            x_names = ", ".join(s.label for s in x_specs)
            title = f"{y_names} vs {x_names}"

        z_spec = self.colour_spec()
        return f"{title} / colour: {z_spec.label}" if z_spec else title

    def spectrogram_allowed(self) -> bool:
        """Whether a spectrogram background would line up with this Y axis.

        The image is drawn in true Hz, so it is only meaningful when the Y axis
        is itself in Hz (or when there is no Y series at all).
        """
        if self.kind is not PlotKind.TIME_SCATTER:
            return False
        specs = self.y_specs()
        return not specs or all(s.unit == "Hz" for s in specs)

    def colour_allowed(self) -> bool:
        """Colouring by a third dimension needs exactly one series per axis."""
        return len(self.x) == 1 and len(self.y) == 1

    # --- Validation ------------------------------------------------------

    def normalised(self) -> "PlotConfig":
        """A copy guaranteed to be renderable. Never raises."""
        x = [k for k in self.x if k in Registry.SERIES]
        y = [k for k in self.y if k in Registry.SERIES]

        if not x:
            x = [Registry.TIME_KEY]

        # An exclusive series (time, frequency, magnitude) cannot share an axis.
        x = _collapse_exclusive(x)
        y = _collapse_exclusive(y)

        # At most one axis may carry several series.
        if len(x) > 1 and len(y) > 1:
            y = y[:1]

        kind = PlotConfig(x=x, y=y).kind
        spectrogram = bool(self.spectrogram)
        colour = self.colour

        if kind is PlotKind.SPECTRUM_SLICE:
            y = [Registry.MAGNITUDE_KEY]
            spectrogram = False
        elif kind is PlotKind.TIME_SCATTER:
            # An empty Y axis only makes sense as a bare spectrogram.
            if not y and not spectrogram:
                y = [Registry.PRESETS_BY_NAME[Registry.DEFAULT_PRESET].y[0]]
        else:
            spectrogram = False
            if not y:
                y = [k for k in Registry.SERIES if Registry.SERIES[k].is_signal and k not in x][:1]

        probe = PlotConfig(x=x, y=y, spectrogram=spectrogram)
        if spectrogram and not probe.spectrogram_allowed():
            spectrogram = False

        if colour is not None:
            spec = Registry.get(colour)
            if spec is None or not spec.is_signal or len(x) != 1 or len(y) != 1:
                colour = None

        trail = self.trail_time
        try:
            trail = min(MAX_TRAIL_TIME, max(MIN_TRAIL_TIME, float(trail)))
        except (TypeError, ValueError):
            trail = 3.0

        return replace(
            self,
            x=x, y=y, colour=colour,
            trail_time=trail,
            spectrogram=spectrogram,
            point_size=int(self.point_size or DEFAULT_POINT_SIZE),
            x_range=tuple(self.x_range) if self.x_range else None,
            y_range=tuple(self.y_range) if self.y_range else None,
        )

    def copy(self) -> "PlotConfig":
        return replace(self, x=list(self.x), y=list(self.y))

    # --- Serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        data = {
            "x": list(self.x),
            "y": list(self.y),
            "colour": self.colour,
            "trail_time": self.trail_time,
            "spectrogram": self.spectrogram,
            "local_size": int(self.point_size),
        }
        if self.x_range is not None:
            data["x_range"] = list(self.x_range)
        if self.y_range is not None:
            data["y_range"] = list(self.y_range)
        return data

    @classmethod
    def from_preset(cls, name: str, point_size: int = DEFAULT_POINT_SIZE) -> "PlotConfig":
        preset = Registry.PRESETS_BY_NAME.get(name)
        if preset is None:
            logging.warning("Unknown plot preset %r; falling back to %r", name, Registry.DEFAULT_PRESET)
            preset = Registry.PRESETS_BY_NAME[Registry.DEFAULT_PRESET]

        return cls(
            x=list(preset.x),
            y=list(preset.y),
            colour=preset.colour,
            trail_time=preset.trail_time,
            spectrogram=preset.spectrogram,
            point_size=point_size,
            y_range=preset.y_range,
        ).normalised()

    @classmethod
    def from_layout_entry(cls, entry, default_point_size: int = DEFAULT_POINT_SIZE) -> "PlotConfig":
        """Build a config from any layout-file entry ever written by this app.

        Accepts the current schema, the ``{"name", "local_size", "toggles"}``
        entries of layout v1, and the bare plot-name strings of the oldest
        format.
        """
        if isinstance(entry, str):
            return cls.from_preset(entry, default_point_size)

        if not isinstance(entry, dict):
            logging.warning("Unreadable layout entry %r; using default plot", entry)
            return cls.from_preset(Registry.DEFAULT_PRESET, default_point_size)

        if "x" in entry:
            size = entry.get("local_size", entry.get("point_size", default_point_size))
            return cls(
                x=list(entry.get("x") or []),
                y=list(entry.get("y") or []),
                colour=entry.get("colour"),
                trail_time=entry.get("trail_time", 3.0),
                spectrogram=bool(entry.get("spectrogram", False)),
                point_size=int(size or default_point_size),
                x_range=_as_range(entry.get("x_range")),
                y_range=_as_range(entry.get("y_range")),
            ).normalised()

        if "name" in entry:
            size = entry.get("local_size", default_point_size)
            return cls.from_preset(entry["name"], int(size or default_point_size))

        logging.warning("Unrecognised layout entry %r; using default plot", entry)
        return cls.from_preset(Registry.DEFAULT_PRESET, default_point_size)


def _collapse_exclusive(keys: List[str]) -> List[str]:
    """Reduce an axis to one series if any of its series is exclusive."""
    for key in keys:
        if Registry.SERIES[key].exclusive:
            return [key]
    return keys


def _as_range(value) -> Optional[Tuple[float, float]]:
    try:
        lo, hi = value
        return (float(lo), float(hi))
    except (TypeError, ValueError):
        return None
