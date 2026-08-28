"""What a layout file promises about a plot's colour map.

Serialisation is the one part of the plot stack that needs no screen, and it is
where a new field can quietly break old files: ``LayoutSerializer`` has to read
every layout this application has ever written. The colour map is the newest
key, so the cases worth pinning are the ones where it is absent, unreadable, or
from a format that predates it entirely.
"""

import json
from pathlib import Path

import pytest

from ui.plot.ColourMapping import DEFAULT_COLOUR_MAP
from ui.plot import LayoutSerializer
from ui.plot.PlotConfig import PlotConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMPLE_LAYOUT = REPO_ROOT / "resources" / "layouts" / "layout_simple.json"


def entry(**overrides) -> dict:
    """A current-schema layout entry, minus whatever the caller drops."""
    data = {"x": ["time"], "y": ["pitch"], "colour": "loudness",
            "colour_map": "plasma", "trail_time": 3.0, "spectrogram": False,
            "separate_axes": False, "local_size": 5}
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not ...}


def test_colour_map_survives_a_round_trip():
    config = PlotConfig(x=["time"], y=["pitch"], colour="loudness",
                        colour_map="turbo").normalised()
    restored = PlotConfig.from_layout_entry(config.to_dict())
    assert restored.colour_map == "turbo"


def test_every_selectable_map_round_trips():
    for name in ("viridis", "plasma", "turbo"):
        restored = PlotConfig.from_layout_entry(entry(colour_map=name))
        assert restored.colour_map == name


def test_an_entry_without_the_key_defaults_to_viridis():
    """Every layout written before this feature existed."""
    restored = PlotConfig.from_layout_entry(entry(colour_map=...))
    assert restored.colour_map == DEFAULT_COLOUR_MAP == "viridis"


@pytest.mark.parametrize("value", ["jet", "", None, 7, ["plasma"]])
def test_an_unreadable_map_falls_back_rather_than_raising(value):
    restored = PlotConfig.from_layout_entry(entry(colour_map=value))
    assert restored.colour_map == DEFAULT_COLOUR_MAP


def test_the_map_is_kept_while_nothing_is_coloured():
    """Turning Colour by off and on again comes back in the chosen map."""
    config = PlotConfig(x=["time"], y=["pitch"], colour=None,
                        colour_map="turbo").normalised()
    assert config.colour is None
    assert config.colour_map == "turbo"


def test_older_formats_still_load():
    """A v1 preset entry and the oldest bare-string form both predate the key."""
    from_name = PlotConfig.from_layout_entry({"name": "Pitch", "local_size": 3})
    from_string = PlotConfig.from_layout_entry("Pitch")
    assert from_name.colour_map == DEFAULT_COLOUR_MAP
    assert from_string.colour_map == DEFAULT_COLOUR_MAP


def test_a_whole_layout_carries_a_map_per_plot():
    data = json.loads(SIMPLE_LAYOUT.read_text(encoding="utf-8"))
    layout = LayoutSerializer.load(data)
    assert all(config.colour_map == DEFAULT_COLOUR_MAP
               for column in layout.columns for config in column.configs)

    # Give one cell its own map and check it comes back through dump/load.
    layout.columns[0].configs[0].colour_map = "plasma"
    reloaded = LayoutSerializer.load(LayoutSerializer.dump(layout))
    assert reloaded.columns[0].configs[0].colour_map == "plasma"
    assert reloaded.columns[0].configs[1].colour_map == DEFAULT_COLOUR_MAP
