"""What the live analysis promises: the batch analysis' resolution, live.

A pass sees half a second of audio and re-sees most of it on the next pass, so
the thing to check is what comes out of a *run* of passes: every frame covering
new audio reported once, on the same grids the batch analysis uses.

The extractor is stubbed out. These tests are about which frames are picked out
of a pass and where they land on the timeline, and a stub makes both
observable -- the real extractor takes ~20 ms per pass and its output cannot be
predicted from the input.
"""

import numpy as np
import pytest

from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries, SpectrogramData
from ui.plot.PlotDataHub import PlotDataHub
from workers.RealTimeAnalysisWorker import RealTimeAnalysisWorker

SAMPLE_RATE = 44100
FRAME_SECONDS = 0.01
#: The extractor's spectrogram hop, in samples and in seconds.
SPECTROGRAM_HOP = 1024
SPECTROGRAM_SECONDS = SPECTROGRAM_HOP / float(SAMPLE_RATE)
#: Stand-in for the spectrogram's frequency bins.
BINS = 4


class FakeExtractor:
    """Frames every 10 ms, each reporting where it sits in the audio given."""

    def analyzePCM(self, pcm_data, sampling_rate, with_spectrogram=True):
        step = int(round(FRAME_SECONDS * sampling_rate))
        count = max(0, (len(pcm_data) - step) // step + 1)
        times = np.arange(count) * FRAME_SECONDS

        features = AudioFeatures(sample_rate=sampling_rate,
                                 length_seconds=len(pcm_data) / float(sampling_rate))
        for name in ("pitch", "loudness", "weight", "jitter", "shimmer",
                     "F1", "F2", "F3", "H1_H2", "H1_H3", "H1_H4", "H1_A3",
                     "F1_Pitch", "F2_Pitch", "F3_Pitch", "size"):
            setattr(features, name, SignalTimeSeries(x=times, y=np.arange(count, dtype=float)))
        return features


def spectrogram_of(samples, sample_rate):
    """Columns on the same hop the real STFT uses, over the audio given."""
    count = max(0, (len(samples) - 4 * SPECTROGRAM_HOP) // SPECTROGRAM_HOP + 1)
    times = (np.arange(count) * SPECTROGRAM_HOP + 2 * SPECTROGRAM_HOP) / float(sample_rate)
    return SpectrogramData(x=times, y=np.arange(BINS, dtype=float),
                           magnitude_db=np.tile(np.arange(count, dtype=float), (BINS, 1)))


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr("workers.RealTimeAnalysisWorker.calculate_spectrogram",
                        spectrogram_of)
    return RealTimeAnalysisWorker(FakeExtractor(), None, SAMPLE_RATE)


def run_passes(worker, seconds, poll_seconds=0.033):
    """Drive the worker's per-pass work by hand, as ``run`` would.

    ``run`` itself blocks on the audio queue, so the loop body is repeated here
    rather than started as a thread. It is the frame bookkeeping that is under
    test, not the queue draining.
    """
    poll_samples = int(SAMPLE_RATE * poll_seconds)
    snapshots = []

    while worker.total_samples_processed < seconds * SAMPLE_RATE:
        worker.total_samples_processed += poll_samples
        if worker.total_samples_processed <= worker.window_size_samples / 2:
            continue

        start = worker.total_samples_processed - worker.window_size_samples
        frame_start = worker._align(start, worker.frame_hop_samples)
        results = worker.extractor.analyzePCM(
            worker.sliding_buffer[frame_start - start:], SAMPLE_RATE,
            with_spectrogram=False)

        spectrogram_start = worker._align(start, worker.spectrogram_hop_samples)
        spectrogram = spectrogram_of(worker.sliding_buffer[spectrogram_start - start:],
                                     SAMPLE_RATE)

        snapshots.extend(worker._build_snapshots(
            results, frame_start / float(SAMPLE_RATE),
            spectrogram, spectrogram_start / float(SAMPLE_RATE)))

    return snapshots


def test_every_frame_of_the_recording_is_reported_once(worker):
    times = [snapshot.time for snapshot in run_passes(worker, seconds=5.0)]

    assert times == sorted(times)
    assert len(times) == len(set(np.round(times, 6)))
    # One frame per 10 ms step, give or take the pass that has not run yet.
    assert np.allclose(np.diff(times), FRAME_SECONDS)


def test_frames_land_on_the_batch_analysis_grid(worker):
    times = np.array([snapshot.time for snapshot in run_passes(worker, seconds=5.0)])

    # The batch analysis puts frame k at k * 10 ms from the start of the
    # recording, and so must these, or the two timelines do not line up.
    steps = times / FRAME_SECONDS
    assert np.allclose(steps, np.round(steps))


def test_spectrogram_columns_keep_an_even_spacing(worker):
    columns = [snapshot.spectrogram for snapshot in run_passes(worker, seconds=5.0)
               if snapshot.spectrogram is not None]
    times = np.array([float(column.x[0]) for column in columns])

    assert len(times) > 1
    # The plot draws the columns evenly whatever their times say, so an uneven
    # spacing stretches the image away from the curves behind it.
    assert np.allclose(np.diff(times), SPECTROGRAM_SECONDS)

    steps = times * SAMPLE_RATE / SPECTROGRAM_HOP
    assert np.allclose(steps, np.round(steps))


def test_a_pass_carries_more_than_one_frame(worker):
    """The point of the exercise: a pass no longer reports only its newest frame."""
    worker.total_samples_processed = worker.window_size_samples
    results = worker.extractor.analyzePCM(worker.sliding_buffer, SAMPLE_RATE)
    spectrogram = spectrogram_of(worker.sliding_buffer, SAMPLE_RATE)

    first = worker._build_snapshots(results, 0.0, spectrogram, 0.0)
    assert len(first) > 1

    # Nothing new has arrived, so a repeat pass has nothing to add.
    assert worker._build_snapshots(results, 0.0, spectrogram, 0.0) == []


def test_the_hub_takes_a_whole_pass(worker):
    hub = PlotDataHub(AudioFeatures())
    hub.begin_recording()
    snapshots = run_passes(worker, seconds=3.0)
    hub.append_snapshots(snapshots)

    x, _ = hub.get_xy("pitch")
    assert len(x) == len(snapshots)

    spectrogram = hub.spectrogram()
    columns = sum(1 for snapshot in snapshots if snapshot.spectrogram is not None)
    assert spectrogram.magnitude_db.shape == (BINS, columns)

    hub.end_recording()
    stored = hub.spectrogram()
    assert stored.magnitude_db.shape == (BINS, columns)
    assert np.array_equal(stored.x, spectrogram.x)


def test_a_column_of_the_wrong_height_is_dropped(worker):
    """A live column that does not fit the bins is ignored, not stacked wrong."""
    hub = PlotDataHub(AudioFeatures())
    hub.begin_recording()

    snapshots = run_passes(worker, seconds=1.0)
    hub.append_snapshots(snapshots)
    before = hub.spectrogram().magnitude_db.shape

    odd = next(s for s in snapshots if s.spectrogram is not None)
    odd.spectrogram = SpectrogramData(x=np.array([99.0]), y=np.arange(BINS + 1, dtype=float),
                                      magnitude_db=np.zeros((BINS + 1, 1)))
    hub.append_snapshots([odd])

    assert hub.spectrogram().magnitude_db.shape == before


def test_a_bounded_live_buffer_drops_what_falls_behind(worker):
    """Monitoring never ends, so what it keeps has to stop growing."""
    history = 5.0
    hub = PlotDataHub(AudioFeatures())
    hub.begin_recording(history_seconds=history)

    for snapshot in run_passes(worker, seconds=60.0):
        hub.append_snapshots([snapshot])

    x, _ = hub.get_xy("pitch")
    spectrogram = hub.spectrogram()

    # Trimming happens a batch at a time, so the span settles between the
    # bound and the bound plus one batch rather than exactly on it.
    assert history <= (x[-1] - x[0]) <= history + 11.0
    assert spectrogram.magnitude_db.shape[1] == len(spectrogram.x)
    assert (spectrogram.x[-1] - spectrogram.x[0]) <= history + 11.0
    assert np.all(np.diff(x) > 0)


def test_an_unbounded_live_buffer_keeps_everything(worker):
    """Recording passes no bound: the take is the thing being kept."""
    hub = PlotDataHub(AudioFeatures())
    hub.begin_recording()
    snapshots = run_passes(worker, seconds=30.0)
    hub.append_snapshots(snapshots)

    x, _ = hub.get_xy("pitch")
    assert len(x) == len(snapshots)


def test_discarding_the_live_data_leaves_the_analysis_alone(worker):
    """What monitoring shows is never written into the session's own record."""
    features = AudioFeatures(length_seconds=12.5)
    features.pitch = SignalTimeSeries(x=np.arange(5, dtype=float),
                                      y=np.arange(5, dtype=float) + 100)
    hub = PlotDataHub(features)

    hub.begin_recording(history_seconds=5.0)
    hub.append_snapshots(run_passes(worker, seconds=3.0))
    hub.discard_live()

    assert not hub.is_recording
    assert hub.features is features
    assert np.array_equal(features.pitch.y, np.arange(5, dtype=float) + 100)
    assert hub.spectrogram() is None
