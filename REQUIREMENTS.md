# VoiceVis — Requirements (EARS)

Requirements derived from the **Full feature list** in
[resources/docs/10_usage.md](resources/docs/10_usage.md), with clarifications
taken from the walkthrough sections of that same document. Nothing here is
derived from the source code — where the usage doc is silent, the gap is
recorded under [Open points](#open-points) rather than guessed at.

Throughout, *the system* means the VoiceVis application, and *a session* means
one window together with its own audio, analysis, plot grid and target.

Every new user-visible behaviour is added here as it is built. How to number it,
and what else has to be updated alongside it, is in
[SPEC.md § Definition of done](SPEC.md#7-definition-of-done-for-a-feature).

## EARS patterns used

| Pattern | Form |
|---|---|
| Ubiquitous | The system shall &lt;response&gt;. |
| Event-driven | When &lt;trigger&gt;, the system shall &lt;response&gt;. |
| State-driven | While &lt;state&gt;, the system shall &lt;response&gt;. |
| Optional / conditional feature | Where &lt;feature or configuration&gt;, the system shall &lt;response&gt;. |
| Unwanted behaviour | If &lt;trigger&gt;, then the system shall &lt;response&gt;. |
| Complex | Combinations of the above. |

## 1. Sessions and files (SF)

- **SF-1** When the user selects *File > New*, the system shall open an additional session window whose audio, analysis, plots and targets are independent of every other open session.
- **SF-2** When the user selects *File > Open* and chooses a `.wav` or `.mp3` file, the system shall load that file as the current recording.
- **SF-3** When the user selects *File > Open* and chooses a `.json` annotations file, the system shall load the annotations it contains into the current session.
- **SF-4** When the user drags a `.wav`, `.mp3` or `.json` file onto a session window, the system shall load it into that session as if it had been opened via *File > Open*.
- **SF-5** When a new audio file is loaded, the system shall discard the existing annotations and undo history of that session.
- **SF-6** When the user selects *File > Save Annotations*, the system shall write the session's annotations to a `.json` file that records the source audio path together with a fallback path.
- **SF-7** When the user selects *File > Save Audio As...*, the system shall export the in-memory recording to a `.wav` file.
- **SF-8** When the user selects *File > Close*, the system shall close the current window and end its session.
- **SF-9** When a session window is opened, the system shall place it cascaded relative to the already-open windows.
- **SF-10** While a file is loaded, the system shall show that file's name in the window title bar.
- **SF-11** When the user selects *File > Save Audio As...*, the system shall apply the gains in force (AE-19) to the exported audio.

## 2. Recording and playback (RP)

- **RP-1** When the user presses `R`, or activates Record from the toolbar or menu, the system shall start recording from the default microphone.
- **RP-2** While recording, the system shall capture the incoming waveform into memory.
- **RP-3** While recording, when the user presses `R` or `Space`, the system shall stop recording.
- **RP-4** When recording is started at a position that already contains audio, the system shall extend the recording from that position and overwrite the audio already there.
- **RP-5** While not recording, when the user presses `Space` or activates the toolbar play button, the system shall play the loaded or recorded audio from the current playhead position.
- **RP-6** While audio is playing, when the user presses `Space` or activates the toolbar pause button, the system shall pause playback.
- **RP-7** When the user types a time into the toolbar's *Time:* box, the system shall move the playhead to that time.
- **RP-8** When the user clicks on a time-based plot, the system shall move the playhead to the time corresponding to the clicked position.
- **RP-9** While the playhead is moving, the system shall keep the toolbar's *Time:* field in step with it.
- **RP-10** When the user presses `D`, the system shall clear the entire recording and session.
- **RP-11** While recording, the system shall auto-scroll the time axis so that a 10 s window around the current position stays visible.
- **RP-12** While playing, when the playhead passes 50 % of the visible time range, the system shall page the view forward.
- **RP-13** When the user selects *Edit > Live Analysis*, or presses `L`, the system shall start analysing the default microphone without capturing it into the recording.
- **RP-14** While live analysis is running, the system shall plot the incoming analysis in place of the session's own.
- **RP-15** While live analysis is running, the system shall auto-scroll the time axis so that a 10 s window around the current position stays visible.
- **RP-16** While live analysis is running, the system shall retain at most the most recent 30 s of the incoming analysis.
- **RP-17** While live analysis is running, the system shall disable the audio-editing tools.
- **RP-18** While live analysis is running, when the user presses `L` or `Space`, or selects *Edit > Stop Live Analysis*, the system shall stop live analysis.
- **RP-19** While live analysis is running, if the user starts recording or playback, loads a file, or undoes or redoes an edit, then the system shall stop live analysis before carrying that out.
- **RP-20** When live analysis stops, the system shall restore the analysis, the playhead position and the time axis that the session had before it started.
- **RP-21** When live analysis stops, the system shall leave the recording, its undo history and its annotations as they were before it started.

## 3. Audio editing (AE)

- **AE-1** When the user selects *Edit > Select Audio*, or its toolbar or menu button, the system shall activate the Select tool.
- **AE-2** Where the Select tool is active, when the user drags on a time-based plot, the system shall create a time-range selection covering the dragged range.
- **AE-3** While a selection exists, the system shall display that same selection on every time-based plot.
- **AE-4** Where the Select tool is active, when the user drags an edge of the selection band, the system shall resize the selection to the dragged edge.
- **AE-5** Where the Select tool is active, when the user drags the selection band itself, the system shall move the selected audio to the drop position, overwriting the audio already at the destination and leaving silence at the original position.
- **AE-6** When the user selects *Edit > Replace with Silence*, the system shall zero the samples in the selected range and shall keep the total length of the recording unchanged.
- **AE-7** When the user selects *Edit > Cut Selection*, the system shall remove the samples in the selected range, close the resulting gap so that all later audio shifts earlier, and shorten the recording accordingly.
- **AE-8** When a cut has been applied, the system shall clear the current selection.
- **AE-9** When the user leaves Select mode, the system shall clear the current selection.
- **AE-10** When the user selects *Edit > Undo*, the system shall revert the most recent record, clear, silence, cut or move operation.
- **AE-11** When the user selects *Edit > Redo*, the system shall re-apply the most recently undone operation.
- **AE-12** The system shall label the *Undo* and *Redo* menu entries with the operation that they would respectively undo and redo.
- **AE-13** When the user selects *Edit > Gain...*, the system shall open a dialog in which a level change, in dB, can be entered, positive for gain and negative for attenuation.
- **AE-14** When the Gain dialog is opened, the system shall show the gain currently in force over the range that applying it will act on.
- **AE-15** Where a selection exists, when the user applies a gain, the system shall apply that gain to the selected range only.
- **AE-16** Where no selection exists, when the user applies a gain, the system shall apply that gain to the whole recording.
- **AE-17** When a gain is applied over a range that already carries one, the system shall replace the earlier gain wherever the two ranges overlap.
- **AE-18** When the user applies a gain of 0 dB, the system shall remove any gain in force over that range.
- **AE-19** The system shall apply every gain in force to the audio that it analyses.
- **AE-20** When the system plays back the recording (RP-5), it shall play it with the gains in force applied.
- **AE-21** While a non-zero gain is in force anywhere in the recording, the system shall show the user that this is so, together with the gain's value.
- **AE-22** When a new audio file is loaded, the system shall discard the gains in force in that session.
- **AE-23** If a gain would drive samples past full scale, then the system shall clamp them at full scale and shall tell the user that clipping occurred.
- **AE-24** When the user cuts a selection, the system shall discard the gains in force over the cut range.
- **AE-25** When the user cuts a selection, the system shall keep the gains in force over the audio that follows the cut aligned with that audio as it shifts earlier.
- **AE-26** When the user moves a selection, the system shall move the gains in force over the moved range with the audio, leaving the origin range without them.
- **AE-27** When a moved gain lands on a range that already carries one, the system shall overwrite the gain at the destination, as AE-5 overwrites the audio there.
- **AE-28** The system shall leave the audio file it loaded from disk unmodified, whatever gains are in force. *(The gains reach the analysis (AE-19), playback (AE-20) and an export (SF-11); the file on disk is the one thing they never reach.)*
- **AE-29** When the user selects *Edit > Normalise Volume*, the system shall set the gain that puts the loudest sample of the range it acts on (AE-15, AE-16) just below full scale, without clipping it.
- **AE-30** When the user normalises the volume, the system shall work the gain out from the recorded samples, so that normalising replaces whatever gain was in force over that range rather than adding to it.
- **AE-31** If the range to be normalised is silent, then the system shall leave the gains in force unchanged and shall tell the user that there is nothing to normalise.

## 4. Analysis (AN)

- **AN-1** When an audio file is loaded, the system shall analyse it automatically, without requiring a separate user action.
- **AN-2** When a recording finishes, when an edit is applied to the audio, or when an edit is undone or redone, the system shall re-analyse the recording.
- **AN-3** When re-analysing, the system shall analyse only those portions of the audio that have changed and shall reuse cached results for the unchanged portions.
- **AN-4** While recording, the system shall analyse the incoming audio in near-real time.
- **AN-5** The system shall compute, for the recording, the quantities Pitch, Loudness, Weight, Size, F1, F2, F3, F1/Pitch, F2/Pitch, F3/Pitch, H1-H2, H1-H3, H1-H4, H1-A3, Jitter, Shimmer and CPPS.
- **AN-6** The system shall compute raw spectrogram magnitude and frequency data for the recording.
- **AN-7** The system shall make every quantity in AN-5 and AN-6 available for selection on a plot axis.
- **AN-8** When the gain in force over any part of the recording changes, the system shall re-analyse the affected audio.
- **AN-9** The system shall compute Weight, a single quantity combining the recording's H1-A3 and Loudness, which rises as H1-A3 falls.
- **AN-10** The system shall compute CPPS, the prominence in decibels of each frame's cepstral peak above that frame's cepstral baseline, which rises as the voice's harmonic structure becomes clearer relative to its noise floor.

## 5. Plot grid (PG)

- **PG-1** Where no saved layout applies, the system shall present the plot grid as a 2×2 arrangement of plots.
- **PG-2** When the user adds or removes a row, the system shall change the number of grid rows without changing the number of columns.
- **PG-3** When the user adds or removes a column, the system shall change the number of grid columns without changing the number of rows.
- **PG-4** When the user drags a splitter between plots, rows or columns, the system shall resize the adjacent cells accordingly.
- **PG-5** When the user selects *View > Reset plot spacing*, the system shall redistribute all splitters evenly.
- **PG-6** When the user changes the toolbar's global point size slider, the system shall apply the new point size to every plot in the session.
- **PG-7** The system shall allow every plot cell to be configured independently, and shall not fix the plot type of any cell.
- **PG-8** When the user resizes the window, the system shall stop it shrinking below the size the plot grid needs to draw every plot unclipped.
- **PG-9** If the size PG-8 asks for exceeds the display, then the system shall limit the window's minimum to the available screen.

## 6. Per-plot controls (PP)

- **PP-1** When the user clicks a plot's X-axis or Y-axis label, the system shall open a series picker for that axis.
- **PP-2** The series picker shall allow either a single series or several series to be selected for the axis.
- **PP-3** Where Time is selected on a plot's Y axis, the system shall transpose that plot so that time runs vertically.
- **PP-4** Where Frequency is selected on a plot's X axis, the system shall render that plot as a spectrum-slice plot and shall offer Magnitude as a Y-axis choice.
- **PP-5** ~~The system shall provide, for each plot, an options menu offering *Colour by*, *Colour map*, the *Spectrogram* background toggle, *Separate axis per series*, *Trail (seconds)* and a plot-scoped point size slider.~~ *(withdrawn — superseded by PP-27, which moves the choice from the plot to each series it draws.)*
- **PP-6** ~~Where a series is chosen under *Colour by*, the system shall colour that plot's points by the value of that series, mapped through that plot's chosen colour map.~~ *(withdrawn — superseded by PP-29, which moves the choice from the plot to each series it draws.)*
- **PP-7** ~~Where *Colour by* is set to none, the system shall draw that plot's points without value-based colouring.~~ *(withdrawn — superseded by PP-30, which moves the choice from the plot to each series it draws.)*
- **PP-8** Where a plot's value axis is expressed in Hz or is empty, the system shall offer the spectrogram background toggle for that plot.
- **PP-9** If a plot's value axis is neither expressed in Hz nor empty, then the system shall not offer the spectrogram background toggle for that plot.
- **PP-10** Where *Separate axis per series* is enabled, the system shall give each series on that plot its own Y scale instead of a shared one.
- **PP-11** Where a plot is an XY (non-time) plot and a trail length in seconds is set, the system shall draw a fading trail of the points from the preceding that many seconds instead of a static scatter.
- **PP-12** When the user changes a plot's own point size slider, the system shall apply the new size to that plot only.
- **PP-13** ~~The system shall classify each plot as a time-scatter, XY-trail or spectrum-slice plot according to the series chosen for its axes.~~ *(withdrawn — superseded by PP-24, which adds the radar plot of PP-19 to the list of kinds.)*
- **PP-14** ~~The system shall offer, for each plot, a *Colour map* choice of Viridis, Plasma or Turbo.~~ *(withdrawn — superseded by PP-31, which moves the choice from the plot to each series it draws.)*
- **PP-15** ~~Where no colour map has been chosen for a plot, the system shall use Viridis for that plot.~~ *(withdrawn — superseded by PP-32, which moves the choice from the plot to each series it draws.)*
- **PP-16** ~~When the user changes a plot's colour map, the system shall redraw that plot's coloured points and its colour bar through the newly chosen map.~~ *(withdrawn — superseded by PP-33, which moves the choice from the plot to each series it draws.)*
- **PP-17** ~~If a plot has no series chosen under *Colour by*, then the system shall not offer the *Colour map* choice for that plot.~~ *(withdrawn — superseded by PP-35, which moves the choice from the plot to each series it draws.)*
- **PP-18** The system shall draw the spectrogram background through Viridis regardless of the plot's chosen colour map.
- **PP-19** Where Radar is selected on a plot's X axis, the system shall render that plot as a radar plot, drawing every series selected on its Y axis on a spoke of its own.
- **PP-20** The system shall space a radar plot's spokes evenly around the circle, with the first pointing upwards.
- **PP-21** Where a series is drawn on a radar plot, the system shall place its value along its spoke between the centre, at the bottom of that series' range, and the outer ring, at the top of it.
- **PP-22** Where the active target has a range for a series drawn on a radar plot, the system shall draw that range as a box along that series' spoke, beneath the points.
- **PP-23** Where a trail length in seconds is set on a radar plot, the system shall draw a fading trail of each spoke's points from the preceding that many seconds.
- **PP-24** The system shall classify each plot as a time-scatter, XY-trail, spectrum-slice or radar plot according to the series chosen for its axes.
- **PP-25** Where a value is drawn on a radar plot, the system shall draw it as a line across its spoke, three quarters as wide as that spoke's target box.
- **PP-26** The system shall mark a numbered scale along each of a radar plot's spokes, on both sides of it.
- **PP-27** The system shall provide, for each plot, an options menu offering a *\<series\> colour source* and a *\<series\> colour map* choice for every series that plot draws, together with the *Spectrogram* background toggle, *Separate axis per series*, *Trail (seconds)* and a plot-scoped point size slider.
- **PP-28** The system shall offer that same options menu on every plot, whatever kind of plot it is.
- **PP-29** Where a series is chosen as a drawn series' colour source, the system shall colour that drawn series' points by the value of the chosen series, mapped through that drawn series' own colour map.
- **PP-30** Where a drawn series' colour source is set to none, the system shall draw that series in its own series colour.
- **PP-31** The system shall offer, for each drawn series, a colour map choice of Viridis, Plasma or Turbo.
- **PP-32** Where no colour map has been chosen for a drawn series, the system shall use Viridis for that series.
- **PP-33** When the user changes a drawn series' colour source or colour map, the system shall redraw that series' points and its colour bar accordingly, and shall leave the plot's other series as they were.
- **PP-34** Where more than one of a plot's drawn series has a colour source, the system shall show one colour bar per such series, each labelled with the series it colours and the series it measures.
- **PP-35** If a drawn series has no colour source, then the system shall not offer a colour map choice for that series.
- **PP-36** The system shall map a colour source's values onto its colour map across that source series' own default range, and shall label the corresponding colour bar over that same range, whether or not a recording has been analysed.
- **PP-37** The system shall provide, for each plot, a *Show colour scales* option, and where it is turned off shall draw that plot's coloured series without drawing their colour bars.

## 7. Mouse tools (MT)

- **MT-1** When the user activates *Reset zoom*, the system shall restore the default axis ranges on every plot in the session.
- **MT-2** Where the *Zoom X-axis* tool is active, when the user drags a rubber band on a plot, the system shall zoom that plot's X axis to the dragged range and shall leave its Y axis unchanged.
- **MT-3** Where the *Zoom Y-axis* tool is active, when the user drags a rubber band on a plot, the system shall zoom that plot's Y axis to the dragged range and shall leave its X axis unchanged.
- **MT-4** When the time axis of any time-based plot is zoomed, the system shall apply the same time range to every other time-based plot, including the spectrogram.
- **MT-5** Where the *Measure* tool is active, when the user drags on a plot, the system shall read out the Δtime and Δvalue spanned by the drag, and shall leave the plot's view unchanged.
- **MT-6** Where the *Measure* tool is used on a logarithmic plot, the system shall read out Δfrequency.
- **MT-7** While no drag tool is active, the system shall pan the plot on drag.
- **MT-8** When the user activates one of the drag tools (*Zoom X-axis*, *Zoom Y-axis*, *Measure*, *Select*), the system shall deactivate any other drag tool that is active.

## 8. Overlays (OV)

- **OV-1** While the active target has an enabled range for a plotted series, the system shall draw a shaded band over that range on every plot that shows the series.
- **OV-2** When the user right-clicks a frequency plot and chooses *Add marker at N Hz*, the system shall add a frequency marker at that frequency.
- **OV-3** When the user enters an exact frequency value, the system shall add a frequency marker at that value.
- **OV-4** The system shall show every frequency marker on every plot in every open session window.
- **OV-5** When the user drags a frequency marker, the system shall move it to the dragged frequency.
- **OV-6** When the user right-clicks a frequency marker and enters an exact value, the system shall move that marker to that frequency.
- **OV-7** When the user chooses to remove a single marker from the right-click menu, the system shall remove only that marker.
- **OV-8** When the user chooses to remove all markers from the right-click menu, the system shall remove every frequency marker.
- **OV-9** When the user double-clicks empty space on a time-based plot, the system shall open a text box for a new annotation at that point.
- **OV-10** While an annotation exists, the system shall draw it on its plot as a star marker.
- **OV-11** When the user clicks an existing annotation marker, the system shall reopen it so that its text can be edited or the annotation deleted.
- **OV-12** While audio is loaded, the system shall draw the playhead as a line at the current time on every time-based plot.

## 9. Targets (TG)

- **TG-1** The system shall have exactly one active target at all times, including in a session in which the user has not chosen one (*Default Target*).
- **TG-2** The system shall show the name of the active target in the toolbar.
- **TG-3** When the user selects *Targets > Set Targets...*, the system shall open a dialog listing Loudness, Pitch, F1, F2, F3, F1/Pitch, F2/Pitch, F3/Pitch, Size, Weight, H1-H2, H1-H3, H1-H4 and H1-A3, each with an enable checkbox and a minimum and a maximum value, together with a *Config Name* for the target profile.
- **TG-4** When the user chooses *Apply & Close* in the Set Targets dialog, the system shall make the edited target the active target, update the target bands on every plot, and update the target name shown in the toolbar.
- **TG-5** When the user chooses *Cancel* in the Set Targets dialog, the system shall discard the edits and keep the previously active target.
- **TG-6** When the user selects *Targets > Female* or *Targets > Male*, the system shall load the corresponding preset from `resources/targets/` and make it the active target.
- **TG-7** When the user selects *Targets > Export targets...*, the system shall write the active target to a JSON file.
- **TG-8** When the user selects *Targets > Import targets...*, the system shall load a target from a JSON file, whether that file was exported by this application or supplied by another user, and make it the active target.
- **TG-9** When the user saves a target, the system shall suggest the target's *Config Name* as the default file name.
- **TG-10** ~~Where an enabled target field has no corresponding plottable series (*Weight*, *Slopes*), the system shall not draw a target band for it.~~ *(withdrawn — Weight is a plottable series as of AN-9, and Slopes is no longer offered in the dialog, so every field in TG-3 now draws a band.)*

## 10. Series colours (SC)

- **SC-1** When the user selects *View > Series colours...*, the system shall open a dialog offering a colour picker for each plotted series.
- **SC-2** When the user picks a colour for a series, the system shall preview that colour on the plots immediately.
- **SC-3** When the user activates a series' *Default* button, the system shall revert that one series to its default colour.
- **SC-4** When the user activates *Restore Defaults*, the system shall revert every series to its default colour.
- **SC-5** When the user cancels the Series colours dialog, the system shall revert every colour previewed during that dialog.
- **SC-6** When a series colour is applied, the system shall apply it to that series on every plot in every open window.
- **SC-7** The system shall persist series colour choices across application restarts.

## 11. Layout management (LM)

- **LM-1** When the user selects *Load simple layout*, *Load medium layout* or *Load advanced layout*, the system shall load the corresponding built-in preset from `resources/layouts/` into the current session.
- **LM-2** When the user selects *Save Layout...*, the system shall write the current plot layout to a JSON file.
- **LM-3** When the user selects *Load Layout...*, the system shall load a plot layout from a JSON file.
- **LM-4** When the application exits, the system shall save the plot grid state, including each plot's series choices, the splitter sizes and the point size.
- **LM-5** When the application is next launched, the system shall restore the plot grid state saved under LM-4.
- **LM-6** When the system saves a plot layout, the system shall record each plot's chosen colour map.
- **LM-7** When the system loads a plot layout, the system shall restore each plot's recorded colour map.
- **LM-8** Where a loaded layout records no colour map for a plot, the system shall use Viridis for that plot.

## 12. Appearance (AP)

- **AP-1** The system shall offer the colour schemes *OS Default*, *Light Mode* and *Dark Mode* in the View menu.
- **AP-2** When the user selects a colour scheme, the system shall update all icons and plot themes immediately, without requiring a restart.

## 13. Sample texts (ST)

- **ST-1** When the user selects *View > Sample Texts*, the system shall open a window listing the reading passages in `resources/sample_texts/`.
- **ST-2** When the user selects a passage, the system shall display its Markdown content for reading aloud.
- **ST-3** The Sample Texts window shall allow the user to create a new passage, edit an existing passage, and save either to `resources/sample_texts/`.

## 14. Help (HP)

- **HP-1** When the user selects *Help > Documentation* or presses `F1`, the system shall open an in-app browser of the bundled Markdown documents in `resources/docs/`.
- **HP-2** The documentation browser shall present a sidebar table of contents for the bundled documents.
- **HP-3** When the user activates a cross-link within a bundled document, the system shall navigate to its target inside the documentation browser.

## Open points

Behaviours the usage document does not define. Listed here so that they are
not silently invented above.

1. What happens when *Replace with Silence* or *Cut Selection* is invoked with no selection active (AE-6, AE-7).
2. Whether recording, playback and the destructive edits are mutually exclusive, and what an attempt to start one during another does.
3. Error handling for a file that fails to load, a microphone that is unavailable, or an imported target, annotation or layout JSON that is malformed.
4. Whether annotations and the active target are per-session or application-wide. OV-4 states application-wide for frequency markers and SC-6 for series colours; the rest is unspecified.
5. Undo depth, and whether the undo history survives anything other than loading a new file (SF-5).
6. Whether *File > Open* of an annotations file requires matching audio to be loaded already, and what happens when the recorded source path does not resolve (SF-3, SF-6).
7. Quantitative limits: maximum recording length, supported sample rates, and the latency implied by "near-real time" (AN-4).
8. Whether the gains in force (AE-13) are saved alongside the annotations (SF-6), survive a restart, or are purely per-session.
