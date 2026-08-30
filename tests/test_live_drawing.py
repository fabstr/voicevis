"""What a plot draws while recording, and what it costs to draw it.

Both are about the same thing: a live take grows a hundred frames a second, and
a redraw that touches every frame so far gets slower the longer the take runs.
A coloured series is the worst of them -- no clipping, no downsampling, and a
brush per point -- so what is checked here is that the work per redraw is
bounded by the window on screen and by the number of distinct colours, not by
the length of the recording.
"""

import numpy as np

from ui.plot.ColourMapping import (ALPHA_LEVELS, COLOUR_LEVELS, brushes,
                                   fade_pens, normalise_to, rgba, solid_brushes)
from ui.plot.TimeAxisSyncGroup import RECORD_LOOKAHEAD, RECORD_WINDOW
from ui.plot.renderers.TimeScatterRenderer import TimeScatterRenderer, _inside


class FakeHub:
    def __init__(self, recording: bool):
        self.is_recording = recording


def renderer_for(recording: bool) -> TimeScatterRenderer:
    """A renderer with nothing but a hub, which is all the window needs."""
    renderer = TimeScatterRenderer.__new__(TimeScatterRenderer)
    renderer.hub = FakeHub(recording)
    return renderer


#################### The window drawn while recording ####################

def test_a_finished_recording_is_drawn_whole():
    assert renderer_for(recording=False)._live_window(12.0) is None


def test_a_live_recording_is_drawn_over_the_window_on_screen():
    low, high = renderer_for(recording=True)._live_window(60.0)

    # The view runs from RECORD_WINDOW back of the playhead to RECORD_LOOKAHEAD
    # past it; anything drawn outside that cannot be looked at.
    assert low <= 60.0 - RECORD_WINDOW
    assert high >= 60.0 + RECORD_LOOKAHEAD


def test_the_window_crops_both_arrays_together():
    times = np.arange(0.0, 10.0, 0.01)
    values = times * 2

    cropped_times, cropped_values = _inside((4.0, 6.0), times, values)

    assert cropped_times[0] >= 4.0 and cropped_times[-1] <= 6.0
    assert np.allclose(cropped_values, cropped_times * 2)


def test_no_window_leaves_the_arrays_alone():
    times, values = np.arange(5.0), np.arange(5.0)

    assert _inside(None, times, values) == (times, values)


def test_an_empty_series_survives_the_window():
    times, values = _inside((1.0, 2.0), np.empty(0), np.empty(0))

    assert len(times) == 0 and len(values) == 0


def test_what_is_drawn_does_not_grow_with_the_recording():
    """The whole point: a longer take must not mean more points per redraw."""
    window = renderer_for(recording=True)._live_window(600.0)
    times = np.arange(0.0, 600.0, 0.01)

    drawn, _ = _inside(window, times, times)

    assert len(drawn) < len(times) / 10


#################### The cost of colouring them ####################

def test_the_same_colour_is_the_same_brush():
    colours = rgba(np.array([0.5, 0.5]))

    first, second = brushes(colours)

    assert first is second


def test_a_long_series_comes_out_in_few_distinct_brushes():
    values = normalise_to(np.random.default_rng(0).uniform(0, 1, 20000), 0.0, 1.0)

    distinct = {id(brush) for brush in brushes(rgba(values))}

    assert len(distinct) <= COLOUR_LEVELS


def test_a_fade_comes_out_in_few_distinct_brushes_and_pens():
    alpha = np.linspace(0, 255, 5000)

    faded = solid_brushes("#ff8800", alpha)
    pens = fade_pens((128, 128, 128), alpha * 0.5)

    assert len({id(brush) for brush in faded}) <= ALPHA_LEVELS
    assert len({id(pen) for pen in pens}) <= ALPHA_LEVELS


def test_quantising_keeps_the_colours_it_was_given():
    """Rounding to the map's own resolution must not shift a colour visibly."""
    values = np.linspace(0.0, 1.0, 512)

    coarse = rgba(values).astype(int)
    ends = rgba(np.array([0.0, 1.0])).astype(int)

    assert np.array_equal(coarse[0], ends[0])
    assert np.array_equal(coarse[-1], ends[1])
