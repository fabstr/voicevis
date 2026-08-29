"""What a radar plot promises, in the parts that need no screen.

Two things are worth pinning. The geometry, because the renderer and the layer
compute it separately and a plot whose target boxes sit off its points is wrong
in a way nothing raises about. And the configuration rules, because ``radar``
is a fourth synthetic series on an axis that until now held three, and
``normalised()`` has to keep every one of the old promises while allowing the
one thing a radar needs -- several series on Y with none of them sharing a
scale.
"""

import numpy as np
import pytest

import SeriesRegistry as Registry
from ui.plot import RadarGeometry
from ui.plot.PlotConfig import PlotConfig, PlotKind

RADAR = Registry.RADAR_KEY


def radar(y, **overrides) -> PlotConfig:
    return PlotConfig(x=[RADAR], y=list(y), **overrides).normalised()


# --- Geometry ------------------------------------------------------------

def test_the_first_spoke_points_up_and_the_rest_follow_clockwise():
    up, right, left = RadarGeometry.angles(3)
    assert up == pytest.approx(np.pi / 2)
    # Clockwise from the top: the second spoke is to the lower right.
    assert np.cos(right) > 0 and np.sin(right) < 0
    assert np.cos(left) < 0 and np.sin(left) < 0


def test_the_spokes_are_evenly_spaced():
    for count in (1, 2, 3, 5, 8):
        gaps = np.diff(RadarGeometry.angles(count))
        assert np.allclose(gaps, gaps[0] if len(gaps) else [])


def test_no_series_means_no_spokes():
    assert len(RadarGeometry.angles(0)) == 0


def test_a_value_maps_between_the_centre_and_the_outer_ring():
    spec = Registry.SERIES["pitch"]          # 0-350 Hz
    low, middle, high = RadarGeometry.radius(
        [spec.default_min, (spec.default_min + spec.default_max) / 2, spec.default_max], spec)
    assert low == pytest.approx(RadarGeometry.INNER_RADIUS)
    assert high == pytest.approx(RadarGeometry.OUTER_RADIUS)
    assert low < middle < high


def test_a_value_off_the_scale_is_held_at_the_ring_rather_than_escaping():
    """Otherwise one wild frame would drag the drawing outside its own frame."""
    spec = Registry.SERIES["pitch"]
    below, above = RadarGeometry.radius([-1000.0, 1e6], spec)
    assert below == pytest.approx(RadarGeometry.INNER_RADIUS)
    assert above == pytest.approx(RadarGeometry.OUTER_RADIUS)


def test_a_series_with_no_range_at_all_still_lands_on_the_disc():
    """A degenerate registry range must not divide by zero."""
    spec = Registry.SeriesSpec(key="flat", label="Flat", default_min=5.0, default_max=5.0)
    assert RadarGeometry.radius([5.0], spec) == pytest.approx(RadarGeometry.INNER_RADIUS)


def test_a_point_sits_on_its_own_spoke():
    angle = RadarGeometry.angles(4)[1]
    x_values, y_values = RadarGeometry.to_xy([0.5], angle)
    assert np.arctan2(y_values[0], x_values[0]) == pytest.approx(angle)
    assert np.hypot(x_values[0], y_values[0]) == pytest.approx(0.5)


def test_a_target_box_straddles_its_spoke_over_the_range_it_marks():
    angle = RadarGeometry.angles(3)[0]       # straight up
    x_values, y_values = RadarGeometry.target_box(0.2, 0.6, angle)
    assert len(x_values) == 4
    # Pointing up, the box runs from 0.2 to 0.6 in Y and is symmetric in X.
    assert sorted(np.round(y_values, 6)) == [0.2, 0.2, 0.6, 0.6]
    assert x_values.min() == pytest.approx(-RadarGeometry.TARGET_HALF_WIDTH)
    assert x_values.max() == pytest.approx(RadarGeometry.TARGET_HALF_WIDTH)


def test_a_value_stroke_crosses_its_spoke_at_right_angles():
    angle = RadarGeometry.angles(5)[2]
    x0, y0, x1, y1 = RadarGeometry.value_ticks([0.4], angle)
    along = np.array([np.cos(angle), np.sin(angle)])
    stroke = np.array([x1[0] - x0[0], y1[0] - y0[0]])
    assert np.dot(stroke, along) == pytest.approx(0.0, abs=1e-12)


def test_a_value_stroke_is_three_quarters_of_the_target_box_it_sits_in():
    """The whole point of the stroke: whether it falls inside is read by eye."""
    angle = RadarGeometry.angles(3)[0]
    x0, y0, x1, y1 = RadarGeometry.value_ticks([0.4], angle)
    length = np.hypot(x1[0] - x0[0], y1[0] - y0[0])
    assert length == pytest.approx(0.75 * 2 * RadarGeometry.TARGET_HALF_WIDTH)


def test_a_value_stroke_is_centred_on_its_spoke():
    angle = RadarGeometry.angles(4)[3]
    x0, y0, x1, y1 = RadarGeometry.value_ticks([0.4], angle)
    middle = np.array([(x0[0] + x1[0]) / 2, (y0[0] + y1[0]) / 2])
    assert np.arctan2(middle[1], middle[0]) == pytest.approx(angle)
    assert np.hypot(*middle) == pytest.approx(0.4)


def test_every_value_gets_its_own_stroke():
    x0, _, _, _ = RadarGeometry.value_ticks([0.1, 0.2, 0.3], RadarGeometry.angles(2)[0])
    assert len(x0) == 3


# --- Scales --------------------------------------------------------------

@pytest.mark.parametrize("key, expected", [
    ("loudness", ["2", "4", "6", "8", "10"]),     # 0-10
    ("pitch", ["100", "200", "300"]),             # 0-350
    ("size", ["10", "20", "30"]),                 # 0-30
    ("jitter", ["0.05", "0.10", "0.15", "0.20"]),  # 0-0.2
])
def test_a_scale_is_marked_at_numbers_a_reader_recognises(key, expected):
    values, step = RadarGeometry.scale_ticks(Registry.SERIES[key])
    assert [RadarGeometry.format_tick(v, step) for v in values] == expected


def test_a_scale_never_marks_the_centre():
    """Every spoke meets there, so all of them would print a number on top of
    each other."""
    for spec in Registry.signal_series():
        values, _ = RadarGeometry.scale_ticks(spec)
        assert all(v > spec.default_min for v in values)


def test_a_scale_stays_inside_the_ring():
    for spec in Registry.signal_series():
        values, _ = RadarGeometry.scale_ticks(spec)
        assert all(v <= spec.default_max + 1e-9 for v in values)


def test_a_scale_over_no_range_at_all_is_simply_empty():
    spec = Registry.SeriesSpec(key="flat", label="Flat", default_min=5.0, default_max=5.0)
    assert RadarGeometry.scale_ticks(spec)[0] == []


def test_a_scale_crossing_zero_does_not_print_minus_zero():
    values, step = RadarGeometry.scale_ticks(Registry.SERIES["H1_H2"])   # -20..50
    assert "-0" not in [RadarGeometry.format_tick(v, step) for v in values]


def test_a_scale_mark_sits_either_side_of_the_spoke_clear_of_the_target_box():
    angle = RadarGeometry.angles(3)[0]      # straight up
    x0, y0, x1, y1 = RadarGeometry.scale_tick_marks(0.5, angle)
    assert len(x0) == 2
    # Pointing up, the marks run outwards in X from the box edge, at height 0.5.
    assert sorted(np.round(np.abs(x0), 6)) == [RadarGeometry.SCALE_TICK_INNER] * 2
    assert sorted(np.round(np.abs(x1), 6)) == [RadarGeometry.SCALE_TICK_OUTER] * 2
    assert np.allclose(list(y0) + list(y1), 0.5)
    assert x0[0] * x0[1] < 0            # one either side


def test_a_scale_number_is_printed_on_both_sides_of_its_mark():
    angle = RadarGeometry.angles(3)[1]
    left, right = RadarGeometry.scale_label_points(0.5, angle)
    middle = (np.asarray(left) + np.asarray(right)) / 2
    assert np.hypot(*middle) == pytest.approx(0.5)
    assert np.hypot(*(np.asarray(left) - middle)) == pytest.approx(
        RadarGeometry.SCALE_LABEL_OFFSET)


def test_six_spokes_fit_without_their_scales_running_into_each_other():
    """The width of an axis is what limits how many will fit.

    An axis is a column ``SCALE_LABEL_OFFSET`` wide either side of its spoke,
    and the room between two spokes is narrowest at the innermost number
    printed on them. Six is the count this was sized for; it failed at four
    when the column was twice as wide.
    """
    innermost = min(
        float(RadarGeometry.radius([values[0]], spec)[0])
        for spec in Registry.signal_series()
        for values, _ in [RadarGeometry.scale_ticks(spec)] if values)

    half_gap = innermost * np.sin(np.pi / 6)      # 6 spokes, 60 degrees apart
    assert RadarGeometry.SCALE_LABEL_OFFSET < half_gap


def test_a_scale_mark_and_its_number_clear_the_target_box():
    order = (RadarGeometry.TARGET_HALF_WIDTH,
             RadarGeometry.SCALE_TICK_INNER,
             RadarGeometry.SCALE_TICK_OUTER,
             RadarGeometry.SCALE_LABEL_OFFSET)
    assert list(order) == sorted(order)


def test_the_view_leaves_room_outside_the_ring_for_the_labels():
    low, high = RadarGeometry.VIEW_RANGE
    assert low == -high
    assert high > RadarGeometry.OUTER_RADIUS + RadarGeometry.LABEL_MARGIN


# --- Configuration -------------------------------------------------------

def test_radar_on_x_makes_a_radar_however_many_series_are_on_y():
    for keys in (["pitch"], ["pitch", "size"], ["pitch", "size", "weight", "F1"]):
        config = radar(keys)
        assert config.kind is PlotKind.RADAR
        assert [s.key for s in config.radar_specs()] == keys


def test_only_a_radar_has_spokes():
    assert PlotConfig(x=["time"], y=["pitch", "size"]).normalised().radar_specs() == []
    assert PlotConfig(x=["size"], y=["pitch"]).normalised().radar_specs() == []


def test_choosing_radar_clears_whatever_shared_the_x_axis():
    """``radar`` is exclusive, like time and frequency."""
    config = PlotConfig(x=[RADAR, "F1", "F2"], y=["pitch"]).normalised()
    assert config.x == [RADAR]


def test_a_radar_with_nothing_on_it_falls_back_rather_than_drawing_blank():
    config = PlotConfig(x=[RADAR], y=[]).normalised()
    assert config.kind is PlotKind.RADAR
    assert config.y


def test_the_synthetic_series_are_dropped_off_the_spokes():
    """Magnitude is left over from a spectrum slice; it has no data here."""
    config = PlotConfig(x=[RADAR], y=[Registry.MAGNITUDE_KEY]).normalised()
    assert Registry.MAGNITUDE_KEY not in config.y


def test_a_radar_takes_no_spectrogram():
    config = radar(["pitch"], spectrogram=True)
    assert not config.spectrogram
    assert not config.spectrogram_allowed()


def test_a_radar_has_no_axis_to_split():
    """Each spoke already has a scale of its own, so the option means nothing."""
    config = radar(["pitch", "size", "weight"], separate_axes=True)
    assert config.multi_axis() is None
    assert not config.separate_axes_allowed()
    assert not config.separate_axes


def test_both_axes_show_the_same_square_view():
    config = radar(["pitch", "size"])
    assert config.effective_x_range() == config.effective_y_range()
    assert config.effective_y_range() == RadarGeometry.VIEW_RANGE


def test_a_stale_range_from_another_plot_does_not_squash_the_rings():
    config = radar(["pitch"], y_range=(0.0, 350.0))
    assert config.effective_y_range() == RadarGeometry.VIEW_RANGE


def test_a_radar_is_neither_a_time_plot_nor_a_trail():
    config = radar(["pitch", "size"])
    assert not config.is_time_domain
    assert config.time_axis is None
    assert config.frequency_axis() is None


def test_the_title_names_every_spoke():
    assert radar(["pitch", "size"]).title() == "Radar: Pitch, Size"


def test_a_radar_survives_a_layout_round_trip():
    config = radar(["pitch", "size", "weight"], trail_time=5.0)
    restored = PlotConfig.from_layout_entry(config.to_dict())
    assert restored.kind is PlotKind.RADAR
    assert restored.y == ["pitch", "size", "weight"]
    assert restored.trail_time == 5.0
