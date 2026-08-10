# VoiceVis

This is a python tool based mainly on Opensmile and Pyqtgraph to visualise and understand gender aspects of voices.

Documentation (will be written) is in the [docs folder](resources/docs/README.md).

## Developer documentation

Architecture notes live next to the code they describe:

- [Windows and sessions](src/ui/MainWindow.md) — one session per window, and how a window shuts down
- [The plot layer](src/ui/plot/README.md) — how a plot is configured, drawn, kept in sync and persisted
  - [Renderers](src/ui/plot/renderers/README.md) — the drawing strategies
  - [Layers](src/ui/plot/layers/README.md) — the spectrogram background and target bands
- [The series registry](src/SeriesRegistry.md) — what can be plotted, and how to add something new