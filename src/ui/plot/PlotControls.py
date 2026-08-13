"""The controls around one plot.

The two axis pickers *are* the axis labels: they sit where pyqtgraph would have
drawn "Pitch (Hz)", and clicking one opens the series list. Everything else --
colour, spectrogram, separate axes, trail length, point size -- lives in a single
options menu in the corner, so the plot itself keeps the space.

This is a controller rather than a widget: it owns the controls and the rules
they obey, and :class:`~ui.plot.PlotCell.PlotCell` decides where each one goes.
"""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

import SeriesRegistry as Registry
from ui.plot.MultiSeriesSelector import MultiSeriesSelector, NONE_LABEL
from ui.plot.PlotConfig import (MAX_TRAIL_TIME, MIN_TRAIL_TIME, PlotConfig, PlotKind,
                                colour_candidates)

MIN_POINT_SIZE = 1
MAX_POINT_SIZE = 5

OPTIONS_GLYPH = "≡"          # a hamburger, for the options button

COLOUR_DISABLED_HINT = "Colouring needs exactly one series on each axis"
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
        x_items = [Registry.SERIES[Registry.TIME_KEY],
                   Registry.SERIES[Registry.FREQUENCY_KEY]] + Registry.signal_series()
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

        # Colour: one exclusive choice, so a submenu of radio items.
        self.colour_menu = self.options_menu.addMenu("Colour")
        self.colour_group = QtGui.QActionGroup(self)
        self.colour_group.setExclusive(True)
        self._colour_actions = {}

        none_action = self.colour_menu.addAction(NONE_LABEL)
        none_action.setCheckable(True)
        none_action.triggered.connect(lambda: self._apply(colour=None))
        self.colour_group.addAction(none_action)
        self._colour_actions[None] = none_action
        self.colour_menu.addSeparator()

        for spec in Registry.signal_series() + [Registry.SERIES[Registry.FREQUENCY_KEY]]:
            action = self.colour_menu.addAction(spec.label)
            action.setCheckable(True)
            action.triggered.connect(lambda _, key=spec.key: self._apply(colour=key))
            self.colour_group.addAction(action)
            self._colour_actions[spec.key] = action

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
            is_trail = config.kind is PlotKind.TRAIL

            # X is never disabled: changing it is the only way out of a plot
            # kind, so locking it would strand the cell on whatever it shows.
            self.y_selector.setEnabled(not is_slice)
            self.y_selector.setToolTip(Y_LOCKED_HINT if is_slice else self.y_selector.text())

            self._refresh_colour_menu(config)

            spectrogram_ok = config.spectrogram_allowed()
            self.spectrogram_action.setEnabled(spectrogram_ok)
            self.spectrogram_action.setChecked(config.spectrogram)
            self.spectrogram_action.setToolTip(
                "" if spectrogram_ok else SPECTROGRAM_DISABLED_HINT)

            axes_ok = config.separate_axes_allowed()
            self.separate_axes_action.setEnabled(axes_ok)
            self.separate_axes_action.setChecked(config.separate_axes)
            self.separate_axes_action.setToolTip(
                SEPARATE_AXES_HINT if axes_ok else SEPARATE_AXES_DISABLED_HINT)

            self.trail_action.setVisible(is_trail)
        finally:
            self._updating = False

    def _refresh_colour_menu(self, config):
        allowed = config.colour_allowed()
        self.colour_menu.setEnabled(allowed)
        self.colour_menu.setToolTip("" if allowed else COLOUR_DISABLED_HINT)

        candidates = set(colour_candidates(config.kind))
        for key, action in self._colour_actions.items():
            action.setChecked(key == config.colour)
            if key is not None:
                action.setVisible(key in candidates)
