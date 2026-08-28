# `SeriesRegistry`

The catalogue of everything that can be plotted. This is the module that
replaced the old `PlotsSpec.py`.

The difference is the unit of description. `PlotsSpec` described **plots** — 23
named entries, each a nested dictionary of curves, axis bounds, target names and
behavioural flags. `SeriesRegistry` describes **series**, and a plot is any
combination of them chosen by the user. See
[`ui/plot/README.md`](ui/plot/README.md) for how that combination is turned into
a drawing.

**This module must stay free of Qt and pyqtgraph.** `mass_analyzer.py` imports
it for the colour constants and renders with matplotlib.

---

## `SeriesSpec`

```mermaid
classDiagram
    class SeriesSpec {
        +key: str
        +label: str
        +unit: str
        +default_min: float
        +default_max: float
        +colour: str
        +target_key: str?
        +kind: SeriesKind
        +log_axis: bool
        +exclusive: bool
        +axis_label
        +is_signal
    }
    class SeriesKind {
        <<enumeration>>
        TIME
        SIGNAL
        FREQUENCY
        MAGNITUDE
    }
    SeriesSpec --> SeriesKind
```

| Field | Used for |
|---|---|
| `key` | The attribute name on `AudioFeatures` and `FeatureSnapshot`, or a synthetic name |
| `label`, `unit` | Selector entries, axis labels, plot titles |
| `default_min/max` | The range reset-zoom restores, and the spectrogram crop |
| `colour` | The colour the series *ships* with — see the palette below |
| `target_key` | Looked up in `TargetConfig.get_bounds()`; `None` means no target band |
| `kind` | Whether the series is real data or synthetic |
| `exclusive` | Whether the series can share an axis with others |

### Synthetic series

Three entries are not attributes of `AudioFeatures`. They exist so that the axis
selectors can express every kind of plot through one mechanism:

| Key | Meaning | Selecting it gives |
|---|---|---|
| `time` | The shared frame timebase | a time-scatter plot — on X normally, on Y transposed |
| `frequency` | `SpectrogramData.y` | a spectrum-slice plot (X only) |
| `magnitude` | A `magnitude_db` column at the playhead | (forced onto Y there) |

All three are `exclusive`; every real signal is not. That single flag is what
encodes "time cannot share an axis with pitch" without any special-casing in the
selector or the config.

### Ranges and targets

`default_min`/`default_max` were lifted from the corresponding `y_min`/`y_max`
in the old plot catalogue, so reset-zoom behaves as it did.

`target_key` is mostly the key itself, lowercased by `TargetConfig.get_bounds`.
Nothing stops two series sharing one target key, and earlier versions did that
for the rolling-mean series that have since been removed.

`F1_Pitch_rel_amplitude` and its siblings are **not** in the registry. They are
declared on `AudioFeatures` but never assigned by the extractor and are absent
from `FeatureSnapshot` — work in progress, not plottable data.

---

## The palette

Users can recolour any series, so **nothing should read `spec.colour` directly**
— call `colour_of(spec)`. `SeriesSpec` is frozen and its `colour` is only the
shipped default; overrides live in a separate layer.

```mermaid
flowchart LR
    Q["colour_of(series)"] --> O{"overridden?"}
    O -- yes --> U["the user's choice"]
    O -- no --> D["DEFAULT_COLOURS<br/><i>SeriesSpec.colour</i>"]

    Z["series used as a plot's<br/>colour dimension"] --> V["the plot's colour map<br/><i>never the palette</i>"]

    classDef l fill:#2d3b4d,stroke:#7aa2c8,color:#e8eef5
    classDef v fill:#3d3050,stroke:#a98ac8,color:#e8eef5
    class U,D l
    class V v
```

| Function | |
|---|---|
| `colour_of(series)` | What to draw it in now |
| `default_colour_of(series)` | What it ships with |
| `set_colour(key, colour)` | Override; `None` restores the default |
| `reset_colours()` | Back to the shipped palette |
| `colour_overrides()` / `apply_colour_overrides()` | Persistence |
| `colourable_series()` | What to offer in the picker |

Setting a series back to its default *removes* the override rather than storing
it, so only real changes are saved and a future change to a shipped colour still
reaches users who never touched it.

**A series used as a plot's colour dimension is mapped through that plot's
colour map** -- viridis, plasma or turbo -- never through the palette. The
palette says what a series looks like as *itself*; on the Z axis the colour
encodes a value, not an identity, so a continuous ramp is the point. Which ramp
is a per-plot setting (`PlotConfig.colour_map`); the choice of *ramps offered*
is not, and lives in `ui/plot/ColourMapping.py`.

Overrides are application-wide — a series looks the same in every plot and every
window — which is why they live in this module rather than on a cell. Changing
one is not a `PlotConfig` change, so `PlotCell.refresh_colours()` rebuilds the
items without touching the configuration or the zoom.

`mass_analyzer.py` uses the module-level colour constants directly and so always
renders with the defaults; it has no UI to change them from.

---

## Presets

Presets are the only thing left of the old plot catalogue. They are a thin list
of saved combinations:

```python
PlotPreset(name="Formants", x=("time",), y=("F1", "F2", "F3"))
PlotPreset(name="Size vs Weight", x=("weight_instantaneous",), y=("size",),
           colour="loudness", trail_time=3.0)
PlotPreset(name="Spectrogram", x=("time",), y=(), spectrogram=True)
```

They have exactly two jobs:

```mermaid
flowchart LR
    P["PRESETS"] --> A["seed the default 2&times;2 grid"]
    P --> B["migrate old layout files<br/>and the QSettings blob"]

    classDef l fill:#2d3b4d,stroke:#7aa2c8,color:#e8eef5
    class A,B l
```

**`PlotPreset.name` must stay identical to the corresponding key in the old
`PlotsSpec` dictionary.** Layout files written by earlier versions store that
name, and `PlotConfig.from_layout_entry` resolves it through
`PRESETS_BY_NAME`. Renaming one silently degrades those layouts to the default
plot.

Note that `Spectrogram` has an empty `y`. The standalone spectrogram is not a
special case in the code — it is simply a time plot with no Y series and the
background layer switched on.

---

## The self-check

`self_check()` — run it with `python src/SeriesRegistry.py` — asserts that:

- every `SIGNAL` series is an attribute of `AudioFeatures`
- every series named by a preset exists in the registry
- every colour dimension names a real series
- `DEFAULT_PRESET` is a preset

It catches the failure mode this design is most exposed to: a series renamed in
the analysis pipeline while the registry still names the old one, which would
otherwise surface as a plot that silently draws nothing.

---

## Adding a series

1. Add the field to `AudioFeatures`, and to `FeatureSnapshot` if it can be
   computed live.
2. Add a `_signal(...)` line to `SERIES`, in the position you want it to appear
   in the selectors.
3. If it has a target range, add the name to `TargetConfig` and set `target_key`.
4. Run `python src/SeriesRegistry.py`.

No plot definitions to update, and no change anywhere in `ui/plot` — the new
series appears in every X, Y and Colour selector automatically.
