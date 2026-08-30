"""CPPS -- how clearly a voice is voiced, in one number per frame.

Cepstral Peak Prominence, Smoothed. The cepstrum of a frame is the inverse
Fourier transform of its log power spectrum: a spectrum of the spectrum, whose
axis is *quefrency*, measured in seconds. A voice whose harmonics are evenly
spaced and clearly defined puts a sharp peak there at the pitch period -- the
rhamonic -- while a breathy or aperiodic one smears that peak into the cepstral
background. CPPS is how far the peak stands above that background::

    CPPS = the peak, in dB - the least-squares line through the cepstrum, there

Unlike Jitter and Shimmer it needs no F0 estimate and no period marking, so it
keeps working on the creaky and breathy stretches where those two become
unreliable. That is why the literature reports it for running speech, and why
it is the measure that separates breathy phonation from pressed.

Two choices in here are not obvious and are load-bearing.

**The spectrum is cut off at 5 kHz before the cepstrum is taken.** Without that,
the measure is not comparable between recordings: the rhamonic sits on a log
spectrum whose width is the recording's own Nyquist, so the same synthetic
signal measured 17.2 dB at 22.05 kHz and 23.0 dB at 48 kHz. Band-limiting also
fixes the quefrency grid at ``1 / (2 x ANALYSIS_MAX_HZ)`` whatever the input
rate, so the search and regression bins mean the same thing everywhere.

**The temporal smoothing skips silent frames rather than averaging them in.**
This application can silence a selection, and a digitally silent frame has a
flat spectrum -- a cepstrum of one spike at quefrency zero and numerical dust
elsewhere. Averaged in, it would drag the frames either side of the edit down
with it.

Absolute CPPS values are implementation-dependent: window length, band limit
and smoothing widths each move them by a decibel or more, so the numbers here
are comparable with each other and not with another tool's. Nothing in this
module derives from Praat, though the band limit, the pre-emphasis and the
regression range are chosen to match what its PowerCepstrogram does, so the
values land in the range the literature describes.

References: Noll (1967) for the cepstrum, Hillenbrand et al. (1994) for CPP,
Hillenbrand & Houde (1996) for the smoothing, Murton et al. (2020) for why the
absolute value is implementation-dependent. See
``resources/docs/70_references.md``.
"""

from dataclasses import dataclass

import numpy as np
import scipy.fft
from scipy.ndimage import uniform_filter1d

from signal_processing.AudioFeatures import SignalTimeSeries

#: The pitch range the rhamonic is looked for in. The same bounds the validity
#: check in :meth:`AudioFeatureExtractor.extractFeatures` uses -- a frame
#: outside them is discarded there anyway, so searching wider would only find
#: noise. Repeated rather than imported because the two must not drift apart
#: and a test pins them together.
PITCH_FLOOR_HZ = 65.0
PITCH_CEILING_HZ = 500.0

#: How many periods of the lowest reportable pitch one analysis frame holds.
#: A Hann window's main lobe is four bins wide, so telling harmonics spaced F0
#: apart from each other needs a window of at least four periods of F0; three
#: would smear them together at the pitch floor and flatten the rhamonic.
PERIODS_PER_FRAME = 4

#: 61.5 ms. Given in seconds rather than samples so a frame means the same
#: stretch of voice whatever the recording's sample rate is.
FRAME_SECONDS = PERIODS_PER_FRAME / PITCH_FLOOR_HZ

#: Where the spectrum is cut off before the cepstrum is taken. See the module
#: docstring: this is what makes the measure comparable between recordings at
#: all, not an optimisation. Above 5 kHz there is no harmonic structure left to
#: find in a voice, only fricative noise.
ANALYSIS_MAX_HZ = 5000.0

#: First-order pre-emphasis. Flattening the source's spectral tilt leaves the
#: regression line describing the cepstral noise floor rather than the tilt,
#: which is what the peak is supposed to be measured against.
PRE_EMPHASIS_FROM_HZ = 50.0

#: The quefrency range the baseline is fitted over. The low end excludes bin 0
#: (the frame's overall level) and the few bins after it that describe the
#: vocal tract rather than voicing; the high end reaches past the search band,
#: so the peak is measured against a line fitted to its whole neighbourhood.
REGRESSION_MIN_QUEFRENCY_SECONDS = 0.001
REGRESSION_MAX_QUEFRENCY_SECONDS = 0.025

#: The smoothing that makes CPP into CPPS: the cepstra are averaged over this
#: many frames -- 70 ms, at the 10 ms frame grid -- and this much quefrency
#: before the peak is picked. Unsmoothed CPP jumps around far too much frame to
#: frame to read on a plot.
TIME_SMOOTHING_FRAMES = 7
QUEFRENCY_SMOOTHING_SECONDS = 0.0005

#: One frame every 10 ms, matching openSMILE's frame grid so the values line up
#: with every other series and no interpolation is needed downstream.
HOP_SECONDS = 0.010

#: How far the power spectrum is floored below its own peak before the log. A
#: *relative* floor, so scaling a frame only shifts its log spectrum by a
#: constant -- which lands entirely in cepstral bin 0 and leaves CPPS exactly
#: unchanged. An absolute floor would make the measure depend on the gain.
SPECTRUM_FLOOR = 1e-10

#: A frame quieter than this is not measured, and is left out of its
#: neighbours' smoothing rather than averaged into them.
SILENCE_RMS = 1e-7

#: How many frames are transformed at once. The chunked analysis hands over ten
#: seconds at a time, but ``analyzeFile`` and ``mass_analyzer`` hand over whole
#: recordings, and one frames-by-FFT matrix over all of those at once would run
#: to gigabytes. Blocking bounds it at a few megabytes; overlapping the blocks
#: by half the smoothing window keeps the answer identical to one pass.
BLOCK_FRAMES = 256

#: Floor under the squared cepstrum, so digital silence cannot produce -inf.
_EPSILON = 1e-20

_DB = 10.0 / np.log(10.0)


@dataclass(frozen=True)
class _Grid:
    """Everything the transform sizes depend on, derived once per call."""

    frame_length: int
    nfft: int
    #: Spectrum bins kept, i.e. those at or below :data:`ANALYSIS_MAX_HZ`.
    bins: int
    #: Length of the inverse transform, and how many of its bins are usable.
    cepstrum_length: int
    keep: int
    #: Quefrency bin *k* is ``k / quefrency_rate`` seconds.
    quefrency_rate: float
    peak: slice
    fit: slice
    quefrency_smoothing: int


def calculate_cpps(t, pcm_data, sampling_rate) -> SignalTimeSeries:
    """The per-frame CPPS of ``pcm_data``, over the timepoints ``t``.

    Exactly one value per timepoint, so the caller can mask the result with the
    same validity mask it applies to every other series.

    :param t: The frame timepoints, in seconds, one every :data:`HOP_SECONDS`.
        Used unchanged as the series' x axis.
    :param pcm_data: Mono samples, as the extractor received them.
    :param sampling_rate: Their sample rate, in Hz.
    """
    times = np.asarray(t, dtype=float)
    values, _ = cepstral_peak_prominence(times, pcm_data, sampling_rate)
    return SignalTimeSeries(x=times, y=values)


def cepstral_peak_prominence(t, pcm_data, sampling_rate):
    """CPPS and the quefrency each peak was found at, per frame.

    The quefrency is not plotted; it is returned because it is the thing that
    says the cepstrum is a cepstrum -- one over it is the frame's pitch period
    -- and it is the one quantity here that is stable across sample rates.
    """
    times = np.asarray(t, dtype=float)
    empty = np.empty(0)
    if times.size == 0 or pcm_data is None:
        return empty, empty

    samples = np.asarray(pcm_data, dtype=np.float32).ravel()
    missing = np.full(times.size, np.nan)
    if samples.size == 0 or sampling_rate <= 0:
        return missing, missing.copy()

    grid = _grid(int(sampling_rate))
    if grid is None:
        return missing, missing.copy()

    # A frame is centred on its timepoint: the value describes the voice around
    # that moment rather than only after it.
    starts = np.rint(times * sampling_rate).astype(np.int64) - grid.frame_length // 2

    window = np.hanning(grid.frame_length).astype(np.float32)
    decay = np.float32(np.exp(-2.0 * np.pi * PRE_EMPHASIS_FROM_HZ / sampling_rate))
    quefrency = np.arange(grid.keep) / grid.quefrency_rate

    prominence = np.empty(times.size, dtype=float)
    peak_quefrency = np.empty(times.size, dtype=float)

    halo = TIME_SMOOTHING_FRAMES // 2
    for low in range(0, times.size, BLOCK_FRAMES):
        high = min(times.size, low + BLOCK_FRAMES)
        # Analysed with a halo either side so that the temporal smoothing sees
        # the same neighbours it would in one pass; only the interior is kept.
        first, last = max(0, low - halo), min(times.size, high + halo)

        frames = _frames(samples, starts[first:last], grid.frame_length, decay)
        block, block_quefrency = _prominence_of(frames * window, grid, quefrency)

        inside = slice(low - first, high - first)
        prominence[low:high] = block[inside]
        peak_quefrency[low:high] = block_quefrency[inside]

    return prominence, peak_quefrency


def _grid(sampling_rate):
    """The transform sizes for one sample rate, or None if it is unusable."""
    frame_length = int(round(FRAME_SECONDS * sampling_rate))
    frame_length += frame_length & 1            # even, so the centre is exact
    if frame_length < 8:
        return None

    nfft = 1 << (frame_length - 1).bit_length()
    # The half-spectrum up to ANALYSIS_MAX_HZ, or the whole of it when the
    # recording's own Nyquist is lower. Inverse-transforming just these bins is
    # a resample: the quefrency grid no longer depends on the input rate.
    bins = min(int(round(ANALYSIS_MAX_HZ * nfft / sampling_rate)) + 1, nfft // 2 + 1)
    cepstrum_length = 2 * (bins - 1)
    keep = cepstrum_length // 2
    quefrency_rate = cepstrum_length * float(sampling_rate) / nfft

    peak = slice(int(np.ceil(quefrency_rate / PITCH_CEILING_HZ)),
                 min(int(quefrency_rate / PITCH_FLOOR_HZ) + 1, keep))
    fit = slice(int(round(REGRESSION_MIN_QUEFRENCY_SECONDS * quefrency_rate)),
                min(int(round(REGRESSION_MAX_QUEFRENCY_SECONDS * quefrency_rate)), keep))
    if peak.stop - peak.start < 3 or fit.stop - fit.start < 3:
        return None

    smoothing = int(round(QUEFRENCY_SMOOTHING_SECONDS * quefrency_rate))
    return _Grid(frame_length=frame_length, nfft=nfft, bins=bins,
                 cepstrum_length=cepstrum_length, keep=keep,
                 quefrency_rate=quefrency_rate, peak=peak, fit=fit,
                 quefrency_smoothing=max(1, smoothing | 1))


def _frames(samples, starts, frame_length, decay):
    """One pre-emphasised frame per start, zero-padded past either end.

    Only the stretch this block needs is copied. Padding the whole recording
    instead would mean a second copy of it, which for a long file handed
    straight to ``analyzeFile`` is a hundred megabytes for nothing.
    """
    first = int(starts[0]) - 1                  # one extra for the pre-emphasis
    last = int(starts[-1]) + frame_length
    segment = samples[max(0, first):max(0, min(samples.size, last))]

    pad = (max(0, -first), max(0, last - samples.size))
    if pad[0] or pad[1]:
        segment = np.pad(segment, pad)

    emphasised = segment[1:] - decay * segment[:-1]
    view = np.lib.stride_tricks.sliding_window_view(emphasised, frame_length)
    return view[starts - (first + 1)]


def _prominence_of(frames, grid, quefrency):
    """CPPS and its quefrency for every frame of one block."""
    spectrum = scipy.fft.rfft(frames, n=grid.nfft, axis=1)[:, :grid.bins]
    power = spectrum.real ** 2 + spectrum.imag ** 2
    floor = np.maximum(power.max(axis=1, keepdims=True) * SPECTRUM_FLOOR, _EPSILON)
    log_power = (_DB * np.log(np.maximum(power, floor))).astype(np.float32)

    cepstrum = scipy.fft.irfft(log_power, n=grid.cepstrum_length, axis=1)[:, :grid.keep]
    cepstrum_db = _DB * np.log(cepstrum * cepstrum + _EPSILON)

    smoothed = _smooth(cepstrum_db, frames, grid.quefrency_smoothing)
    slope, intercept = _baseline(smoothed[:, grid.fit], quefrency[grid.fit])
    peak_db, peak_quefrency = _peak(smoothed[:, grid.peak], grid)

    return peak_db - (intercept + slope * peak_quefrency), peak_quefrency


def _smooth(cepstrum_db, frames, quefrency_bins):
    """Average the cepstra over time and quefrency, skipping silent frames.

    ``uniform_filter1d`` is a mean, so dividing a mean over the frames with
    silence zeroed out by the mean of a present/absent indicator gives the mean
    over the frames that were actually there. A run of silence long enough to
    fill the window leaves NaN, which is the honest answer.
    """
    loud = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) >= SILENCE_RMS
    present = loud.astype(np.float32)

    total = uniform_filter1d(np.where(loud[:, None], cepstrum_db, np.float32(0.0)),
                             TIME_SMOOTHING_FRAMES, axis=0, mode="nearest")
    count = uniform_filter1d(present, TIME_SMOOTHING_FRAMES, mode="nearest")

    with np.errstate(invalid="ignore", divide="ignore"):
        smoothed = np.where(count[:, None] > 0, total / count[:, None], np.nan)
    return uniform_filter1d(smoothed, quefrency_bins, axis=1, mode="nearest")


def _baseline(cepstrum_db, quefrency):
    """The least-squares line through each frame's cepstrum.

    Solved in closed form over every frame at once: ``np.polyfit`` would mean a
    Python loop over a hundred frames for every second of audio.
    """
    centred = quefrency - quefrency.mean()
    mean_db = cepstrum_db.mean(axis=1)

    slope = ((centred * (cepstrum_db - mean_db[:, None])).sum(axis=1)
             / (centred ** 2).sum())
    return slope, mean_db - slope * quefrency.mean()


def _peak(band, grid):
    """The tallest point of the search band, and the quefrency it sits at.

    The true peak rarely falls on a bin, so a parabola through the winning bin
    and its neighbours locates it between them -- without that, the reported
    pitch period is quantised to the quefrency grid and CPPS is systematically
    a little low.
    """
    searchable = np.where(np.isnan(band), -np.inf, band)
    index = searchable.argmax(axis=1)
    rows = np.arange(band.shape[0])

    here = searchable[rows, index]
    before = searchable[rows, np.maximum(index - 1, 0)]
    after = searchable[rows, np.minimum(index + 1, band.shape[1] - 1)]

    with np.errstate(invalid="ignore", divide="ignore"):
        curvature = before - 2.0 * here + after
        offset = 0.5 * (before - after) / np.where(curvature == 0.0, 1.0, curvature)
        # A winner on the edge of the band has no parabola to sit on, and a
        # block of silence has no winner at all.
        flat = ~np.isfinite(curvature) | (curvature == 0.0)
        offset = np.where((index == 0) | (index == band.shape[1] - 1) | flat,
                          0.0, np.clip(offset, -0.5, 0.5))
        peak_db = here - 0.25 * (before - after) * offset
    quefrency = (grid.peak.start + index + offset) / grid.quefrency_rate
    return peak_db, np.where(np.isfinite(here), quefrency, np.nan)
