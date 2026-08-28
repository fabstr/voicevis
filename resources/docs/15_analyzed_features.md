# Analyzed Features

- [Pitch](#pitch)
- [Loudness](#loudness)
- [Weight](#weight)
- [F1, F2, F3](#f1-f2-f3)
- [Jitter](#jitter)
- [Shimmer](#shimmer)
- [H1-H2, H1-H3, H1-H4](#h1-h2-h1-h3-h1-h4)
- [H1-A3](#h1-a3)
- [F1/Pitch, F2/Pitch, F3/Pitch](#f1pitch-f2pitch-f3pitch)
- [Size](#size)
- [Spectrogram](#spectrogram)

Every recording is broken into audio frames, and each frame is run through
openSMILE's eGeMAPS low-level-descriptor config, plus a little custom signal
processing on top, in `AudioFeatureExtractor`. The results are stored on
`AudioFeatures`, one value per feature per frame -- these are exactly the
series offered in every plot's axis picker. Frames that fail a validity check
(pitch outside 65-500 Hz, no first formant, loudness too low) are set to NaN
and simply don't appear on a plot.

Each screenshot below is a single plot, alone in an otherwise empty grid, so
it shows nothing but that one feature (or that one group of features, where
the table groups several together) against the sample clip
`F_swedish10.mp3`.

### Pitch

F0, the fundamental frequency of voicing, converted from openSMILE's
semitones-from-27.5 Hz representation into Hz. This is the series most people
mean by "pitch" -- how high or low the voice sounds -- and the one most
target ranges are built around.

![A Pitch-only plot: a scatter of points mostly between 150-250 Hz over the clip's duration](img/features/pitch.png)

### Loudness

openSMILE's `Loudness_sma3`, an auditory-model estimate of perceived
loudness per frame rather than a raw amplitude reading.

![A Loudness-only plot: a scatter mostly under 2, with spikes up to about 4 on stressed syllables](img/features/loudness.png)

### Weight

A single calculated "vocal weight" score: the length of the vector whose
components are the frame's distance from a reference H1-A3 of 50 dB and its
loudness, the latter counted four times over --
`sqrt((50 - H1-A3)^2 + (4 x Loudness)^2)`. A voice gets heavier as its H1-A3
falls away from that reference, and heavier again as it gets louder. Where Size describes the vocal tract, Weight describes the voice
source, condensed the same way Size condenses the three formant/pitch ratios.

Both inputs are already cleaned by the validity check (and, for H1-A3, the
outlier filter), so Weight is missing on exactly the frames the rest of the
series are missing on.

![A Weight-only plot: a scatter mostly between 20 and 40, sitting inside its target band, with the contour running inverse to H1-A3](img/features/weight.png)

### F1, F2, F3

The first three formant frequencies (`F1frequency_sma3nz`,
`F2frequency_sma3nz`, `F3frequency_sma3nz`) -- resonances of the vocal tract
that shift with its length and shape, and the basis of the derived F1/F2/F3
ratios and Size below. All three share one Y axis here since they're on
comparable Hz scales.

![An F1, F2, F3 plot: three colour-coded scatters stacked by frequency -- F1 lowest, F3 highest](img/features/formants.png)

### Jitter

`jitterLocal_sma3nz` -- cycle-to-cycle variation in the pitch period. Small
and mostly near zero for a steady voice, with occasional spikes on unstable
or creaky stretches.

![A Jitter-only plot: a scatter clustered near 0, with scattered higher points up to about 0.2](img/features/jitter.png)

### Shimmer

`shimmerLocaldB_sma3nz` -- cycle-to-cycle variation in amplitude, in dB. Like
Jitter, it's a measure of vocal-fold instability, just on the loudness axis
instead of the pitch axis.

![A Shimmer-only plot: a scatter mostly under 2 dB, with occasional spikes up to 6 dB](img/features/shimmer.png)

### H1-H2, H1-H3, H1-H4

The amplitude of the voice's first harmonic relative to its 2nd, 3rd and 4th
(`logRelF0-H1-Hx_sma3nz`, in dB), cleaned of local outliers with a rolling
median/MAD filter before plotting. These describe how the voice source
itself is shaped -- roughly, how breathy versus pressed the phonation is --
independent of the vocal tract. Each gets its own plot below, one per
harmonic comparison.

![An H1-H2-only plot: a dB scatter ranging roughly -15 to 40, with a target band around 0-20](img/features/h1_h2.png)

![An H1-H3-only plot: a similarly-shaped dB scatter over the same range and target band](img/features/h1_h3.png)

![An H1-H4-only plot: a dB scatter following the same overall contour again](img/features/h1_h4.png)

### H1-A3

The amplitude of the first harmonic relative to the third formant's own
amplitude (`logRelF0-H1-A3_sma3nz`, in dB), with the same outlier cleaning as
the H1-Hx series above. Another voice-source-quality measure, this one
comparing the source directly against a resonance rather than another
harmonic.

![An H1-A3-only plot: a dB scatter, mostly between 10 and 30](img/features/h1_a3.png)

### F1/Pitch, F2/Pitch, F3/Pitch

Each formant frequency divided by Pitch for that frame -- a calculated
series, not a raw openSMILE output. Dividing out pitch removes intonation
from the picture, leaving a ratio that tracks vocal-tract shape more
directly than the raw formant frequencies do. All three share one Y axis.

![An F1/Pitch, F2/Pitch, F3/Pitch plot: three colour-coded ratio scatters, F3/Pitch highest and most spread out, F1/Pitch lowest and tightest](img/features/formant_pitch_ratios.png)

### Size

A single calculated "vocal tract size" score: the signed RMS of F1/Pitch,
F2/Pitch and F3/Pitch combined into one number. This is the series the
"simple" layout leads with -- the closest thing this app has to a one-number summary of the formant/pitch
relationship.

![A Size-only plot: a scatter mostly between 7 and 12, with occasional spikes above 20](img/features/size.png)

### Spectrogram

Not a per-frame scalar like the rest, but a full 2-D time/frequency/magnitude
image: an STFT power spectrogram (Blackman-Harris window, 4096-point
segments, 8192-point FFT), converted to dB. Every plot above is really a
scatter of points; this is the one place raw spectral detail -- harmonics,
formant bands, silence -- is visible directly instead of being reduced to a
single curve per frame.

![A Spectrogram-only plot: time on X, frequency on Y up to about 8000 Hz, harmonic bands visible as bright horizontal striping](img/features/spectrogram.png)
