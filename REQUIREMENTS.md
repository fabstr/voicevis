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

## 4. Analysis (AN)

- **AN-1** When an audio file is loaded, the system shall analyse it automatically, without requiring a separate user action.
- **AN-2** When a recording finishes, when an edit is applied to the audio, or when an edit is undone or redone, the system shall re-analyse the recording.
- **AN-3** When re-analysing, the system shall analyse only those portions of the audio that have changed and shall reuse cached results for the unchanged portions.
- **AN-4** While recording, the system shall analyse the incoming audio in near-real time.
- **AN-5** The system shall compute, for the recording, the quantities Pitch, Loudness, Size, F1, F2, F3, F1/Pitch, F2/Pitch, F3/Pitch, H1-H2, H1-H3, H1-H4, H1-A3, Jitter and Shimmer.
- **AN-6** The system shall compute raw spectrogram magnitude and frequency data for the recording.
- **AN-7** The system shall make every quantity in AN-5 and AN-6 available for selection on a plot axis.

## 5. Plot grid (PG)

- **PG-1** Where no saved layout applies, the system shall present the plot grid as a 2×2 arrangement of plots.
- **PG-2** When the user adds or removes a row, the system shall change the number of grid rows without changing the number of columns.
- **PG-3** When the user adds or removes a column, the system shall change the number of grid columns without changing the number of rows.
- **PG-4** When the user drags a splitter between plots, rows or columns, the system shall resize the adjacent cells accordingly.
- **PG-5** When the user selects *View > Reset plot spacing*, the system shall redistribute all splitters evenly.
- **PG-6** When the user changes the toolbar's global point size slider, the system shall apply the new point size to every plot in the session.
- **PG-7** The system shall allow every plot cell to be configured independently, and shall not fix the plot type of any cell.

## 6. Per-plot controls (PP)

- **PP-1** When the user clicks a plot's X-axis or Y-axis label, the system shall open a series picker for that axis.
- **PP-2** The series picker shall allow either a single series or several series to be selected for the axis.
- **PP-3** Where Time is selected on a plot's Y axis, the system shall transpose that plot so that time runs vertically.
- **PP-4** Where Frequency is selected on a plot's X axis, the system shall render that plot as a spectrum-slice plot and shall offer Magnitude as a Y-axis choice.
- **PP-5** The system shall provide, for each plot, an options menu offering *Colour by*, the *Spectrogram* background toggle, *Separate axis per series*, *Trail (seconds)* and a plot-scoped point size slider.
- **PP-6** Where a series is chosen under *Colour by*, the system shall colour that plot's points by the value of that series, mapped through a viridis gradient.
- **PP-7** Where *Colour by* is set to none, the system shall draw that plot's points without value-based colouring.
- **PP-8** Where a plot's value axis is expressed in Hz or is empty, the system shall offer the spectrogram background toggle for that plot.
- **PP-9** If a plot's value axis is neither expressed in Hz nor empty, then the system shall not offer the spectrogram background toggle for that plot.
- **PP-10** Where *Separate axis per series* is enabled, the system shall give each series on that plot its own Y scale instead of a shared one.
- **PP-11** Where a plot is an XY (non-time) plot and a trail length in seconds is set, the system shall draw a fading trail of the points from the preceding that many seconds instead of a static scatter.
- **PP-12** When the user changes a plot's own point size slider, the system shall apply the new size to that plot only.
- **PP-13** The system shall classify each plot as a time-scatter, XY-trail or spectrum-slice plot according to the series chosen for its axes.

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
- **TG-3** When the user selects *Targets > Set Targets...*, the system shall open a dialog listing Loudness, Pitch, F1, F2, F3, F1/Pitch, F2/Pitch, F3/Pitch, Size, Weight, Slopes, H1-H2, H1-H3, H1-H4 and H1-A3, each with an enable checkbox and a minimum and a maximum value, together with a *Config Name* for the target profile.
- **TG-4** When the user chooses *Apply & Close* in the Set Targets dialog, the system shall make the edited target the active target, update the target bands on every plot, and update the target name shown in the toolbar.
- **TG-5** When the user chooses *Cancel* in the Set Targets dialog, the system shall discard the edits and keep the previously active target.
- **TG-6** When the user selects *Targets > Female* or *Targets > Male*, the system shall load the corresponding preset from `resources/targets/` and make it the active target.
- **TG-7** When the user selects *Targets > Export targets...*, the system shall write the active target to a JSON file.
- **TG-8** When the user selects *Targets > Import targets...*, the system shall load a target from a JSON file, whether that file was exported by this application or supplied by another user, and make it the active target.
- **TG-9** When the user saves a target, the system shall suggest the target's *Config Name* as the default file name.
- **TG-10** Where an enabled target field has no corresponding plottable series (*Weight*, *Slopes*), the system shall not draw a target band for it. *(Known limitation, documented as such in the usage doc.)*

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
