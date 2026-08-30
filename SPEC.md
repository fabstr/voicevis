# VoiceVis — Project specification

What this project is, where each part of it lives, and what has to be true
before a change is finished.

This is the map. It does not restate the detail held elsewhere — it says which
document holds it. The three things it defines itself are the
[document set](#1-the-document-set), the [invariants](#6-invariants), and the
[definition of done](#7-definition-of-done-for-a-feature).

> Not to be confused with [`VoiceVis.spec`](VoiceVis.spec), which is
> PyInstaller's build recipe.

---

## 0. Purpose and scope

VoiceVis is a desktop application for **seeing the gendered aspects of a
voice**: it records or loads speech, extracts per-frame acoustic features with
openSMILE and some signal processing of its own, and draws them against
configurable target ranges so that a speaker can work towards them.

It is a practice and teaching tool for voice training. In scope:

- Recording, playing back and destructively editing one recording at a time,
  and a non-destructive gain over any part of it.
- Batch and near-real-time extraction of pitch, formants, harmonic ratios,
  loudness, jitter, shimmer, derived ratios and a spectrogram.
- A freely configurable grid of plots over those quantities, with target bands,
  annotations, frequency markers and a shared time axis.
- Target profiles that can be built, saved, imported and shared.

Explicitly **not** in scope:

- Clinical assessment or diagnosis. The numbers are for practice, not for
  medical decisions.
- Speech recognition, transcription or content analysis.
- Multi-track editing, mixing, or anything resembling a DAW.
- A server, an account, or any network traffic. VoiceVis runs offline against
  local files.

The user-facing description lives in [`resources/docs/README.md`](resources/docs/README.md);
the method behind the numbers in [`20_methology.md`](resources/docs/20_methology.md).

---

## 1. The document set

Each question has exactly one authoritative answer. Write the answer where it
belongs, and link to it from anywhere else that needs it.

| Question | Authoritative document | Audience |
|---|---|---|
| What is this, and why? | [`README.md`](README.md), [`resources/docs/README.md`](resources/docs/README.md) | everyone |
| How do I use it? | [`resources/docs/10_usage.md`](resources/docs/10_usage.md) | users, in-app via `F1` |
| What does the application do, precisely? | [`REQUIREMENTS.md`](REQUIREMENTS.md) (EARS) | developers, reviewers |
| What is each measured quantity? | [`resources/docs/15_analyzed_features.md`](resources/docs/15_analyzed_features.md) | users |
| Why these measures? | [`resources/docs/20_methology.md`](resources/docs/20_methology.md) | users |
| Where does a claim come from? | [`resources/docs/70_references.md`](resources/docs/70_references.md) | everyone |
| What is it built from? | `resources/docs/99_dependencies.md` + `resources/SBOM.json` | *generated at build time* |
| How is the code arranged? | **this file**, plus the per-module documents below | developers |
| How does *this module* work? | the `.md` next to the module | developers |

**Developer documentation lives next to the code it describes**, not in a
central `docs/` tree, so that a change and its explanation move together:

- [`src/SeriesRegistry.md`](src/SeriesRegistry.md) — what can be plotted, and how to add something new
- [`src/ui/MainWindow.md`](src/ui/MainWindow.md) — one session per window, and how a window shuts down
- [`src/ui/ResponsiveToolBar.md`](src/ui/ResponsiveToolBar.md) — controls that fold into dropdowns when the window is narrow
- [`src/ui/AudioEditing.md`](src/ui/AudioEditing.md) — selecting a stretch, silencing it, moving it
- [`src/ui/plot/README.md`](src/ui/plot/README.md) — how a plot is configured, drawn, kept in sync and persisted
  - [`src/ui/plot/renderers/README.md`](src/ui/plot/renderers/README.md) — the drawing strategies
  - [`src/ui/plot/layers/README.md`](src/ui/plot/layers/README.md) — spectrogram background, target bands, radar frame, frequency markers

`resources/docs/` is **shipped**: it is what `F1` opens, so it is written for
users and stays free of implementation detail. The numeric filename prefixes
(`10_`, `15_`, `20_`, `70_`, `99_`) are the table-of-contents order —
[`HelpWindow`](src/ui/HelpWindow.py) sorts the directory by name.

---

## 2. Runtime shape

- **One session per window.** `MainWindow` → one `AnalysisWidget` → its own
  audio buffer, analysis, plot grid and target. Sessions share nothing except
  frequency markers, series colours and the saved layout. See
  [MainWindow.md](src/ui/MainWindow.md).
- **Three threads that matter.** The GUI thread; `AnalysisWorker` (batch
  re-analysis, cancellable); `RealTimeAnalysisWorker` and `PlaybackWorker`
  during recording and playback. Workers never touch widgets — they emit
  signals.
- **One owner of the data and the clock.** `PlotDataHub`. Nothing else keeps a
  reference to a `SignalTimeSeries`, because a re-analysis replaces those
  objects wholesale.
- **Two redraw paths, deliberately separate.** A 33 ms timer moves the playhead
  every frame; a full redraw happens only when the hub reports dirty. See
  [the plot layer](src/ui/plot/README.md#data-flow).
- **Re-analysis is chunked.** 10 s chunks with 1 s of context per side, keyed by
  content digest, so an edit re-analyses only what changed
  ([`ChunkedAnalysis.py`](src/signal_processing/ChunkedAnalysis.py)).

---

## 3. Code map

Entry point: [`src/main.py`](src/main.py) — logging to the OS app-data
directory, a global exception hook that survives a pre-`QApplication` crash,
per-platform icon setup, then `MainWindow`.

### `src/` — top level

| File | Responsibility |
|---|---|
| [`main.py`](src/main.py) | Entry point, logging, crash dialogue, application icon |
| [`SeriesRegistry.py`](src/SeriesRegistry.py) | The catalogue of plottable series, the colour palette, the layout presets. **Qt-free** — see [its document](src/SeriesRegistry.md) |
| [`ResourceManager.py`](src/ResourceManager.py) | The only way to reach anything under `resources/`; resolves both the source tree and a PyInstaller bundle |
| [`mass_analyzer.py`](src/mass_analyzer.py) | Offline batch analysis of a corpus into matplotlib figures and GIFs. No UI |
| [`generate_version.py`](src/generate_version.py) | Writes the generated `_version.py` from the git tag or hash at build time |
| [`utils.py`](src/utils.py) | Small helpers (PCM to a temporary wav) |

### `src/signal_processing/` — the numbers

Qt appears here only as `QByteArray` in the edit helpers. Nothing in this
package knows about widgets.

| File | Responsibility |
|---|---|
| [`AudioFeatureExtractor.py`](src/signal_processing/AudioFeatureExtractor.py) | openSMILE eGeMAPSv02 low-level descriptors plus the derived features, the validity mask, the outlier filter and the STFT spectrogram |
| [`AudioFeatures.py`](src/signal_processing/AudioFeatures.py) | `SignalTimeSeries`, `SpectrogramData`, `AudioFeatures`, `FeatureSnapshot` — the shapes everything downstream reads |
| [`ChunkedAnalysis.py`](src/signal_processing/ChunkedAnalysis.py) | The chunk cache: what gets re-analysed after an edit, and how the pieces are stitched back together |
| [`AudioEdit.py`](src/signal_processing/AudioEdit.py) | `silence`, `cut` and `move` over the raw PCM buffer |
| [`GainMap.py`](src/signal_processing/GainMap.py) | The gains in force over the recording, applied to a copy on its way to the analysis, to playback and to an export |
| [`TargetConfig.py`](src/signal_processing/TargetConfig.py) | A target profile: named bounds, enable flags, JSON round-trip |
| [`Cepstrum.py`](src/signal_processing/Cepstrum.py) | CPPS: how far the cepstral peak at the pitch period stands above the cepstral baseline, per frame |
| [`Weight.py`](src/signal_processing/Weight.py) | Weight: the length of the vector (50 &minus; H1-A3, Loudness), per frame |
| [`genderer.py`](src/signal_processing/genderer.py) | Probability of a frame belonging to a target distribution |

### `src/workers/` — the threads

| File | Responsibility |
|---|---|
| [`AnalysisWorker.py`](src/workers/AnalysisWorker.py) | Batch analysis off the GUI thread, cancellable, through the chunk cache |
| [`RealTimeAnalysisWorker.py`](src/workers/RealTimeAnalysisWorker.py) | Live feature snapshots while recording |
| [`PlaybackWorker.py`](src/workers/PlaybackWorker.py) | miniaudio playback and the playhead clock |

### `src/ui/` — the application

| File | Responsibility |
|---|---|
| [`MainWindow.py`](src/ui/MainWindow.py) | The window: menus, sessions, shutdown. [Document](src/ui/MainWindow.md) |
| [`AnalysisWidget.py`](src/ui/AnalysisWidget.py) | The session: transport, audio buffer, plot grid, files, targets, undo. The largest file in the project |
| [`ResponsiveToolBar.py`](src/ui/ResponsiveToolBar.py) | Grouped controls that fold into dropdowns. [Document](src/ui/ResponsiveToolBar.md) |
| [`AudioHistory.py`](src/ui/AudioHistory.py) | Undo and redo of record, clear, silence, cut and move. [Document](src/ui/AudioEditing.md) |
| [`AnnotationMarker.py`](src/ui/AnnotationMarker.py) | A star marker and its text |
| [`TargetConfigDialog.py`](src/ui/TargetConfigDialog.py) | Set Targets… |
| [`SeriesColourDialog.py`](src/ui/SeriesColourDialog.py) | View > Series colours… |
| [`SampleTextWindow.py`](src/ui/SampleTextWindow.py) | The reading passages |
| [`HelpWindow.py`](src/ui/HelpWindow.py) | The in-app Markdown browser over `resources/docs/` |

### `src/ui/plot/` — the plot layer

A plot is a *choice of series*, not a named kind. Everything else is derived
from that choice. The structure, the rules a configuration must satisfy, the
data flow, the mouse tools and the layout migration are documented in
[`src/ui/plot/README.md`](src/ui/plot/README.md), which also carries the
file-by-file map for this package, for
[`renderers/`](src/ui/plot/renderers/README.md) and for
[`layers/`](src/ui/plot/layers/README.md). It is not repeated here.

### `tests/` and `tools/`

| Path | |
|---|---|
| [`tests/test_chunked_analysis.py`](tests/test_chunked_analysis.py) | What the chunk cache promises: correct stitching, and no wasted work. The extractor is stubbed |
| [`tests/test_gain_map.py`](tests/test_gain_map.py) | What a gain promises: it lands on the range asked for, and follows the audio through a cut or a move |
| [`tests/test_radar.py`](tests/test_radar.py) | What a radar plot promises: where its spokes point, where a value lands on one, and the configuration rules that keep it renderable |
| [`tools/generate_doc_screenshots.py`](tools/generate_doc_screenshots.py) | Drives a headless VoiceVis through the walkthroughs and grabs the screenshots the usage docs embed |

---

## 4. Resource map

Everything under `resources/` is read through
[`ResourceManager`](src/ResourceManager.py) and copied next to the executable at
build time. **Never open a resource by a path relative to `__file__`** — that
works from the source tree and fails in a bundle.

| Path | What it is | Read by |
|---|---|---|
| `resources/docs/*.md` | The shipped user documentation, ordered by filename prefix | `HelpWindow` (`F1`) |
| `resources/docs/img/{workflow,features}/` | Screenshots, regenerated by `tools/generate_doc_screenshots.py` | the docs above |
| [`resources/layouts/`](resources/layouts) | The `simple`, `medium` and `advanced` built-in plot layouts | `AnalysisWidget`, `LayoutSerializer` |
| [`resources/targets/`](resources/targets) | The `female` and `male` target presets | the Targets menu, `TargetConfig.from_json` |
| [`resources/sample_texts/`](resources/sample_texts) | Reading passages in Markdown; users may add their own | `SampleTextWindow` |
| `resources/smile_configs/` | The openSMILE configuration tree. VoiceVis uses `egemaps/v02/eGeMAPSv02.conf`, customised to compute more harmonics | `AudioFeatureExtractor` |
| `resources/icon.ico` | The application icon | `main.set_application_icon`, `VoiceVis.spec` |
| `resources/docs/99_dependencies.md`, `resources/SBOM.json` | **Generated** by `build.py`; both are git-ignored | shipped only |

---

## 5. Building, running, testing

Run from source:

```bash
.venv/Scripts/python src/main.py
```

Run the tests (`pyproject.toml` puts `src` on the path):

```bash
.venv/Scripts/python -m pytest
```

Check the series registry against the analysis pipeline:

```bash
.venv/Scripts/python src/SeriesRegistry.py
```

Regenerate the documentation screenshots (headless, isolated `QSettings`):

```bash
.venv/Scripts/python tools/generate_doc_screenshots.py
```

Build the distributable:

```bash
.venv/Scripts/python build.py
```

[`build.py`](build.py) generates `src/_version.py` from the git tag or hash,
writes the dependency Markdown and the CycloneDX SBOM, runs PyInstaller against
[`VoiceVis.spec`](VoiceVis.spec), and deletes the generated files afterwards.
The version string carries `-DIRTY` when the working tree is not clean.
CI ([`.github/workflows/python-app.yml`](.github/workflows/python-app.yml))
lints with flake8 and builds on Windows for every push and pull request to
`main`; **the pytest step is currently commented out.**

Dependencies are pinned in [`requirements.txt`](requirements.txt) (runtime) and
[`requirements-dev.txt`](requirements-dev.txt): Python 3.14, PyQt6, pyqtgraph,
openSMILE, librosa, miniaudio, numpy/scipy/scikit-learn, and matplotlib for the
batch analyser.

---

## 6. Invariants

Rules that are load-bearing. Breaking one of these does not usually fail
loudly — it degrades something silently, which is why they are written down.

1. **`SeriesRegistry.py` imports neither Qt nor pyqtgraph.** `mass_analyzer.py`
   imports it and renders with matplotlib.
2. **Nothing reads `SeriesSpec.colour` directly.** Call
   `SeriesRegistry.colour_of(spec)` — users can recolour any series.
3. **A series used as a colour dimension maps through one of
   `ColourMapping.COLOUR_MAPS`** -- viridis, plasma or turbo, chosen per drawn
   series -- never through the palette. The spectrogram background is not a
   colour dimension and stays viridis.
4. **`PlotPreset.name` values are frozen.** Saved layout files store the name;
   renaming one silently degrades those layouts to the default plot.
5. **The `QSettings` key stays `AudioAnalyzer` / `LiveMultiPlotWidget`.**
   Renaming it discards every existing user's saved layout. Old blobs are read,
   upgraded in memory and written back in the current schema.
6. **`PlotConfig.normalised()` is total** — it never raises and always returns
   something renderable. An unreadable layout falls back to the default plot
   *and logs a warning*.
7. **Resources are reached only through `ResourceManager`.**
8. **Workers never touch widgets.** They emit signals; the GUI thread draws.
9. **`PlotDataHub` is the only holder of analysed data**, and the only live-append
   path.
10. **`resources/docs/` is written for users.** Implementation detail belongs in
    the `.md` next to the code.
11. **Generated files are not committed**: `src/_version.py`,
    `resources/docs/99_dependencies.md`, `resources/SBOM.json`.

---

## 7. Definition of done for a feature

A feature is not finished when it works. It is finished when the four artefacts
below agree with each other.

### 7.1 Write the requirement

Every user-visible behaviour gets a requirement in
[`REQUIREMENTS.md`](REQUIREMENTS.md), in the EARS form that file already uses:

| Pattern | Form |
|---|---|
| Ubiquitous | The system shall … |
| Event-driven | When \<trigger\>, the system shall … |
| State-driven | While \<state\>, the system shall … |
| Optional feature | Where \<feature\>, the system shall … |
| Unwanted behaviour | If \<trigger\>, then the system shall … |

- Add it to the section it belongs to, with the next free number in that
  section's prefix (`SF`, `RP`, `AE`, `AN`, `PG`, `PP`, `MT`, `OV`, `TG`, `SC`,
  `LM`, `AP`, `ST`, `HP`). Start a new section, and a new prefix, only for a
  genuinely new area.
- **Identifiers are never reused and never renumbered.** A requirement that no
  longer holds is struck through and marked *(withdrawn)*, not deleted — it may
  be cited from a commit message or an issue.
- One requirement, one behaviour. If it needs an "and", it is probably two.
- Say what the user observes, not how the code does it.
- If the behaviour is deliberately undefined, add it to
  [Open points](REQUIREMENTS.md#open-points) rather than inventing an answer.

### 7.2 Update the documentation

Work down this list and update everything the change actually touches:

| If the change… | then update |
|---|---|
| is visible to a user at all | [`10_usage.md`](resources/docs/10_usage.md) — the **Full feature list**, and the walkthrough if the change affects one |
| adds or alters a measured quantity | [`15_analyzed_features.md`](resources/docs/15_analyzed_features.md), the feature table in [`README.md`](README.md), and [`20_methology.md`](resources/docs/20_methology.md) if the reasoning changes |
| rests on a paper, dataset or corpus | [`70_references.md`](resources/docs/70_references.md), cited from the text that relies on it |
| changes how a module works | the `.md` next to that module — and its diagrams, not only its prose |
| adds a module, a package or a resource directory | **this file** (§3, §4) and the file map in the owning package's README |
| establishes a rule that must not be broken later | §6 above, with the reason it exists |
| changes the toolbar, a menu, a dialog, the `simple` layout, a target file the docs reference, or the set of series | re-run `tools/generate_doc_screenshots.py` |

Screenshots are generated, never hand-cropped: a hand-made one goes stale at the
next UI change and nothing notices.

### 7.3 Cover it

- A new series: add the field to `AudioFeatures` (and to `FeatureSnapshot` if it
  can be computed live), add a `_signal(...)` line to `SERIES`, give it a
  `target_key` if it has a target range, and run `python src/SeriesRegistry.py`.
  No plot definitions to update — see
  [Adding a series](src/SeriesRegistry.md#adding-a-series).
- Logic that can be tested without a screen — analysis, chunking, editing,
  serialisation, target maths — gets a test under `tests/`.
- A new persisted format is read *and* migrated: `LayoutSerializer` reads every
  layout format the application has ever written, and a new one must not break
  that.

### 7.4 Check the seams

Before calling it done: does it behave in a **second window**? While
**recording**, and during **playback**? On a **transposed** plot, with time on
Y? After an **undo**? In a **built** application, where resources come from the
bundle rather than from the source tree?

---

## 8. Traceability

| Requirements | Primary code | Documents |
|---|---|---|
| SF — sessions and files | `MainWindow.py`, `AnalysisWidget.py` | [MainWindow.md](src/ui/MainWindow.md) |
| RP — recording and playback | `PlaybackWorker.py`, `RealTimeAnalysisWorker.py`, `AnalysisWidget.py` | [plot README, time sync](src/ui/plot/README.md#time-axis-synchronisation) |
| AE — audio editing | `AudioEdit.py`, `GainMap.py`, `AudioHistory.py`, `TimeSelection.py`, `layers/SelectionLayer.py` | [AudioEditing.md](src/ui/AudioEditing.md) |
| AN — analysis | `AudioFeatureExtractor.py`, `Cepstrum.py`, `ChunkedAnalysis.py`, `AnalysisWorker.py` | [15_analyzed_features.md](resources/docs/15_analyzed_features.md), [20_methology.md](resources/docs/20_methology.md) |
| PG, PP, MT — grid, per-plot controls, tools | `ui/plot/` | [plot README](src/ui/plot/README.md) |
| OV — overlays | `FrequencyMarkers.py`, `layers/`, `AnnotationMarker.py` | [layers README](src/ui/plot/layers/README.md) |
| TG — targets | `TargetConfig.py`, `TargetConfigDialog.py`, `resources/targets/` | [10_usage.md](resources/docs/10_usage.md) |
| SC — series colours | `SeriesRegistry.py`, `SeriesColourDialog.py` | [SeriesRegistry.md, the palette](src/SeriesRegistry.md#the-palette) |
| LM — layout management | `LayoutSerializer.py`, `resources/layouts/` | [plot README, persistence](src/ui/plot/README.md#layout-persistence) |
| AP — appearance | `PlotTheme.py`, `MainWindow.py` | — |
| ST — sample texts | `SampleTextWindow.py`, `resources/sample_texts/` | — |
| HP — help | `HelpWindow.py`, `resources/docs/` | — |

---

## 9. Known gaps

Recorded so that they are not mistaken for oversights:

- The behaviours [`REQUIREMENTS.md` lists as open points](REQUIREMENTS.md#open-points):
  error handling for unreadable files and malformed JSON, undo depth, the scope
  of annotations and targets, and the quantitative limits behind "near-real
  time".
- Test coverage is the parts that need no screen: the chunk cache, the gain map,
  the real-time worker, weight, layout serialisation and the radar geometry.
  Everything else is untested, and CI does not run pytest at all.
- `Weight` and `Slopes` are target fields with no plottable series, so they take
  no target band (TG-10).
- `F1_Pitch_rel_amplitude` and its siblings are declared on `AudioFeatures` but
  never assigned — work in progress, deliberately absent from the registry.
- CI builds on Windows only; the Linux and macOS matrix entries are commented
  out.
