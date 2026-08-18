"""What the chunk cache promises: correct stitching, and no wasted work.

The extractor is stubbed out. These tests are about which chunks get looked at
and how their results are joined up, and a stub makes both observable -- the
real extractor takes seconds per chunk and its output cannot be predicted from
the input.
"""

import numpy as np
import pytest

from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, SpectrogramData
from signal_processing.ChunkedAnalysis import (AnalysisCancelled, ChunkedAudioAnalysis,
                                               aligned_chunk_samples)

SAMPLE_RATE = 44100
FRAME_SECONDS = 0.01
#: Stand-in for the spectrogram's frequency bins.
BINS = 4


@pytest.fixture
def calls():
    return []


@pytest.fixture
def analyse(calls):
    """A stub extractor that records what it was asked to analyse.

    Every frame reports the mean sample value over the audio it covers, so a
    stitched timeline can be checked against the audio it came from.
    """

    def analyse_chunk(samples, sample_rate):
        calls.append(len(samples))
        step = int(round(FRAME_SECONDS * sample_rate))
        count = max(0, len(samples) // step)
        times = np.arange(count) * FRAME_SECONDS
        values = np.array([samples[i * step:(i + 1) * step].mean() for i in range(count)])

        features = AudioFeatures(sample_rate=sample_rate,
                                 length_seconds=len(samples) / float(sample_rate))
        features.pitch = SignalTimeSeries(x=times, y=values)
        features.loudness = SignalTimeSeries(x=times, y=values * 2)
        features.spectrogram = SpectrogramData(
            x=times, y=np.arange(BINS, dtype=float),
            magnitude_db=np.tile(values, (BINS, 1)))
        return features

    return analyse_chunk


def audio(seconds, seed=0, sample_rate=SAMPLE_RATE):
    """A deterministic waveform that never repeats itself.

    Constant audio would hide the thing several of these tests are about: after
    a cut, the audio downstream of it has *moved*, and the chunks covering it
    have to notice. It is biased away from zero so that a silenced stretch is
    the only part whose frames average to exactly nothing.
    """
    count = int(seconds * sample_rate)
    return np.random.default_rng(seed).integers(1000, 9000, size=count, dtype=np.int16)


def chunk_seconds(sample_rate=SAMPLE_RATE):
    return aligned_chunk_samples(10.0, sample_rate) / sample_rate


# --- Chunk length --------------------------------------------------------

def test_chunk_length_is_a_whole_number_of_analysis_steps():
    samples = aligned_chunk_samples(10.0, SAMPLE_RATE)
    assert samples % 1024 == 0, "must tile the spectrogram hop"
    assert samples % 441 == 0, "must tile openSMILE's 10 ms frame"
    assert abs(samples / SAMPLE_RATE - 10.0) < 0.5


def test_chunk_length_never_rounds_down_to_nothing():
    assert aligned_chunk_samples(0.001, SAMPLE_RATE) == 1024 * 441


# --- Stitching -----------------------------------------------------------

def test_assembled_timeline_covers_the_whole_buffer(analyse):
    seconds = chunk_seconds() * 2.5
    features = ChunkedAudioAnalysis().analyse(audio(seconds).tobytes(), SAMPLE_RATE, analyse)

    assert features.length_seconds == pytest.approx(seconds)
    assert features.sample_rate == SAMPLE_RATE
    assert np.all(np.diff(features.pitch.x) > 0), "times must not go backwards"
    assert features.pitch.x[0] == pytest.approx(0.0)
    assert features.pitch.x[-1] == pytest.approx(seconds - FRAME_SECONDS, abs=FRAME_SECONDS)
    assert len(features.pitch.y) == len(features.pitch.x)


def test_frames_line_up_with_the_audio_underneath_them(analyse):
    """A quiet second in the middle has to come back at the time it went in."""
    samples = audio(chunk_seconds() * 3)
    start, end = int(15.0 * SAMPLE_RATE), int(16.0 * SAMPLE_RATE)
    samples[start:end] = 0

    features = ChunkedAudioAnalysis().analyse(samples.tobytes(), SAMPLE_RATE, analyse)
    quiet = features.pitch.x[np.abs(features.pitch.y) < 1e-9]

    assert quiet.min() == pytest.approx(15.0, abs=FRAME_SECONDS)
    assert quiet.max() == pytest.approx(16.0 - FRAME_SECONDS, abs=FRAME_SECONDS)


def test_spectrogram_columns_match_the_frames(analyse):
    features = ChunkedAudioAnalysis().analyse(
        audio(chunk_seconds() * 2.5).tobytes(), SAMPLE_RATE, analyse)

    spectrogram = features.spectrogram
    assert spectrogram.magnitude_db.shape == (BINS, len(spectrogram.x))
    assert len(spectrogram.y) == BINS
    assert np.all(np.diff(spectrogram.x) > 0)


def test_empty_buffer_gives_an_empty_record(analyse, calls):
    features = ChunkedAudioAnalysis().analyse(b"", SAMPLE_RATE, analyse)

    assert calls == []
    assert features.length_seconds == 0.0
    assert len(features.pitch.x) == 0


# --- Reuse ---------------------------------------------------------------

def test_unchanged_audio_is_not_analysed_twice(analyse, calls):
    cache = ChunkedAudioAnalysis()
    buffer = audio(chunk_seconds() * 3).tobytes()

    first = cache.analyse(buffer, SAMPLE_RATE, analyse)
    calls.clear()
    second = cache.analyse(buffer, SAMPLE_RATE, analyse)

    assert calls == []
    assert cache.last_analysed == 0
    assert cache.last_reused == cache.chunk_count
    assert np.array_equal(first.pitch.y, second.pitch.y)


def test_recording_onto_the_end_only_analyses_the_end(analyse, calls):
    cache = ChunkedAudioAnalysis()
    samples = audio(chunk_seconds() * 2.5)
    cache.analyse(samples.tobytes(), SAMPLE_RATE, analyse)

    calls.clear()
    longer = np.concatenate([samples, audio(2.0, seed=1)])
    features = cache.analyse(longer.tobytes(), SAMPLE_RATE, analyse)

    assert cache.last_analysed == 1, "only the chunk the new audio landed in"
    assert cache.last_reused == 2
    assert features.length_seconds == pytest.approx(chunk_seconds() * 2.5 + 2.0)


def test_recording_past_a_boundary_still_leaves_the_earlier_chunks_alone(analyse):
    """A take that fills the buffer to the brim redoes the last chunk too.

    Its trailing context used to run off the end of the recording and now has
    audio in it, so it is genuinely stale -- but only it.
    """
    cache = ChunkedAudioAnalysis()
    samples = audio(chunk_seconds() * 3)
    cache.analyse(samples.tobytes(), SAMPLE_RATE, analyse)

    longer = np.concatenate([samples, audio(2.0, seed=1)])
    cache.analyse(longer.tobytes(), SAMPLE_RATE, analyse)

    assert cache.last_reused == 2
    assert cache.last_analysed == 2


def test_an_edit_in_the_middle_of_a_chunk_leaves_its_neighbours_alone(analyse):
    cache = ChunkedAudioAnalysis()
    samples = audio(chunk_seconds() * 4)
    cache.analyse(samples.tobytes(), SAMPLE_RATE, analyse)

    # Well inside chunk 2, clear of the context its neighbours are analysed with.
    edited = samples.copy()
    middle = int(chunk_seconds() * 2.5 * SAMPLE_RATE)
    edited[middle:middle + SAMPLE_RATE] = 0
    cache.analyse(edited.tobytes(), SAMPLE_RATE, analyse)

    assert cache.last_analysed == 1
    assert cache.last_reused == 3


def test_an_edit_next_to_a_boundary_invalidates_the_chunk_over_it(analyse):
    """The neighbour was analysed with this audio as context, so it is stale."""
    cache = ChunkedAudioAnalysis()
    samples = audio(chunk_seconds() * 4)
    cache.analyse(samples.tobytes(), SAMPLE_RATE, analyse)

    edited = samples.copy()
    boundary = int(chunk_seconds() * 2 * SAMPLE_RATE)
    edited[boundary:boundary + SAMPLE_RATE // 10] = 0
    cache.analyse(edited.tobytes(), SAMPLE_RATE, analyse)

    assert cache.last_analysed == 2, "the chunk edited, and the one before it"
    assert cache.last_reused == 2


def test_cutting_audio_out_shifts_and_invalidates_the_tail(analyse):
    cache = ChunkedAudioAnalysis()
    samples = audio(chunk_seconds() * 3)
    cache.analyse(samples.tobytes(), SAMPLE_RATE, analyse)

    cut = np.concatenate([samples[:SAMPLE_RATE], samples[2 * SAMPLE_RATE:]])
    features = cache.analyse(cut.tobytes(), SAMPLE_RATE, analyse)

    assert cache.last_analysed == 3
    assert features.length_seconds == pytest.approx(chunk_seconds() * 3 - 1.0)


def test_shortening_the_buffer_drops_the_chunks_past_the_end(analyse):
    cache = ChunkedAudioAnalysis()
    cache.analyse(audio(chunk_seconds() * 3).tobytes(), SAMPLE_RATE, analyse)
    assert cache.chunk_count == 3

    features = cache.analyse(audio(chunk_seconds()).tobytes(), SAMPLE_RATE, analyse)

    assert cache.chunk_count == 1
    assert features.pitch.x[-1] < chunk_seconds()


def test_a_new_sample_rate_starts_over(analyse):
    cache = ChunkedAudioAnalysis()
    cache.analyse(audio(chunk_seconds() * 2).tobytes(), SAMPLE_RATE, analyse)

    other = 22050
    cache.analyse(audio(chunk_seconds(other) * 2, sample_rate=other).tobytes(), other, analyse)

    assert cache.last_reused == 0


def test_reset_forgets_everything(analyse):
    cache = ChunkedAudioAnalysis()
    buffer = audio(chunk_seconds() * 2).tobytes()
    cache.analyse(buffer, SAMPLE_RATE, analyse)

    cache.reset()
    cache.analyse(buffer, SAMPLE_RATE, analyse)

    assert cache.last_analysed == 2
    assert cache.last_reused == 0


# --- Cancellation --------------------------------------------------------

def test_cancelling_keeps_the_chunks_already_done(analyse, calls):
    cache = ChunkedAudioAnalysis()
    buffer = audio(chunk_seconds() * 4).tobytes()

    with pytest.raises(AnalysisCancelled):
        cache.analyse(buffer, SAMPLE_RATE, analyse,
                      is_cancelled=lambda: len(calls) >= 2)

    assert cache.chunk_count == 2

    calls.clear()
    cache.analyse(buffer, SAMPLE_RATE, analyse)

    assert cache.last_reused == 2, "the two that finished are still good"
    assert cache.last_analysed == 2
