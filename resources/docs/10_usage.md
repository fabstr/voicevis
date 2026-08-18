# Usage of VoiceVis

## General workflow
- Record/open -> Playback, analyse
- Working with annotations
- Sample texts
- Save

## Working with targets
- Defining targets
- Modifying default targets

## Audio editing
- Move
- Cut 
- Replace with silence
- Save

## General
- Open/import audio
- recording (& saving)
- playback
- annotations
- preset targets

## View/hide
- view/hide plots and data
- zoom in plots
- reset zoom
- reset plots
- one session per window; File > New opens another window

## Analysis
- probably need target defined
- How to read 
  - loudness
  - pitch
  - size
  - weight
  - fullness
  - formants
  - formant ratios
- working with zoom and point size
- Defining custom targets


## Features

### Sessions & files
- **File > New** opens another independent session window (own audio, analysis, plots, targets)
- **File > Open** an audio file (`.wav`, `.mp3`) or an annotations file (`.json`)
- **Drag-and-drop** a `.wav`/`.mp3`/`.json` file onto the window to load it
- **File > Save Annotations** to a `.json` file (linked to the source audio path, with a fallback path)
- **File > Save Audio As...** exports the in-memory recording to a `.wav` file
- **File > Close** closes the current window/session
- Windows cascade automatically when opened, and the title bar shows the loaded file name

### Recording & playback
- **Record** from the default microphone (`R` key or toolbar/menu), with live waveform capture into memory
- **Stop recording** (`R` again, or Space)
- **Play / Pause** the loaded or recorded audio (Space, or the toolbar play button)
- **Seek**: type a time into the "Time:" box, or click on any time-based plot to jump the playhead there
- **Clear** the entire recording/session (`D` key)
- Recording extends/overwrites a specific position (so you can punch in over prior audio)
- Playhead auto-scrolls: 10 s window while recording, page-forward once past 50% of the view while playing

### Audio editing
- **Select** a time range by dragging on any time-based plot (Select tool)
- Drag the **edges** of a selection to resize it
- Drag the **band itself** to move that audio to a new position (overwrites destination, leaves silence behind)
- **Replace with Silence** — zero out the selected range, keeping timeline length
- **Cut Selection** — remove the selected range and close the gap (shortens recording)
- **Undo / Redo** for record, clear, silence, cut, and move — menu labels show what will be undone/redone
- Leaving Select mode clears the current selection

### Analysis
- Automatic re-analysis after recording, playback edits, undo/redo, or loading a file
- Chunked/cached analysis (only re-analyzes the portions of audio that changed)
- Live, near-real-time analysis while recording
- Computed/plottable quantities: **Pitch, Loudness, Size, Formants (F1, F2, F3), Formant/Pitch ratios (F1/Pitch, F2/Pitch, F3/Pitch), Harmonic differences (H1-H2, H1-H3, H1-H4, H1-A3), Jitter, Shimmer**, plus raw spectrogram magnitude/frequency data

### Plot grid
- Default 2×2 grid of plots; **add/remove rows** and **add/remove columns** independently
- Resizable **splitters** between plots/columns/rows; **Reset plot spacing** (View menu) redistributes them evenly
- **Global point size** slider (toolbar) affecting every plot at once
- Each plot cell independently configurable — nothing is a "fixed" plot type

### Per-plot controls
- **X-axis picker** and **Y-axis picker** (click the axis label) — choose any series, including multiple series on one axis
- Putting **Time on the Y axis** transposes that plot (time runs vertically)
- **Frequency** as X gives a spectrum-slice plot; **Magnitude** is offered on Y for that
- Per-plot **options menu**:
  - **Colour by** a chosen series (mapped through a viridis gradient) or none
  - **Spectrogram** background image toggle (only when the value axis is in Hz or empty)
  - **Separate axis per series** — give each series its own Y scale instead of sharing one
  - **Trail (seconds)** — for XY (non-time) plots, show a fading trail of recent points instead of a static scatter
  - **Point size** slider scoped to that one plot
- Plots automatically fall into one of three kinds depending on axis choice: time-scatter, XY trail, or spectrum-slice

### Mouse tools (toolbar)
- **Reset zoom** — restore default ranges on every plot
- **Zoom X-axis** / **Zoom Y-axis** — single-axis rubber-band zoom (mutually exclusive tools)
- **Measure** — drag to read out Δtime/Δvalue (or Δfrequency on log plots)
- **Select** (Edit menu) — the audio-editing selection tool described above
- Pan by default drag; all drag tools are mutually exclusive

### Overlays
- **Target bands**: shaded regions on any plotted series that has a target range defined
- **Frequency markers**: draggable reference lines at user-chosen frequencies, shared across every plot and every open window
  - Add a marker (right-click a frequency plot > "Add marker at N Hz" or type an exact value)
  - Drag a marker to move it, or right-click it to type an exact new value
  - Remove one marker or all markers via right-click menu
- **Annotations**: double-click empty space on a time plot to add a text note (marked with a star); click an existing marker to edit or delete its text
- Playhead line shown on every time-based plot

### Targets
- **Targets > Set Targets...** dialog: enable/disable and set min/max for Loudness, Pitch, F1, F2, F3, F1/F2/F3-Pitch ratios, Size, Weight, Slopes, H1-H2, H1-H3, H1-H4, H1-A3, plus a custom name for the target profile
- One-click preset targets: **Female** / **Male** (from `resources/targets/`)
- **Import targets...** / **Export targets...** as JSON
- Current target name shown in the toolbar

### Series colours
- **View > Series colours...** dialog: recolour any plotted series via a colour picker, per series
- **Default** button per series to revert one colour; **Restore Defaults** for all
- Cancel reverts any live-previewed changes; colour choices are application-wide (affect every plot/window) and persist across restarts

### Layout management
- **Load simple / medium / advanced layout** — built-in presets (`resources/layouts/`)
- **Load Layout... / Save Layout...** — custom layouts to/from JSON files
- The full plot grid (series choices, splitter sizes, point size) is auto-saved on exit and restored on next launch

### Appearance
- **Colour scheme**: OS Default / Light Mode / Dark Mode (View menu), live-updates all icons and plot themes

### Sample texts
- **View > Sample Texts** window: browse, view, create, edit, and save short Markdown reading passages (`resources/sample_texts/`) for the user to read aloud while recording

### Help
- **Help > Documentation** (`F1`): in-app browser of the bundled Markdown docs (`resources/docs/`), with a sidebar table of contents and clickable cross-links