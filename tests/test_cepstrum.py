"""What CPPS promises: how far a voice's cepstral peak stands above its floor.

The measure is a chain of transforms, so the tests are about the properties
that chain has to preserve rather than about particular decibel values. That
distinction matters more here than for most units: absolute CPPS values are
implementation-dependent -- window length, band limit and smoothing widths each
move them -- so a test asserting "a periodic voice reads 21.4 dB" would be
pinning an accident. Every dB assertion below is a *difference* between two
signals or an *identity* between two views of one signal.

The test signal is a pulse train, which is what a cepstrum is for: a single
sine has no rhamonic at all, so it would pass any of this with a broken
implementation. A sum of harmonics works too, but has notches at particular
fundamentals that are properties of the sum, not of the measure.

No screen, no openSMILE, no recordings -- synthetic audio and seeded noise, so
nothing here is flaky.
"""

import numpy as np
import pytest

import SeriesRegistry as Registry
import signal_processing.Cepstrum as Cepstrum
from signal_processing import ChunkedAnalysis
from signal_processing.Cepstrum import (FRAME_SECONDS, HOP_SECONDS,
                                        PERIODS_PER_FRAME, PITCH_CEILING_HZ,
                                        PITCH_FLOOR_HZ, TIME_SMOOTHING_FRAMES,
                                        calculate_cpps,
                                        cepstral_peak_prominence)
from signal_processing.TargetConfig import TargetConfig

SAMPLE_RATE = 44100

#: Enough frames to have an interior; 1.4 s of audio covers them all.
TIMEPOINTS = np.arange(140) * HOP_SECONDS

#: The frames to judge by. A frame within a window's width of either end of the
#: audio is half zero-padding, and the temporal smoothing repeats the edge into
#: it, so those frames are legitimately not like the rest.
INTERIOR = slice(10, -10)


def pulse_train(f0, sample_rate=SAMPLE_RATE, seconds=1.5):
    """A periodic voice, reduced to the one property the cepstrum reads."""
    audio = np.zeros(int(sample_rate * seconds), dtype=np.float32)
    at = np.rint(np.arange(0, seconds * f0) * sample_rate / f0).astype(int)
    audio[at[at < audio.size]] = 1.0
    return audio


def steady(values):
    """The value the interior frames settled on."""
    return float(np.nanmedian(np.asarray(values)[INTERIOR]))


@pytest.mark.parametrize("f0", [80, 100, 150, 200, 300])
def test_the_peak_is_found_at_one_over_the_fundamental(f0):
    """The rhamonic sits at the pitch period. This is the cepstrum working."""
    _, quefrency = cepstral_peak_prominence(TIMEPOINTS, pulse_train(f0), SAMPLE_RATE)

    assert 1.0 / steady(quefrency) == pytest.approx(f0, rel=0.03)


def test_a_periodic_voice_stands_well_clear_of_noise():
    """The gap is the measure; neither number on its own means anything."""
    rng = np.random.default_rng(0)
    noise = (0.3 * rng.standard_normal(int(SAMPLE_RATE * 1.5))).astype(np.float32)

    periodic, _ = cepstral_peak_prominence(TIMEPOINTS, pulse_train(200), SAMPLE_RATE)
    aperiodic, _ = cepstral_peak_prominence(TIMEPOINTS, noise, SAMPLE_RATE)

    assert steady(periodic) > steady(aperiodic) + 5.0


def test_a_quiet_recording_reads_the_same_as_a_loud_one():
    """A prominence is a difference of two dB values, so gain cancels.

    It only cancels because the spectrum is floored relative to its own peak.
    Anyone who makes that floor absolute breaks this and nothing else.
    """
    audio = pulse_train(200)

    loud, _ = cepstral_peak_prominence(TIMEPOINTS, audio, SAMPLE_RATE)
    quiet, _ = cepstral_peak_prominence(TIMEPOINTS, audio * np.float32(0.01), SAMPLE_RATE)

    assert quiet == pytest.approx(loud, abs=0.05)


@pytest.mark.parametrize("count", [1, 7, 46, 140])
def test_there_is_exactly_one_value_per_timepoint(count):
    """The extractor masks the result frame by frame; it has to line up."""
    timepoints = np.arange(count) * HOP_SECONDS
    result = calculate_cpps(timepoints, pulse_train(180, seconds=2.0), SAMPLE_RATE)

    assert result.y.size == count
    assert result.x == pytest.approx(timepoints)


def test_timepoints_past_the_end_of_the_audio_are_still_answered():
    """The last chunk of a recording asks for frames the audio runs out under."""
    result = calculate_cpps(TIMEPOINTS, pulse_train(180, seconds=0.2), SAMPLE_RATE)

    assert result.y.size == TIMEPOINTS.size


def test_no_timepoints_gives_an_empty_series():
    result = calculate_cpps(np.array([]), pulse_train(200), SAMPLE_RATE)

    assert result.x.size == 0
    assert result.y.size == 0


def test_a_silent_frame_is_not_measured():
    """Silence has no cepstral peak, and a number there would be a fiction."""
    audio = np.concatenate([pulse_train(200, seconds=1.0),
                            np.zeros(SAMPLE_RATE // 2, dtype=np.float32)])
    values, _ = cepstral_peak_prominence(TIMEPOINTS, audio, SAMPLE_RATE)

    assert np.isnan(values[-15:]).all()


def test_a_silent_frame_does_not_drag_its_neighbours_down():
    """The smoothing steps over silence rather than averaging it in.

    Without that, silencing a selection would visibly pull down the frames on
    either side of the edit -- a measurement of the edit, not of the voice.
    """
    voice = pulse_train(200, seconds=1.0)
    edited = np.concatenate([voice, np.zeros(SAMPLE_RATE // 2, dtype=np.float32)])

    alone, _ = cepstral_peak_prominence(TIMEPOINTS, voice, SAMPLE_RATE)
    beside_silence, _ = cepstral_peak_prominence(TIMEPOINTS, edited, SAMPLE_RATE)

    assert beside_silence[10:90] == pytest.approx(alone[10:90], abs=1e-6)


@pytest.mark.parametrize("sample_rate", [16000, 22050, 44100, 48000])
def test_the_pitch_period_found_does_not_depend_on_the_sample_rate(sample_rate):
    """Band-limiting the spectrum is what puts every rate on one grid.

    The decibel value is deliberately *not* asserted across rates: the frame is
    a different number of samples at each, which moves it by a decibel or two.
    """
    _, quefrency = cepstral_peak_prominence(
        TIMEPOINTS, pulse_train(150, sample_rate), sample_rate)

    assert 1.0 / steady(quefrency) == pytest.approx(150, rel=0.03)


def test_blocking_the_transform_does_not_change_the_answer():
    """Long recordings are analysed a block at a time; the seams must not show."""
    timepoints = np.arange(290) * HOP_SECONDS
    audio = pulse_train(180, seconds=3.0)
    original = Cepstrum.BLOCK_FRAMES
    try:
        Cepstrum.BLOCK_FRAMES = 10_000
        whole, _ = cepstral_peak_prominence(timepoints, audio, SAMPLE_RATE)
        Cepstrum.BLOCK_FRAMES = 13
        blocked, _ = cepstral_peak_prominence(timepoints, audio, SAMPLE_RATE)
    finally:
        Cepstrum.BLOCK_FRAMES = original

    assert blocked == pytest.approx(whole, abs=1e-6)


def test_the_window_holds_enough_periods_of_the_lowest_pitch():
    """Fewer than four and the harmonics smear together at the pitch floor."""
    assert PERIODS_PER_FRAME >= 4
    assert FRAME_SECONDS * PITCH_FLOOR_HZ == pytest.approx(PERIODS_PER_FRAME)


def test_the_search_band_matches_the_extractor_s_validity_check():
    """``AudioFeatureExtractor.extractFeatures`` discards frames outside 65-500
    Hz, so looking for a rhamonic outside that range could only find noise."""
    assert (PITCH_FLOOR_HZ, PITCH_CEILING_HZ) == (65.0, 500.0)


def test_the_measure_fits_inside_the_context_a_chunk_is_given():
    """The invariant that keeps chunked and live analysis correct.

    A chunk is analysed with a second of audio either side and then trimmed, and
    a live pass sees half a second. Both hold as long as a frame's value depends
    only on audio close to it -- which is what this asserts, and what widening
    the window or the smoothing would quietly break.
    """
    support = FRAME_SECONDS / 2 + (TIME_SMOOTHING_FRAMES // 2) * HOP_SECONDS

    assert support < ChunkedAnalysis.CONTEXT_SECONDS
    # The live worker centres its newest frame no later than half its window.
    assert support < 0.25


def test_cpps_is_a_registered_series_with_a_target():
    spec = Registry.get("cpps")

    assert spec is not None and spec.is_signal
    assert TargetConfig().get_bounds(spec.target_key) is not None


def test_the_registry_agrees_with_the_data_model():
    Registry.self_check()
