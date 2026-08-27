"""What Weight promises: the length of the (50 - H1-A3, loudness) vector.

Plain arithmetic over two frame-aligned arrays, so none of this needs a screen,
openSMILE or a real recording -- a handful of hand-computed frames is enough.
The one thing worth pinning beyond the maths is that a frame the extractor
rejected stays rejected: NaN in, NaN out, so it never reaches a plot.
"""

import numpy as np
import pytest

import SeriesRegistry as Registry
from signal_processing.TargetConfig import TargetConfig
from signal_processing.Weight import H1_A3_REFERENCE, calculate_weight


@pytest.mark.parametrize("h1_a3, loudness, expected", [
    (H1_A3_REFERENCE, 0.0, 0.0),          # at the reference, silent: no weight
    (H1_A3_REFERENCE, 3.0, 3.0),          # at the reference: loudness alone
    (H1_A3_REFERENCE - 4.0, 0.0, 4.0),    # silent: the H1-A3 distance alone
    (47.0, 4.0, 5.0),                     # both: a 3-4-5 triangle
    (H1_A3_REFERENCE + 3.0, 4.0, 5.0),    # above the reference is still a distance
])
def test_weight_is_the_length_of_the_vector(h1_a3, loudness, expected):
    result = calculate_weight(np.array([0.0]), np.array([h1_a3]), np.array([loudness]))
    assert result.y == pytest.approx([expected])


def test_timepoints_are_passed_through_untouched():
    t = np.array([0.0, 0.01, 0.02])
    result = calculate_weight(t, np.array([50.0, 47.0, 40.0]), np.array([0.0, 4.0, 0.0]))

    assert result.x == pytest.approx(t)
    assert result.y == pytest.approx([0.0, 5.0, 10.0])


@pytest.mark.parametrize("h1_a3, loudness", [
    (np.nan, 1.0),
    (45.0, np.nan),
    (np.nan, np.nan),
])
def test_a_rejected_frame_stays_rejected(h1_a3, loudness):
    """The extractor NaNs frames that fail its validity check; so does Weight."""
    result = calculate_weight(np.array([0.0]), np.array([h1_a3]), np.array([loudness]))
    assert np.isnan(result.y).all()


def test_a_rejected_frame_does_not_take_its_neighbours_with_it():
    result = calculate_weight(np.arange(3.0),
                              np.array([47.0, np.nan, 47.0]),
                              np.array([4.0, 4.0, 4.0]))

    assert np.isnan(result.y[1])
    assert result.y[[0, 2]] == pytest.approx([5.0, 5.0])


def test_no_frames_gives_an_empty_series():
    result = calculate_weight(np.array([]), np.array([]), np.array([]))

    assert result.x.size == 0
    assert result.y.size == 0


def test_weight_is_a_registered_series_with_a_target():
    spec = Registry.get("weight")

    assert spec is not None and spec.is_signal
    assert TargetConfig().get_bounds(spec.target_key) is not None


def test_the_registry_agrees_with_the_data_model():
    Registry.self_check()
