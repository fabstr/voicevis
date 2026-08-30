# Methology

Most of what this application measures it does not compute: openSMILE's
eGeMAPSv02 low-level-descriptor config produces the pitch, the formants, the
loudness, the jitter, the shimmer and the harmonic differences, and
`AudioFeatureExtractor` reads them off, cleans them and combines them.
[`15_analyzed_features.md`](15_analyzed_features.md) says what each one is.

This file is for the measures whose *method* is ours, where the choice of
constants is a judgement someone might later want to revisit or disagree with.

## CPPS

Smoothed Cepstral Peak Prominence, in `signal_processing/Cepstrum.py`. The
chain, per frame:

```
frame  ->  pre-emphasis  ->  Hann window  ->  FFT  ->  |.|^2  ->  10 log10
       ->  cut off at 5 kHz  ->  inverse FFT  ->  cepstrum
       ->  average over time and quefrency
       ->  peak in the search band  -  regression line, at the peak
```

Each of the numbers involved is a named constant in that module, commented with
its reason. The ones worth arguing about:

**Four periods of the pitch floor, not three (61.5 ms).** A Hann window's main
lobe is four bins wide, so telling harmonics spaced F0 apart from each other
needs a window holding at least four periods of F0. Three -- the more common
rule -- smears adjacent harmonics together at the bottom of the pitch range the
validity mask admits, and a smeared spectrum has a flatter rhamonic.

**The spectrum is cut off at 5 kHz before the cepstrum is taken.** This is a
correctness requirement, not an optimisation. The cepstral peak sits on a
background whose extent is set by the width of the log spectrum it was
transformed from -- so without a band limit, the same signal measures
differently depending only on the recording's sample rate. Measured on a
synthetic harmonic signal: 17.2 dB at 22.05 kHz against 23.0 dB at 48 kHz.
Cutting the spectrum at a fixed frequency also fixes the quefrency grid at
`1 / (2 x 5000)` seconds whatever the input rate, so the search band and the
regression range mean the same thing in every recording. Above 5 kHz a voice
has no harmonic structure left to find, only fricative noise.

**The search band is 65-500 Hz** -- the same bounds
`AudioFeatureExtractor.extractFeatures` uses for its validity mask. A frame
whose pitch falls outside them is discarded anyway, so a rhamonic found outside
them could only be noise. A test pins the two together, because they are two
copies of one decision.

**The spectrum is floored relative to its own peak, not absolutely.** A
prominence is the difference between two decibel values on one axis, so scaling
a frame shifts its whole log spectrum by a constant -- which lands entirely in
cepstral bin 0 and leaves CPPS unchanged. That invariance is only true of a
relative floor; an absolute one would make the measure depend on the recording
gain, which for a tool people use with whatever microphone they have would be a
serious flaw.

**Silent frames are skipped by the smoothing, not averaged into it.** This
application can silence a selection, and a digitally silent frame has a flat
spectrum -- a cepstrum of one spike at quefrency zero and numerical dust
elsewhere. Averaged in, it would pull down the frames on either side of the
edit, so the plot would be showing the edit rather than the voice.

**Seven frames of temporal smoothing (70 ms).** This is the S in CPPS, and it
is also what makes the series readable: unsmoothed CPP jumps around far too
much frame to frame to plot. It is bounded by something real -- a frame's value
must depend only on audio close to it, or the chunk cache would produce
different answers at chunk boundaries and the live analysis would disagree with
the batch one. The total support is 60.8 ms either side of a frame, against the
1 s of context `ChunkedAnalysis` gives each chunk and the 0.5 s window the live
worker holds. `tests/test_cepstrum.py` asserts that margin, so widening the
window or the smoothing fails loudly rather than quietly.

**Nothing here derives from Praat**, directly or indirectly. The band limit,
the pre-emphasis and the regression range are chosen to match what its
`PowerCepstrogram` does, so the values land in the range the literature
describes -- but the implementation is numpy and scipy, and Praat is a design
reference, not a dependency.

The consequence, which the feature documentation repeats because users will
compare notes: **absolute CPPS values are implementation-dependent**. Window
length, band limit and smoothing widths each move them by a decibel or more.
The numbers here are comparable with each other and not with another tool's
[[10]](70_references.md).
