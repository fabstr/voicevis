# VoiceVis

This is a python tool based mainly on Opensmile and Pyqtgraph to visualise and understand gender aspects of voices.

Documentation (will be written) is in the [docs folder](resources/docs/README.md).

## Analyzed Features

Extracted per audio frame (via openSMILE eGeMAPS LLD config, plus custom signal processing) in `src/signal_processing/AudioFeatureExtractor.py`, stored on `AudioFeatures` (`src/signal_processing/AudioFeatures.py`). Frames failing a validity check (pitch 65–500 Hz, F1 > 0, loudness > -0.8) are set to NaN and dropped from plots.

| Feature | What it is | Source |
|---|---|---|
| **Pitch** (Hz) | F0, converted from openSMILE's semitones-from-27.5 Hz representation | Opensmile |
| **Loudness** | openSMILE's `Loudness_sma3` | Opensmile |
| **Weight** | Length of the vector (50 &minus; H1-A3, 4 &times; Loudness) &mdash; a single "vocal weight" score, rising as H1-A3 falls | Calculated |
| **F1, F2, F3** (Hz) | First three formant frequencies (`F1/F2/F3frequency_sma3nz`) | Opensmile |
| **Jitter** | `jitterLocal_sma3nz` — cycle-to-cycle pitch-period variation | Opensmile |
| **Shimmer** (dB) | `shimmerLocaldB_sma3nz` — cycle-to-cycle amplitude variation | Opensmile |
| **H1-H2, H1-H3, H1-H4** (dB) | Amplitude of the 1st harmonic relative to the 2nd/3rd/4th harmonic (`logRelF0-H1-Hx_sma3nz`), cleaned of local outliers (rolling-median/MAD filter) | Opensmile |
| **H1-A3** (dB) | Amplitude of the 1st harmonic relative to the 3rd formant's amplitude (`logRelF0-H1-A3_sma3nz`), same outlier cleaning | Opensmile |
| **F1/Pitch, F2/Pitch, F3/Pitch** | Each formant frequency divided by pitch | Calculated |
| **Size** | Signed RMS of (F1/Pitch, F2/Pitch, F3/Pitch) — a single combined "vocal tract size" score | Calculated |
| **Spectrogram** | STFT power spectrogram (Blackman-Harris window, 4096-pt segments, 8192-pt FFT), converted to dB — full 2-D time/frequency/magnitude data | Calculated|


## Developer documentation

Start with the [project specification](SPEC.md) — the code and resource map, the
invariants, and what has to be true before a change is finished. What the
application does, precisely, is in [REQUIREMENTS.md](REQUIREMENTS.md).

Architecture notes live next to the code they describe:

- [The main toolbar](src/ui/ResponsiveToolBar.md) — grouped controls that fold into dropdowns when the window is narrow
- [Editing the audio](src/ui/AudioEditing.md) — selecting a stretch of the recording, silencing it, moving it, changing its level
- [Windows and sessions](src/ui/MainWindow.md) — one session per window, and how a window shuts down
- [The plot layer](src/ui/plot/README.md) — how a plot is configured, drawn, kept in sync and persisted
  - [Renderers](src/ui/plot/renderers/README.md) — the drawing strategies
  - [Layers](src/ui/plot/layers/README.md) — the spectrogram background, the target bands and the radar frame
- [The series registry](src/SeriesRegistry.md) — what can be plotted, and how to add something new