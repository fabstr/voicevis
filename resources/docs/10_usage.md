# Usage of VoiceVis

- [General workflow](#general-workflow)
  - [1. Launch](#1-launch)
  - [2. Open a recording](#2-open-a-recording)
  - [3. Play it back](#3-play-it-back)
  - [4. Change what a plot shows](#4-change-what-a-plot-shows)
  - [5. Apply a target](#5-apply-a-target)
  - [6. Zoom in on a moment](#6-zoom-in-on-a-moment)
  - [7. Leave a note](#7-leave-a-note)
  - [From here](#from-here)
- [Working with targets](#working-with-targets)
  - [Presets](#presets)
  - [Building your own](#building-your-own)
  - [Sharing a target](#sharing-a-target)
- [Audio editing](#audio-editing)
  - [Selecting](#selecting)
  - [Editing the selection](#editing-the-selection)
  - [Gain](#gain)
  - [Undo](#undo)
- [Live analysis without recording](#live-analysis-without-recording)
- [Full feature list](#full-feature-list)
  - [Sessions & files](#sessions--files)
  - [Recording & playback](#recording--playback)
  - [Audio editing](#audio-editing-1)
  - [Analysis](#analysis)
  - [Plot grid](#plot-grid)
  - [Per-plot controls](#per-plot-controls)
  - [Mouse tools (toolbar)](#mouse-tools-toolbar)
  - [Overlays](#overlays)
  - [Targets](#targets)
  - [Series colours](#series-colours)
  - [Layout management](#layout-management)
  - [Appearance](#appearance)
  - [Sample texts](#sample-texts)
  - [Help](#help)

## General workflow

This walks through a first session end to end, using the sample clip
`F_swedish10.mp3` as the recording. Everything here works the same way for
your own recordings -- the audio just has to already exist somewhere on disk,
or be recorded from the microphone instead of opened from a file.

The screenshots below use the bundled **simple** layout (`View > Load simple
layout`) rather than the four-plot grid a fresh install starts with, because
it puts more of what there is to see on screen at once: Size and Pitch,
each coloured by Loudness, a Spectrogram, and a plain Loudness plot.

### 1. Launch

![The VoiceVis window on first launch: Size and Pitch (coloured by Loudness), a Spectrogram, and Loudness -- all empty, no file loaded yet](img/workflow/01_launch.png)

### 2. Open a recording

`File > Open` accepts `.wav` and `.mp3` files (dragging one onto the window
works too). Loading a new file clears any existing annotations and undo
history, since they described a different recording. Opening a file analyses
it automatically -- there's no separate "Analyse" step.

![The File menu open, showing New, Open, Save Annotations, Save Audio As and Close](img/workflow/02_open_menu.png)

![The same four plots filled in once analysis finishes: coloured scatters, a real spectrogram, and the loudness trace](img/workflow/03_loaded.png)

### 3. Play it back

Space, or the toolbar's play button, plays from the current position. The
playhead (the vertical line) moves across every time-based plot together,
since they share one time axis, and the Time field in the toolbar tracks it.
Clicking anywhere on a time plot seeks to that point instead.

![Mid-playback: a playhead line at 6.5s across all four plots, the toolbar button showing pause](img/workflow/04_playback.png)

### 4. Change what a plot shows

Click a plot's axis label to pick a different series -- it doubles as the
button that opens the picker. Here the Loudness plot's Y axis is being
changed to the three formants (F1, F2, F3) at once.

![The Y-axis picker open on the Loudness plot, a checklist of series with Loudness checked](img/workflow/05_axis_picker_menu.png)

![The same plot now showing F1, F2 and F3 instead](img/workflow/06_axis_picker_result.png)

### 5. Apply a target

A target is active from the moment the window opens -- the toolbar already
reads "Target: Default Target" on launch, and every plotted series with a
target band shows one even before you pick anything. `Targets > Female` (or
`Male`, or a target you build yourself -- see **Working with targets** below)
swaps in a different set of ranges.

![The Targets menu open: Set Targets..., Female, Male, Import targets..., Export targets...](img/workflow/07_targets_menu.png)

![The same grid after loading Female: the target bands have moved, and the toolbar now reads "Target: Default female"](img/workflow/08_targets_result.png)

### 6. Zoom in on a moment

The toolbar's Zoom X / Zoom Y buttons restrict a rubber-band drag to one axis;
because the time plots share an axis, zooming in on one zooms all of them
together (including the spectrogram). Reset zoom puts every plot back to its
default range. The Measure tool, next to the zoom buttons, works the same way
but reads out a Δtime/Δvalue instead of changing the view.

![All four plots zoomed in to roughly seconds 2-8 of the recording, spectrogram included](img/workflow/09_zoom.png)

### 7. Leave a note

Double-clicking empty space on a time plot opens a small text box for an
annotation at that point; clicking an existing marker (drawn as a star)
reopens it for editing or deletion. `File > Save Annotations` writes them out
as JSON, linked back to the audio file they belong to.

![The annotation dialog open over the Pitch plot, with a note being typed in](img/workflow/10_annotation_dialog.png)

![The saved annotation: a star marker on the Pitch plot at the point it was added](img/workflow/11_annotation_result.png)

### From here

- **Audio editing** below covers reshaping the recording itself -- selecting,
  moving, cutting or silencing a stretch of it.
- **Live analysis without recording** covers watching the plots while you
  speak, without producing a recording at all.
- **Working with targets** covers building a target profile of your own
  rather than using the Female/Male presets.
- The **Full feature list** further down is the complete reference: every
  menu entry, dialog and toolbar control, independent of this walkthrough's
  particular order.

## Working with targets

A target is a set of min/max ranges, one per feature, each optionally
enabled. Whichever target is active is named in the toolbar, and any plotted
series with an enabled range in it gets a shaded band on its plot -- there is
always *some* target active, even in a brand new session ("Default Target"),
not just after you pick one.

### Presets

`Targets > Female` and `Targets > Male` (from `resources/targets/`) are the
quickest way to switch: one click loads a ready-made set of ranges and
relabels the toolbar.

![The Targets menu open: Set Targets..., Female, Male, Import targets..., Export targets...](img/workflow/07_targets_menu.png)

The two presets are genuinely different ranges, not just a different name --
switching between them visibly moves every band. Female puts Pitch at
134-258 Hz and Size at 4-15; Male puts Pitch lower, at 79-143 Hz, and Size
higher, at 12-21 -- so the two bands swap which one sits higher on screen.
The formants shift too, by smaller amounts.

![Target bands after loading Female: Pitch's band sits high (134-258 Hz), Size's sits low (4-15)](img/workflow/08_targets_result.png)

![The same plots after loading Male instead: Pitch's band now sits low (79-143 Hz), Size's now sits high (12-21) -- and the toolbar reads "Target: Default male"](img/workflow/08b_targets_result_male.png)

### Building your own

`Targets > Set Targets...` opens a dialog listing every target-capable field:
a checkbox to enable it, and a min/max for the range. The **Config Name** at
the top is what shows up in the toolbar and gets suggested as the default
name when saving. **Apply & Close** applies the changes immediately, the same
way loading a preset does; **Cancel** discards them.

![The Set Targets dialog, populated with the Female preset's values -- config name, and an enable checkbox plus min/max per field](img/workflow/12_set_targets_dialog.png)

### Sharing a target

`Targets > Export targets...` saves the current target as a `.json` file;
`Targets > Import targets...` loads one back in, from this app or a `.json`
file someone else exported. That's how to hand a target profile to someone
else, or keep more than the two built-in presets around.

## Audio editing

Editing works on a selected stretch of the recording, made on any time-based
plot -- the same selection appears on every one of them at once, since they
all share one timeline.

### Selecting

With the Select tool active (`Edit > Select Audio`, or its toolbar/menu
button), drag on any time plot to mark a range. Drag one of the band's edges
to resize the selection, or drag the band itself to move that stretch of
audio to a new position -- overwriting whatever is there, and leaving silence
behind where it used to be. Turning Select off clears the selection, so an
edit can never land on a range you can no longer see.

![A selection band (8s-10s) drawn across all four plots, the Select tool active](img/workflow/13_select_band.png)

### Editing the selection

Three destructive edits work on whatever is currently selected, all in the
**Edit** menu:

- **Replace with Silence** zeroes the selected samples out but keeps the
  recording the same length -- everything after the edit stays exactly where
  it was.
- **Cut Selection** removes the selected stretch and closes the gap, so the
  recording gets shorter and everything after it shifts earlier. The
  selection is dropped afterwards, since it no longer describes the same
  audio.
- Dragging the selection band itself (above) **moves** it, which is the
  third way to edit -- no separate menu entry needed.

The screenshot below shows the result of Replace with Silence on the
selection above: a flat gap in every plot, and a clean silent column in the
spectrogram.

![The same range after Replace with Silence: flat data in every scatter plot and a silent gap in the spectrogram](img/workflow/14_silence_result.png)

### Gain

`Edit > Gain...` asks for a level change in dB and applies it to the audio
**before the session does anything with it** -- analysing, playing and saving
alike. A positive figure lifts a recording made at too low an input level, a
negative one attenuates. It applies to the selection if there is one, and to
the whole recording if there is not.

![The Gain dialog over the four plots, with -6.0 dB entered](img/workflow/15_gain_dialog.png)

A gain is not an edit to the recording: it changes what the session *does*
with the audio, not the audio it holds. Playback comes out at the new level,
and so does every number derived from it -- loudness most obviously, but the
harmonic ratios and the formant estimates shift with the level too. The file
you opened is never touched. The toolbar names the gain while one is in force,
so it is not a setting you can forget you left on; hovering it lists the
ranges.

![The same plots after -6 dB: the Loudness colour scale now tops out at 2.5 instead of 4, the spectrogram is dimmer, and the toolbar reads "Gain: -6.0 dB"](img/workflow/16_gain_result.png)

Setting a range back to **0 dB** removes its gain -- that, rather than Undo,
is the way back, since a gain is not an edit to undo. Loading a different file
clears the gains with it.

Two things worth knowing:

- **Saving carries the gain.** `File > Save Audio As...` writes the audio the
  analysis saw, gain included -- so the wav on disk matches the numbers. The
  file you originally opened is left as it was; only a save writes a gained
  one, and only where you tell it to.
- **A large gain can clip.** Samples pushed past full scale are clamped, which
  flattens the peaks of the waveform -- both the one you hear and the one the
  analysis measures. VoiceVis says so when it happens; back the gain off if it
  does.

### Undo

`Edit > Undo` / `Edit > Redo` (or the standard shortcuts) step back and
forward through recording, clearing, and every edit above -- the menu entry
itself names what it would undo or redo next, so it's never a guess.

## Live analysis without recording

`Edit > Live Analysis` (or the `L` key) opens the microphone and plots what it
hears, at the same rate and in the same detail as a finished recording -- but
keeps none of it. Press `L` again (or `Space`, or `Edit > Stop Live Analysis`)
to stop.

Use it when the feedback is the point rather than the take: working a vowel,
feeling for a resonance shift, warming up. Recording answers *what did I just
say?*; this answers *what am I saying?*, without leaving a pile of attempts
behind.

While it runs:

- The plots show the microphone instead of the session's own analysis, and the
  time axis scrolls with a 10 s window, exactly as it does while recording.
- The last **30 seconds** are kept, so you can zoom out and look back over the
  last few attempts. Anything older is dropped -- nothing is being written
  down, and an open-ended session cannot be allowed to fill memory.
- The audio-editing tools are switched off. What is on screen is not the
  recording, so an edit made from it would land somewhere you cannot see.
- Annotations are not taken, for the same reason.

When it stops, the session comes back exactly as it was: the same analysis,
the same playhead position, the same time axis, and the recording, its undo
history and its annotations all untouched. Starting a recording, pressing play,
loading a file or undoing an edit stops live analysis first and then does what
was asked.

The microphone signal is analysed as it arrives, so a gain set with
`Edit > Gain...` does not apply -- a gain describes a stretch of the recording,
and this is not part of one.

## Full feature list

### Sessions & files
- **File > New** opens another independent session window (own audio, analysis, plots, targets)
- **File > Open** an audio file (`.wav`, `.mp3`) or an annotations file (`.json`)
- **Drag-and-drop** a `.wav`/`.mp3`/`.json` file onto the window to load it
- **File > Save Annotations** to a `.json` file (linked to the source audio path, with a fallback path)
- **File > Save Audio As...** exports the in-memory recording to a `.wav` file, with any gain applied
- **File > Close** closes the current window/session
- Windows cascade automatically when opened, and the title bar shows the loaded file name

### Recording & playback
- **Record** from the default microphone (`R` key or toolbar/menu), with live waveform capture into memory
- **Stop recording** (`R` again, or Space)
- **Play / Pause** the loaded or recorded audio (Space, or the toolbar play button)
- **Seek**: type a time into the "Time:" box, or click on any time-based plot to jump the playhead there
- **Live Analysis** — analyse the microphone without recording it (`L` key or Edit menu); the last 30 s are kept and the session is restored untouched when it stops
- **Stop live analysis** (`L` again, or Space)
- **Clear** the entire recording/session (`D` key)
- Recording extends/overwrites a specific position (so you can punch in over prior audio)
- Playhead auto-scrolls: 10 s window while recording, page-forward once past 50% of the view while playing

### Audio editing
- **Select** a time range by dragging on any time-based plot (Select tool)
- Drag the **edges** of a selection to resize it
- Drag the **band itself** to move that audio to a new position (overwrites destination, leaves silence behind)
- **Replace with Silence** — zero out the selected range, keeping timeline length
- **Cut Selection** — remove the selected range and close the gap (shortens recording)
- **Gain...** — a level change in dB applied to the audio before analysis: the selection if there is one, otherwise the whole recording
- The gain reaches the analysis, playback and `Save Audio As` alike; the file on disk is the one thing it never reaches, and 0 dB removes it
- A gain follows the audio it covers through a cut or a move, and is cleared when a different file is loaded
- **Undo / Redo** for record, clear, silence, cut, and move — menu labels show what will be undone/redone
- Leaving Select mode clears the current selection

### Analysis
- Automatic re-analysis after recording, playback edits, undo/redo, or loading a file
- Chunked/cached analysis (only re-analyzes the portions of audio that changed)
- Live, near-real-time analysis while recording, and while running Live Analysis without recording
- Computed/plottable quantities: **Pitch, Loudness, Weight, Size, Formants (F1, F2, F3), Formant/Pitch ratios (F1/Pitch, F2/Pitch, F3/Pitch), Harmonic differences (H1-H2, H1-H3, H1-H4, H1-A3), Jitter, Shimmer**, plus raw spectrogram magnitude/frequency data

### Plot grid
- Default 2×2 grid of plots; **add/remove rows** and **add/remove columns** independently
- Resizable **splitters** between plots/columns/rows; **Reset plot spacing** (View menu) redistributes them evenly
- **Global point size** slider (toolbar) affecting every plot at once
- Each plot cell independently configurable — nothing is a "fixed" plot type

### Per-plot controls
- **X-axis picker** and **Y-axis picker** (click the axis label) — choose any series, including multiple series on one axis
- Putting **Time on the Y axis** transposes that plot (time runs vertically)
- **Frequency** as X gives a spectrum-slice plot; **Magnitude** is offered on Y for that
- **Radar** as X arranges every series chosen on Y around a circle, one spoke each, evenly spaced. A spoke runs from the centre (the bottom of that series' range) to the outer ring (the top of it) and carries a numbered scale on both sides. Its target range is drawn as a box along it, and each value is drawn on top as a line across the spoke, three quarters as wide as that box, fading out with age like a trail — so several features can be watched against their targets at once
- Per-plot **options menu**:
  - **\<series\> colour source** — one entry per series the plot draws (e.g. *Pitch colour source*, *Size colour source*): the series whose value colours that one's points, or none to leave it in its own colour. Each drawn series is set independently, so a plot showing three series can colour each by something different
  - **\<series\> colour map** — which gradient that series' colour source runs through: **Viridis** (the default), **Plasma** or **Turbo**. Saved with the layout, and offered only once that series has a colour source
  - The same options menu appears on every plot, whatever kind it is; the colour entries simply name whatever that plot happens to be drawing
  - A colour bar appears for each coloured series, labelled with the series it colours and the series it measures. Its scale is the colour source's own range — the same range *Reset zoom* restores — so a colour means the same thing in every plot and in every recording, rather than rescaling itself to whatever the current take happens to cover
  - **Show colour scales** — turn the colour bars off for that plot when its width is better spent on the plot itself. What is coloured, and how, is unaffected
  - **Spectrogram** background image toggle (only when the value axis is in Hz or empty)
  - **Separate axis per series** — give each series its own Y scale instead of sharing one
  - **Trail (seconds)** — for XY and radar plots, show a fading trail of recent points instead of a static scatter
  - **Point size** slider scoped to that one plot
- Plots automatically fall into one of four kinds depending on axis choice: time-scatter, XY trail, spectrum-slice, or radar

### Mouse tools (toolbar)
- **Reset zoom** — restore default ranges on every plot
- **Zoom X-axis** / **Zoom Y-axis** — single-axis rubber-band zoom (mutually exclusive tools)
- **Measure** — drag to read out Δtime/Δvalue (or Δfrequency on log plots)
- **Select** (Edit menu) — the audio-editing selection tool described above
- Pan by default drag; all drag tools are mutually exclusive

### Overlays
- **Target bands**: shaded regions on any plotted series that has a target range defined — drawn as a box along the spoke on a radar plot
- **Frequency markers**: draggable reference lines at user-chosen frequencies, shared across every plot and every open window
  - Add a marker (right-click a frequency plot > "Add marker at N Hz" or type an exact value)
  - Drag a marker to move it, or right-click it to type an exact new value
  - Remove one marker or all markers via right-click menu
- **Annotations**: double-click empty space on a time plot to add a text note (marked with a star); click an existing marker to edit or delete its text
- Playhead line shown on every time-based plot

### Targets
- **Targets > Set Targets...** dialog: enable/disable and set min/max for Loudness, Pitch, F1, F2, F3, F1/F2/F3-Pitch ratios, Size, Weight, H1-H2, H1-H3, H1-H4, H1-A3, plus a custom name for the target profile
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