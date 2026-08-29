"""The controls around one plot.

The two axis pickers *are* the axis labels: they sit where pyqtgraph would have
drawn "Pitch (Hz)", and clicking one opens the series list. Everything else --
colour, spectrogram, separate axes, trail length, point size -- lives in a single
options menu in the corner, so the plot itself keeps the space.

The colour entries are per drawn series -- "Pitch colour source", "Pitch colour
map", "Size colour source" and so on -- so they depend on what the plot is
currently showing. They are therefore rebuilt each time the menu opens rather
than created once, the same way the frequency-marker menu is: building them in
response to a selection change would mean deleting the very menu whose action
was still being dispatched.

This is a controller rather than a widget: it owns the controls and the rules
they obey, and :class:`~ui.plot.PlotCell.PlotCell` decides where each one goes.
"""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

import SeriesRegistry as Registry
from ui.plot.ColourMapping import COLOUR_MAPS
from ui.plot.MultiSeriesSelector import MultiSeriesSelector, NONE_LABEL
from ui.plot.PlotConfig import (MAX_TRAIL_TIME, MIN_TRAIL_TIME, PlotConfig, PlotKind,
                                colour_candidates)

MIN_POINT_SIZE = 1
MAX_POINT_SIZE = 5

OPTIONS_GLYPH = "≡"          # a hamburger, for the options button

NOTHING_TO_COLOUR_HINT = "This plot draws no series to colour"
COLOUR_MAP_DISABLED_HINT = "Choose a colour source for this series first"
COLOUR_SOURCE_SUFFIX = "colour source"
COLOUR_MAP_SUFFIX = "colour map"
COLOUR_SCALES_HINT = "Show a colour bar beside the plot for each coloured series"
COLOUR_SCALES_DISABLED_HINT = "Nothing on this plot has a colour source yet"
Y_LOCKED_HINT = ("A spectrum slice only has magnitude to plot. "
                 "Change X away from Frequency to plot something else.")
SPECTROGRAM_DISABLED_HINT = ("The spectrogram is drawn in Hz, so it only lines up "
                             "with a value axis in Hz (or no series at all)")
SEPARATE_AXES_HINT = "Give each series its own scale instead of sharing one"
SEPARATE_AXES_DISABLED_HINT = "Only useful when an axis holds more than one series"


class PlotControls(QtCore.QObject):
    """Edits one plot's configuration."""

    config_changed = QtCore.pyqtSignal(object)

    def __init__(self, config: PlotConfig, parent=None):
        super().__init__(parent)
        self._config = config.copy()
        self._updating = False

        self._build_selectors()
        self._build_options_menu()
        self._refresh_widgets()

    # --- Construction ----------------------------------------------------

    def _build_selectors(self):
        # Radar sits with time and frequency: like them it names how the plot
        # is arranged rather than a quantity to put on the axis.
        x_items = [Registry.SERIES[Registry.TIME_KEY],
                   Registry.SERIES[Registry.FREQUENCY_KEY],
                   Registry.SERIES[Registry.RADAR_KEY]] + Registry.signal_series()
        # Time is offered on both axes: putting it on Y transposes the plot.
        y_items = ([Registry.SERIES[Registry.TIME_KEY]] + Registry.signal_series()
                   + [Registry.SERIES[Registry.MAGNITUDE_KEY]])

        self.x_selector = MultiSeriesSelector(x_items, allow_multi=True)
        # Drawn on its side, like the axis label it stands in for.
        self.y_selector = MultiSeriesSelector(y_items, allow_multi=True, allow_none=True,
                                              vertical=True)
        for selector in (self.x_selector, self.y_selector):
            selector.setAutoRaise(True)
        self.x_selector.selection_changed.connect(self._on_x_changed)
        self.y_selector.selection_changed.connect(self._on_y_changed)

    def _build_options_menu(self):
        self.options_button = QtWidgets.QToolButton()
        self.options_button.setText(OPTIONS_GLYPH)
        self.options_button.setToolTip("Plot options")
        self.options_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.options_button.setAutoRaise(True)

        self.options_menu = QtWidgets.QMenu()
        self.options_button.setMenu(self.options_menu)

        # The colour entries name the series they apply to, so they cannot be
        # built until the selection is known. They are inserted above the
        # toggle that governs them, every time the menu opens.
        self._colour_actions = []
        self._colour_menus = []
        self.options_menu.aboutToShow.connect(self._populate_colour_menus)

        self.colour_scales_action = self.options_menu.addAction("Show colour scales")
        self.colour_scales_action.setCheckable(True)
        self.colour_scales_action.toggled.connect(
            lambda checked: self._apply(colour_scales=bool(checked)))
        self._colour_anchor = self.colour_scales_action

        self.options_menu.addSeparator()

        self.spectrogram_action = self.options_menu.addAction("Spectrogram")
        self.spectrogram_action.setCheckable(True)
        self.spectrogram_action.toggled.connect(
            lambda checked: self._apply(spectrogram=bool(checked)))

        self.separate_axes_action = self.options_menu.addAction("Separate axis per series")
        self.separate_axes_action.setCheckable(True)
        self.separate_axes_action.setToolTip(SEPARATE_AXES_HINT)
        self.separate_axes_action.toggled.connect(
            lambda checked: self._apply(separate_axes=bool(checked)))

        self.options_menu.addSeparator()
        self.trail_action = self._build_trail_action()
        self.size_action = self._build_size_action()

    def _build_trail_action(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(20, 2, 8, 2)

        self.trail_edit = QtWidgets.QLineEdit()
        self.trail_edit.setValidator(QtGui.QDoubleValidator(MIN_TRAIL_TIME, MAX_TRAIL_TIME, 2))
        self.trail_edit.setFixedWidth(56)
        self.trail_edit.editingFinished.connect(self._on_trail_edited)

        layout.addWidget(QtWidgets.QLabel("Trail (s):"))
        layout.addStretch()
        layout.addWidget(self.trail_edit)

        action = QtWidgets.QWidgetAction(self.options_menu)
        action.setDefaultWidget(widget)
        self.options_menu.addAction(action)
        return action

    def _build_size_action(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(20, 2, 8, 2)

        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(MIN_POINT_SIZE)
        self.size_slider.setMaximum(MAX_POINT_SIZE)
        self.size_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(1)
        self.size_slider.setFixedWidth(90)
        self.size_slider.valueChanged.connect(self._on_size_changed)

        layout.addWidget(QtWidgets.QLabel("Point size:"))
        layout.addStretch()
        layout.addWidget(self.size_slider)

        action = QtWidgets.QWidgetAction(self.options_menu)
        action.setDefaultWidget(widget)
        self.options_menu.addAction(action)
        return action

    # --- External updates ------------------------------------------------

    @property
    def config(self) -> PlotConfig:
        return self._config

    def set_config(self, config: PlotConfig):
        """Show ``config`` without emitting a change."""
        self._config = config.copy()
        self._refresh_widgets()

    def set_point_size(self, size: int):
        """Used by the global size slider; does not emit."""
        self._config.point_size = int(size)
        self._updating = True
        try:
            self.size_slider.setValue(int(size))
        finally:
            self._updating = False

    def widgets(self):
        """Everything that needs theming."""
        return [self.x_selector, self.y_selector, self.options_button,
                self.trail_edit, self.size_slider]

    # --- Edits -----------------------------------------------------------

    def _on_x_changed(self, keys):
        if not self._updating:
            self._apply(x=keys)

    def _on_y_changed(self, keys):
        if not self._updating:
            self._apply(y=keys)

    def _on_size_changed(self, value):
        if not self._updating:
            self._apply(point_size=int(value))

    def _on_trail_edited(self):
        if self._updating:
            return
        text = self.trail_edit.text().replace(',', '.').strip()
        try:
            trail = float(text)
        except ValueError:
            logging.debug("Ignoring unreadable trail length %r", text)
            self._refresh_widgets()
            return
        self._apply(trail_time=trail)

    def _apply(self, **changes):
        if self._updating:
            return

        candidate = self._config.copy()
        for name, value in changes.items():
            setattr(candidate, name, value)

        # Explicit ranges came from a preset for a different series selection.
        if 'x' in changes:
            candidate.x_range = None
        if 'y' in changes:
            candidate.y_range = None

        self._config = candidate.normalised()
        self._refresh_widgets()
        self.config_changed.emit(self._config)

    # --- Presentation ----------------------------------------------------

    def _refresh_widgets(self):
        config = self._config
        self._updating = True
        try:
            self.x_selector.set_selection(config.x)
            self.y_selector.set_selection(config.y)
            # The pickers stand in for the axis labels, so they read as labels.
            self.x_selector.set_display_text(config.x_axis_label() or NONE_LABEL)
            self.y_selector.set_display_text(config.y_axis_label() or NONE_LABEL)

            self.size_slider.setValue(int(config.point_size))
            self.trail_edit.setText(f"{config.trail_time:.2f}")

            is_slice = config.kind is PlotKind.SPECTRUM_SLICE
            # Both kinds draw a fading window of history rather than a curve
            # against time, so both are steered by the trail length.
            has_trail = config.kind in (PlotKind.TRAIL, PlotKind.RADAR)

            # X is never disabled: changing it is the only way out of a plot
            # kind, so locking it would strand the cell on whatever it shows.
            self.y_selector.setEnabled(not is_slice)
            self.y_selector.setToolTip(Y_LOCKED_HINT if is_slice else self.y_selector.text())

            spectrogram_ok = config.spectrogram_allowed()
            self.spectrogram_action.setEnabled(spectrogram_ok)
            self.spectrogram_action.setChecked(config.spectrogram)
            self.spectrogram_action.setToolTip(
                "" if spectrogram_ok else SPECTROGRAM_DISABLED_HINT)

            # The bars are worth their width only once something is coloured.
            scales_ok = config.any_colour()
            self.colour_scales_action.setEnabled(scales_ok)
            self.colour_scales_action.setChecked(config.colour_scales)
            self.colour_scales_action.setToolTip(
                COLOUR_SCALES_HINT if scales_ok else COLOUR_SCALES_DISABLED_HINT)

            axes_ok = config.separate_axes_allowed()
            self.separate_axes_action.setEnabled(axes_ok)
            self.separate_axes_action.setChecked(config.separate_axes)
            self.separate_axes_action.setToolTip(
                SEPARATE_AXES_HINT if axes_ok else SEPARATE_AXES_DISABLED_HINT)

            self.trail_action.setVisible(has_trail)
        finally:
            self._updating = False

    def _populate_colour_menus(self):
        """Rebuild the per-series colour entries for whatever is drawn now."""
        for action in self._colour_actions:
            self.options_menu.removeAction(action)
        for menu in self._colour_menus:
            menu.setParent(None)
            menu.deleteLater()
        self._colour_actions, self._colour_menus = [], []

        specs = self._config.drawn_specs()
        if not specs:
            placeholder = QtGui.QAction(NOTHING_TO_COLOUR_HINT, self.options_menu)
            placeholder.setEnabled(False)
            self.options_menu.insertAction(self._colour_anchor, placeholder)
            self._colour_actions.append(placeholder)
            return

        for spec in specs:
            self._add_source_menu(spec)
            self._add_map_menu(spec)

    def _add_source_menu(self, spec):
        """"<Series> colour source": what a series' points are coloured by."""
        menu = self._insert_menu(f"{spec.label} {COLOUR_SOURCE_SUFFIX}")
        chosen = self._config.colour_source(spec.key)

        self._radio(menu, NONE_LABEL, chosen is None,
                    lambda: self._set_colour_source(spec.key, None))
        menu.addSeparator()

        for candidate in colour_candidates(self._config.kind):
            source = Registry.SERIES[candidate]
            self._radio(menu, source.label, candidate == chosen,
                        lambda key=candidate: self._set_colour_source(spec.key, key))

    def _add_map_menu(self, spec):
        """"<Series> colour map": which gradient that series' source runs through."""
        menu = self._insert_menu(f"{spec.label} {COLOUR_MAP_SUFFIX}")

        # Nothing to run through a gradient until a source is chosen, so the
        # entry stays visible -- and says why -- rather than coming and going.
        usable = self._config.is_coloured(spec.key)
        menu.setEnabled(usable)
        menu.setToolTip("" if usable else COLOUR_MAP_DISABLED_HINT)

        chosen = self._config.colour_map_of(spec.key)
        for key, label in COLOUR_MAPS:
            self._radio(menu, label, key == chosen,
                        lambda name=key: self._set_colour_map(spec.key, name))

    def _insert_menu(self, title: str) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(title, self.options_menu)
        self._colour_menus.append(menu)
        self._colour_actions.append(
            self.options_menu.insertMenu(self._colour_anchor, menu))
        return menu

    @staticmethod
    def _radio(menu, label: str, checked: bool, handler):
        """One choice in an exclusive submenu, checked to show the current one."""
        group = menu.findChild(QtGui.QActionGroup) or QtGui.QActionGroup(menu)
        group.setExclusive(True)
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(checked)
        action.triggered.connect(lambda _=False: handler())
        group.addAction(action)
        return action

    def _set_colour_source(self, key: str, source):
        sources = dict(self._config.colour_sources)
        sources[key] = source
        self._apply(colour_sources=sources)

    def _set_colour_map(self, key: str, name: str):
        maps = dict(self._config.colour_maps)
        maps[key] = name
        self._apply(colour_maps=maps)
