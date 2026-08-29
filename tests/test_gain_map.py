"""What a gain promises: it lands where it was asked for, and it follows the audio.

The map is arithmetic over ranges, so none of this needs a screen or a real
recording -- a few seconds of a constant tone is enough to see a factor applied
to one stretch and not to its neighbour.
"""

import numpy as np
import pytest

from signal_processing.GainMap import (FULL_SCALE, GainMap, INFINITY,
                                       NORMALISE_CEILING_DB, normalising_gain,
                                       peak_level, to_factor)

SAMPLE_RATE = 1000
LEVEL = 1000


def audio(seconds, level=LEVEL, sample_rate=SAMPLE_RATE):
    """A constant-level buffer, so a gain shows up as a plain multiplication."""
    return np.full(int(seconds * sample_rate), level, dtype='<i2').tobytes()


def levels(audio_bytes):
    return np.frombuffer(audio_bytes, dtype='<i2')


@pytest.fixture
def gains():
    return GainMap()


# --- Setting and removing ------------------------------------------------

def test_a_new_map_is_empty(gains):
    assert gains.is_empty
    assert gains.uniform_gain(0.0, INFINITY) == 0.0


def test_setting_a_gain_over_the_whole_recording(gains):
    assert gains.set_gain(0.0, INFINITY, 6.0)
    assert gains.uniform_gain(0.0, INFINITY) == 6.0
    assert gains.segments()[0].covers_everything


def test_setting_a_gain_over_a_range_leaves_its_neighbours_alone(gains):
    gains.set_gain(0.0, INFINITY, 6.0)
    gains.set_gain(1.0, 2.0, -3.0)

    assert gains.uniform_gain(1.0, 2.0) == -3.0
    assert gains.uniform_gain(0.0, 1.0) == 6.0
    assert gains.uniform_gain(2.0, 3.0) == 6.0


def test_a_range_carrying_two_gains_has_no_single_gain(gains):
    gains.set_gain(0.0, 1.0, 6.0)
    gains.set_gain(1.0, 2.0, -6.0)

    assert gains.uniform_gain(0.0, 2.0) is None


def test_zero_db_removes_the_gain_over_that_range_only(gains):
    gains.set_gain(0.0, 3.0, 6.0)
    assert gains.set_gain(1.0, 2.0, 0.0)

    assert gains.uniform_gain(1.0, 2.0) == 0.0
    assert gains.uniform_gain(0.0, 1.0) == 6.0
    assert gains.uniform_gain(2.0, 3.0) == 6.0


def test_reapplying_the_same_gain_changes_nothing(gains):
    assert gains.set_gain(0.0, 1.0, 6.0)
    assert not gains.set_gain(0.0, 1.0, 6.0)


def test_an_empty_range_is_not_a_gain(gains):
    assert not gains.set_gain(1.0, 1.0, 6.0)
    assert gains.is_empty


# --- Applying ------------------------------------------------------------

def test_an_empty_map_hands_the_audio_straight_back(gains):
    original = audio(1.0)
    result, clipped = gains.apply(original, SAMPLE_RATE)

    assert result is original
    assert not clipped


def test_a_gain_multiplies_only_its_own_range(gains):
    gains.set_gain(1.0, 2.0, 6.0)
    result, clipped = gains.apply(audio(3.0), SAMPLE_RATE)

    values = levels(result)
    assert values[:SAMPLE_RATE].tolist() == [LEVEL] * SAMPLE_RATE
    assert values[2 * SAMPLE_RATE:].tolist() == [LEVEL] * SAMPLE_RATE
    assert values[SAMPLE_RATE:2 * SAMPLE_RATE] == pytest.approx(
        round(LEVEL * to_factor(6.0)), abs=1)
    assert not clipped


def test_attenuation_is_a_negative_gain(gains):
    gains.set_gain(0.0, INFINITY, -6.0)
    values = levels(gains.apply(audio(1.0), SAMPLE_RATE)[0])

    assert values.max() == pytest.approx(round(LEVEL * to_factor(-6.0)), abs=1)


def test_a_gain_to_infinity_covers_audio_recorded_later(gains):
    gains.set_gain(0.0, INFINITY, 6.0)
    short = levels(gains.apply(audio(1.0), SAMPLE_RATE)[0])
    longer = levels(gains.apply(audio(5.0), SAMPLE_RATE)[0])

    assert longer.min() == short.min() == short.max()


def test_an_offset_places_a_live_chunk_in_the_recording(gains):
    gains.set_gain(2.0, 3.0, 6.0)
    # The chunk covering 2..3s, handed over on its own while recording.
    chunk, _ = gains.apply(audio(1.0), SAMPLE_RATE, offset_seconds=2.0)

    assert levels(chunk).min() == pytest.approx(round(LEVEL * to_factor(6.0)), abs=1)


def test_samples_past_full_scale_are_clamped_and_reported(gains):
    gains.set_gain(0.0, INFINITY, 20.0)
    loud = audio(1.0, level=20000)

    assert gains.clips(loud, SAMPLE_RATE)
    result, clipped = gains.apply(loud, SAMPLE_RATE)
    assert clipped
    assert levels(result).max() == 32767


def test_a_gain_that_stays_inside_full_scale_does_not_clip(gains):
    gains.set_gain(0.0, INFINITY, 3.0)

    assert not gains.clips(audio(1.0), SAMPLE_RATE)
    assert not gains.apply(audio(1.0), SAMPLE_RATE)[1]


# --- Following the audio -------------------------------------------------

def test_a_cut_takes_the_gain_over_it_away(gains):
    gains.set_gain(1.0, 2.0, 6.0)
    gains.cut(1.0, 2.0)

    assert gains.is_empty


def test_a_cut_pulls_later_gains_back_with_the_audio(gains):
    gains.set_gain(4.0, 5.0, 6.0)
    gains.cut(1.0, 2.0)

    assert gains.uniform_gain(3.0, 4.0) == 6.0
    assert gains.uniform_gain(4.0, 5.0) == 0.0


def test_a_cut_through_a_gain_shortens_it(gains):
    gains.set_gain(1.0, 4.0, 6.0)
    gains.cut(2.0, 3.0)

    assert gains.uniform_gain(1.0, 3.0) == 6.0
    assert gains.uniform_gain(3.0, 4.0) == 0.0


def test_a_move_takes_the_gain_with_the_audio(gains):
    gains.set_gain(1.0, 2.0, 6.0)
    gains.move(1.0, 2.0, 3.0)

    assert gains.uniform_gain(4.0, 5.0) == 6.0
    assert gains.uniform_gain(1.0, 2.0) == 0.0


def test_a_move_overwrites_the_gain_where_it_lands(gains):
    gains.set_gain(0.0, 1.0, 6.0)
    gains.set_gain(3.0, 4.0, -6.0)
    gains.move(0.0, 1.0, 3.0)

    assert gains.uniform_gain(3.0, 4.0) == 6.0


def test_a_move_past_the_start_clips_the_gain_as_it_clips_the_audio(gains):
    gains.set_gain(1.0, 2.0, 6.0)
    gains.move(1.0, 2.0, -1.5)

    assert gains.uniform_gain(0.0, 0.5) == 6.0
    assert gains.uniform_gain(0.5, 2.0) == 0.0


def test_an_edit_that_moves_nothing_leaves_the_gains_alone(gains):
    gains.set_gain(1.0, 2.0, 6.0)
    before = gains.segments()

    gains.move(1.0, 2.0, 0.0)
    gains.cut(1.0, 1.0)

    assert gains.segments() == before


# --- Copying -------------------------------------------------------------

def test_a_copy_does_not_follow_the_original(gains):
    gains.set_gain(0.0, 1.0, 6.0)
    snapshot = gains.copy()

    gains.set_gain(0.0, 1.0, -6.0)

    assert snapshot.uniform_gain(0.0, 1.0) == 6.0
    assert gains.uniform_gain(0.0, 1.0) == -6.0


# --- Normalising ---------------------------------------------------------

def loudest_after(audio_bytes, db):
    """The loudest sample once ``db`` is applied over the whole of it."""
    gains = GainMap()
    gains.set_gain(0.0, INFINITY, db)
    gained, _ = gains.apply(audio_bytes, SAMPLE_RATE)
    return int(np.abs(levels(gained).astype(np.int32)).max())


def test_the_peak_is_read_over_the_range_asked_for():
    quiet, loud = audio(1.0, 100), audio(1.0, 8000)

    assert peak_level(quiet + loud, SAMPLE_RATE, 1.0, 2.0) == 8000
    assert peak_level(quiet + loud, SAMPLE_RATE, 0.0, 1.0) == 100
    assert peak_level(quiet + loud, SAMPLE_RATE) == 8000


def test_normalising_lifts_the_loudest_sample_to_just_below_full_scale():
    quiet = audio(1.0, 1000)

    db = normalising_gain(quiet, SAMPLE_RATE)

    assert db > 0
    assert loudest_after(quiet, db) == pytest.approx(
        FULL_SCALE * to_factor(NORMALISE_CEILING_DB), rel=1e-3)


def test_normalising_never_clips():
    hot = audio(1.0, FULL_SCALE)

    db = normalising_gain(hot, SAMPLE_RATE)

    assert db < 0
    gains = GainMap()
    gains.set_gain(0.0, INFINITY, db)
    assert not gains.clips(hot, SAMPLE_RATE)


def test_normalising_reads_the_range_asked_for_only():
    quiet, loud = audio(1.0, 100), audio(1.0, 8000)

    over_the_quiet_part = normalising_gain(quiet + loud, SAMPLE_RATE, 0.0, 1.0)

    assert over_the_quiet_part == pytest.approx(
        normalising_gain(quiet, SAMPLE_RATE))


def test_silence_has_no_normalising_gain():
    assert normalising_gain(audio(1.0, 0), SAMPLE_RATE) is None
    assert normalising_gain(b'', SAMPLE_RATE) is None
    assert normalising_gain(audio(1.0), SAMPLE_RATE, 5.0, 6.0) is None
