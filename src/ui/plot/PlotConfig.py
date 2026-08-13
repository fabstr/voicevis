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
    #: Give each series on the multi-valued axis its own scale, instead of
    #: sharing one. Only meaningful when that axis holds more than one series.
    separate_axes: bool = False
    point_size: int = DEFAULT_POINT_SIZE
    #: Explicit axis ranges; None means "use the series' default range".
    x_range: Optional[Tuple[float, float]] = None
    y_range: Optional[Tuple[float, float]] = None

    # --- Derived properties ---------------------------------------------

    @property
    def kind(self) -> PlotKind:
        # Frequency on X wins: it means a spectrum slice whatever Y holds.
        if self.x[:1] == [Registry.FREQUENCY_KEY]:
            return PlotKind.SPECTRUM_SLICE
        if self.x[:1] == [Registry.TIME_KEY] or self.y[:1] == [Registry.TIME_KEY]:
            return PlotKind.TIME_SCATTER
        return PlotKind.TRAIL

    @property
    def is_time_domain(self) -> bool:
        return self.kind is PlotKind.TIME_SCATTER

    @property
    def time_on_y(self) -> bool:
        """True when the plot is transposed: time running up the Y axis."""
        return self.y[:1] == [Registry.TIME_KEY]

    @property
    def time_axis(self) -> Optional[str]:
        """Which axis carries time, if either."""
        if self.kind is not PlotKind.TIME_SCATTER:
            return None
        return 'y' if self.time_on_y else 'x'

    def value_keys(self) -> List[str]:
        """The plotted quantities, i.e. whatever is not the time axis."""
        return self.x if self.time_on_y else self.y

    def value_specs(self) -> List[SeriesSpec]:
        return [Registry.SERIES[k] for k in self.value_keys() if k in Registry.SERIES]

    def x_specs(self) -> List[SeriesSpec]:
        return [Registry.SERIES[k] for k in self.x if k in Registry.SERIES]

    def y_specs(self) -> List[SeriesSpec]:
        return [Registry.SERIES[k] for k in self.y if k in Registry.SERIES]

    def colour_spec(self) -> Optional[SeriesSpec]:
        return Registry.get(self.colour) if self.colour else None

    def effective_x_range(self) -> Optional[Tuple[float, float]]:
        if self.x_range is not None:
            return tuple(self.x_range)
        if not self.x:
            return SPECTROGRAM_ONLY_RANGE if self.spectrogram else None
        return Registry.union_range(self.x)

    def effective_y_range(self) -> Optional[Tuple[float, float]]:
        if self.y_range is not None:
            return tuple(self.y_range)
        if not self.y:
            return SPECTROGRAM_ONLY_RANGE if self.spectrogram else None
        return Registry.union_range(self.y)

    def value_range(self) -> Optional[Tuple[float, float]]:
        """The range of the non-time axis."""
        return self.effective_x_range() if self.time_on_y else self.effective_y_range()

    def x_axis_label(self) -> str:
        return self._axis_label(self.x_specs())

    def y_axis_label(self) -> str:
        return self._axis_label(self.y_specs())

    def _axis_label(self, specs: List[SeriesSpec]) -> str:
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
        if self.kind is PlotKind.TIME_SCATTER:
            specs = self.value_specs()
            if not specs:
                return "Spectrogram" if self.spectrogram else "Empty plot"
            names = ", ".join(s.label for s in specs)
            # Transposed plots are named "Y vs X" so the layout is obvious.
            title = f"Time vs {names}" if self.time_on_y else names
            if self.spectrogram:
                title += " + spectrogram"
        else:
            y_specs = self.y_specs()
            if not y_specs:
                return "Empty plot"
            title = (f"{', '.join(s.label for s in y_specs)} vs "
                     f"{', '.join(s.label for s in self.x_specs())}")

        z_spec = self.colour_spec()
        return f"{title} / colour: {z_spec.label}" if z_spec else title

    def spectrogram_allowed(self) -> bool:
        """Whether a spectrogram background would line up with the value axis.

        The image is drawn in true Hz, so it is only meaningful when the axis
        opposite time is itself in Hz (or carries no series at all).
        """
        if self.kind is not PlotKind.TIME_SCATTER:
            return False
        specs = self.value_specs()
        return not specs or all(s.unit == "Hz" for s in specs)

    def frequency_axis(self) -> Optional[str]:
        """Which axis is measured in Hz, if either.

        This is where frequency markers can be drawn: across the X axis of a
        spectrum slice, or across the value axis of a time plot whose series are
        all in Hz -- formants, pitch, or a bare spectrogram.
        """
        if self.kind is PlotKind.SPECTRUM_SLICE:
            return 'x'
        if self.kind is not PlotKind.TIME_SCATTER:
            return None

        value_axis = 'x' if self.time_on_y else 'y'
        specs = self.value_specs()
        if not specs:
            return value_axis if self.spectrogram else None
        return value_axis if all(s.unit == "Hz" for s in specs) else None

    def colour_allowed(self) -> bool:
        """Colouring by a third dimension needs exactly one series per axis."""
        return len(self.x) == 1 and len(self.y) == 1

    def multi_axis(self) -> Optional[str]:
        """The axis holding several series, if either does.

        Only one axis can, so this also says which axis could be split into one
        scale per series.
        """
        if len(self.x) > 1:
            return 'x'
        if len(self.y) > 1:
            return 'y'
        return None

    def separate_axes_allowed(self) -> bool:
        """Separate scales only mean anything with several series to separate."""
        return self.multi_axis() is not None

    # --- Validation ------------------------------------------------------

    def normalised(self) -> "PlotConfig":
        """A copy guaranteed to be renderable. Never raises."""
        x = [k for k in self.x if k in Registry.SERIES]
        y = [k for k in self.y if k in Registry.SERIES]

        # An exclusive series (time, frequency, magnitude) cannot share an axis.
        x = _collapse_exclusive(x)
        y = _collapse_exclusive(y)

        # Time belongs to one axis or the other, never both.
        if x[:1] == [Registry.TIME_KEY] and y[:1] == [Registry.TIME_KEY]:
            y = []

        time_on_y = y[:1] == [Registry.TIME_KEY]
        if not x and not time_on_y:
            x = [Registry.TIME_KEY]

        # At most one axis may carry several series.
        if len(x) > 1 and len(y) > 1:
            y = y[:1]

        kind = PlotConfig(x=x, y=y).kind
        spectrogram = bool(self.spectrogram)
        colour = self.colour
        default_value = Registry.PRESETS_BY_NAME[Registry.DEFAULT_PRESET].y[0]

        if kind is PlotKind.SPECTRUM_SLICE:
            y = [Registry.MAGNITUDE_KEY]
            spectrogram = False
        elif kind is PlotKind.TIME_SCATTER:
            # Magnitude only exists inside a spectrum slice, so it is dropped
            # on the way out of one -- otherwise changing X away from Frequency
            # leaves the plot showing a series that has no data.
            if time_on_y:
                x = _signals_only(x)
                if not x and not spectrogram:
                    x = [default_value]
            else:
                y = _signals_only(y)
                if not y and not spectrogram:
                    y = [default_value]
        else:
            spectrogram = False
            x = _signals_only(x) or x
            y = _signals_only(y)
            if not y:
                y = [k for k in Registry.SERIES if Registry.SERIES[k].is_signal and k not in x][:1]

        probe = PlotConfig(x=x, y=y, spectrogram=spectrogram)
        if spectrogram and not probe.spectrogram_allowed():
            spectrogram = False

        separate_axes = bool(self.separate_axes) and probe.separate_axes_allowed()

        if colour is not None:
            spec = Registry.get(colour)
            usable = spec is not None and (spec.is_signal or colour in _extra_colour_keys(kind))
            if not usable or len(x) != 1 or len(y) != 1:
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
            separate_axes=separate_axes,
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
            "separate_axes": self.separate_axes,
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
                separate_axes=bool(entry.get("separate_axes", False)),
                point_size=int(size or default_point_size),
                x_range=_as_range(entry.get("x_range")),
                y_range=_as_range(entry.get("y_range")),
            ).normalised()

        if "name" in entry:
            size = entry.get("local_size", default_point_size)
            return cls.from_preset(entry["name"], int(size or default_point_size))

        logging.warning("Unrecognised layout entry %r; using default plot", entry)
        return cls.from_preset(Registry.DEFAULT_PRESET, default_point_size)


def _extra_colour_keys(kind: PlotKind) -> tuple:
    """Non-signal series a plot kind may colour by.

    A spectrum slice is one instant, so an ordinary time series has a single
    value there. Frequency is the axis that actually varies along the curve,
    which makes it the useful thing to map colour onto.
    """
    return (Registry.FREQUENCY_KEY,) if kind is PlotKind.SPECTRUM_SLICE else ()


def colour_candidates(kind: PlotKind) -> List[str]:
    """Every series that may drive the colour dimension for ``kind``."""
    return [s.key for s in Registry.signal_series()] + list(_extra_colour_keys(kind))


def _signals_only(keys: List[str]) -> List[str]:
    """Drop the synthetic series, which are axes rather than measurements."""
    return [k for k in keys if Registry.SERIES[k].is_signal]


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
