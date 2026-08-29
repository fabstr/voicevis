"""What a layout file promises about a plot's colouring.

Serialisation is the one part of the plot stack that needs no screen, and it is
where a new field can quietly break old files: ``LayoutSerializer`` has to read
every layout this application has ever written. So the cases worth pinning are
the ones where a key is absent, unreadable, or from a format that predates it.

The colour map came first, per plot. Colouring is now chosen per *drawn series*
instead -- ``colour_sources`` and ``colour_maps`` -- with the older plot-wide
``colour``/``colour_map`` kept as the fallback, which is the only thing that
makes an existing layout come back looking the way it did.
"""

import json
from pathlib import Path

import numpy as np
import pytest

import SeriesRegistry as Registry
from ui.plot.ColourMapping import DEFAULT_COLOUR_MAP, normalise_to
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


# --- Per-series colouring ------------------------------------------------

def coloured(**overrides) -> PlotConfig:
    data = dict(x=["time"], y=["F1", "F2"],
                colour_sources={"F1": "loudness", "F2": "pitch"},
                colour_maps={"F1": "turbo", "F2": "plasma"})
    data.update(overrides)
    return PlotConfig(**data).normalised()


def test_each_drawn_series_keeps_its_own_source_and_map():
    config = coloured()
    assert config.colour_source("F1") == "loudness"
    assert config.colour_source("F2") == "pitch"
    assert config.colour_map_of("F1") == "turbo"
    assert config.colour_map_of("F2") == "plasma"


def test_per_series_colouring_survives_a_layout_round_trip():
    restored = PlotConfig.from_layout_entry(coloured().to_dict())
    assert restored.colour_sources == {"F1": "loudness", "F2": "pitch"}
    assert restored.colour_maps == {"F1": "turbo", "F2": "plasma"}


def test_a_layout_written_before_per_series_colouring_still_colours_its_plot():
    """The whole point of keeping the plot-wide keys as a fallback."""
    restored = PlotConfig.from_layout_entry(
        {"x": ["time"], "y": ["pitch"], "colour": "loudness", "colour_map": "plasma"})
    assert restored.colour_sources == {}
    assert restored.colour_source("pitch") == "loudness"
    assert restored.colour_map_of("pitch") == "plasma"


def test_choosing_none_for_one_series_overrides_the_plot_wide_fallback():
    config = PlotConfig(x=["time"], y=["F1", "F2"], colour="loudness",
                        colour_sources={"F1": None}).normalised()
    assert config.colour_source("F1") is None
    assert config.colour_source("F2") == "loudness"


@pytest.mark.parametrize("source", ["frequency", "nonsense", "time"])
def test_a_source_that_cannot_be_read_here_is_dropped(source):
    """Frequency only varies along a spectrum slice; the rest are not data."""
    config = PlotConfig(x=["time"], y=["pitch"],
                        colour_sources={"pitch": source}).normalised()
    assert "pitch" not in config.colour_sources


def test_frequency_is_still_a_source_on_a_spectrum_slice():
    config = PlotConfig(x=["frequency"], y=["magnitude"],
                        colour_sources={"magnitude": "frequency"}).normalised()
    assert config.colour_source("magnitude") == "frequency"


@pytest.mark.parametrize("value", ["jet", "", None, 7])
def test_an_unreadable_per_series_map_falls_back_to_the_default(value):
    config = PlotConfig(x=["time"], y=["pitch"], colour_maps={"pitch": value}).normalised()
    assert config.colour_map_of("pitch") == DEFAULT_COLOUR_MAP


@pytest.mark.parametrize("value", ["not a dict", 7, ["pitch"]])
def test_an_unreadable_colour_mapping_loads_as_empty_rather_than_raising(value):
    restored = PlotConfig.from_layout_entry(
        {"x": ["time"], "y": ["pitch"], "colour_sources": value, "colour_maps": value})
    assert restored.colour_sources == {} and restored.colour_maps == {}


def test_a_series_taken_off_an_axis_gets_its_colouring_back_when_it_returns():
    """The same reason the map outlives the colour dimension being turned off."""
    config = coloured(y=["F1"])
    assert "F2" not in config.drawn_keys()
    assert config.colour_sources["F2"] == "pitch"
    assert coloured(y=["F1", "F2"]).colour_source("F2") == "pitch"


def test_several_series_on_an_axis_may_now_each_be_coloured():
    """They could not before: one plot-wide colour would have painted them alike."""
    config = coloured()
    assert config.colour_allowed()
    assert config.colour_sources == {"F1": "loudness", "F2": "pitch"}


def test_the_title_says_per_series_only_when_they_actually_differ():
    assert coloured().title().endswith("/ colour: per series")
    same = coloured(colour_sources={"F1": "loudness", "F2": "loudness"})
    assert same.title().endswith("/ colour: Loudness")
    assert "colour" not in coloured(colour_sources={}).title()


@pytest.mark.parametrize("x, y, expected", [
    (["time"], ["F1", "F2"], ["F1", "F2"]),          # the quantities
    (["F1", "F2"], ["pitch"], ["F1", "F2"]),          # a trail's pairs
    (["radar"], ["pitch", "size"], ["pitch", "size"]),  # the spokes
    (["frequency"], ["magnitude"], ["magnitude"]),    # the one curve
    (["time"], [], []),                               # a bare spectrogram
])
def test_the_colour_menu_is_keyed_by_what_the_plot_actually_draws(x, y, expected):
    config = PlotConfig(x=x, y=y, spectrogram=not y).normalised()
    assert config.drawn_keys() == expected


# --- The scale a colour means --------------------------------------------

def test_a_colour_spans_its_source_range_not_the_data_it_happens_to_cover():
    """Otherwise the palette rescales itself whenever a different take is analysed."""
    pitch = Registry.SERIES["pitch"]                       # 0-350 Hz
    low, middle, high = normalise_to([0.0, 175.0, 350.0],
                                     pitch.default_min, pitch.default_max)
    assert (low, middle, high) == pytest.approx((0.0, 0.5, 1.0))

    # A quiet recording covering only 150-200 Hz still maps to the same colours.
    quiet = normalise_to([175.0], pitch.default_min, pitch.default_max)
    assert quiet[0] == pytest.approx(middle)


def test_a_value_off_the_scale_is_clamped_rather_than_wrapping_the_map():
    assert list(normalise_to([-1e6, 1e6], 0.0, 10.0)) == [0.0, 1.0]


def test_a_source_with_no_range_at_all_does_not_divide_by_zero():
    assert list(normalise_to([5.0, 7.0], 5.0, 5.0)) == [0.0, 0.0]


def test_normalising_nothing_returns_nothing():
    assert len(normalise_to([], 0.0, 1.0)) == 0


def test_a_nan_lands_at_the_bottom_of_the_scale_rather_than_poisoning_the_map():
    assert list(normalise_to([np.nan], 0.0, 10.0)) == [0.0]


# --- Show colour scales --------------------------------------------------

def test_the_colour_scales_toggle_survives_a_layout_round_trip():
    config = coloured(colour_scales=False)
    assert PlotConfig.from_layout_entry(config.to_dict()).colour_scales is False


def test_a_layout_written_before_the_toggle_existed_still_shows_its_scales():
    restored = PlotConfig.from_layout_entry({"x": ["time"], "y": ["pitch"]})
    assert restored.colour_scales is True


def test_the_toggle_says_nothing_about_what_is_coloured():
    """Turning the bars off must not quietly turn the colouring off with them."""
    config = coloured(colour_scales=False)
    assert config.colour_source("F1") == "loudness"
    assert config.any_colour()
