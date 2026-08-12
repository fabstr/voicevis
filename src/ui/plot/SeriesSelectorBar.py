"""The control strip above every plot.

    [X v] [Y v] [Colour v]        [x] Spectrogram   Trail (s): [__]   Size [---]

Constraints are enforced here rather than silently in the model, so that when
the app has to reduce a selection -- picking several series on both axes, for
instance -- the user sees it happen.
"""

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

import SeriesRegistry as Registry
from ui.plot.MultiSeriesSelector import MultiSeriesSelector
from ui.plot.PlotConfig import (MAX_TRAIL_TIME, MIN_TRAIL_TIME, PlotConfig, PlotKind,
                                colour_candidates)

MIN_POINT_SIZE = 1
MAX_POINT_SIZE = 5

COLOUR_DISABLED_HINT = "Colouring needs exactly one series on each axis"
SPECTROGRAM_DISABLED_HINT = ("The spectrogram is drawn in Hz, so it only lines up "
                             "with a Y axis in Hz (or no Y series at all)")


class SeriesSelectorBar(QtWidgets.QWidget):
    """Edits one plot's configuration."""

    config_changed = QtCore.pyqtSignal(object)

    def __init__(self, config: PlotConfig, parent=None):
        super().__init__(parent)
        self._config = config.copy()
        self._updating = False

        x_items = [Registry.SERIES[Registry.TIME_KEY],
                   Registry.SERIES[Registry.FREQUENCY_KEY]] + Registry.signal_series()
        # Time is offered on both axes: putting it on Y transposes the plot.
        y_items = ([Registry.SERIES[Registry.TIME_KEY]] + Registry.signal_series()
                   + [Registry.SERIES[Registry.MAGNITUDE_KEY]])

        self.x_selector = MultiSeriesSelector(x_items, allow_multi=True, prefix="X: ")
        self.y_selector = MultiSeriesSelector(y_items, allow_multi=True, allow_none=True, prefix="Y: ")
        # Frequency is only offered on a spectrum slice; _refresh_widgets greys
        # it out everywhere else.
        colour_items = Registry.signal_series() + [Registry.SERIES[Registry.FREQUENCY_KEY]]
        self.colour_selector = MultiSeriesSelector(colour_items, allow_multi=False,
                                                   allow_none=True, prefix="Colour: ")

        self.spectrogram_check = QtWidgets.QCheckBox("Spectrogram")

        self.trail_label = QtWidgets.QLabel("Trail (s):")
        self.trail_edit = QtWidgets.QLineEdit()
        self.trail_edit.setValidator(QtGui.QDoubleValidator(MIN_TRAIL_TIME, MAX_TRAIL_TIME, 2))
        self.trail_edit.setFixedWidth(48)

        self.size_label = QtWidgets.QLabel("Size:")
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(MIN_POINT_SIZE)
        self.size_slider.setMaximum(MAX_POINT_SIZE)
        self.size_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(1)
        self.size_slider.setFixedWidth(80)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.x_selector)
        layout.addWidget(self.y_selector)
        layout.addWidget(self.colour_selector)
        layout.addStretch()
        layout.addWidget(self.spectrogram_check)
        layout.addSpacing(8)
        layout.addWidget(self.trail_label)
        layout.addWidget(self.trail_edit)
        layout.addSpacing(8)
        layout.addWidget(self.size_label)
        layout.addWidget(self.size_slider)

        self.x_selector.selection_changed.connect(self._on_x_changed)
        self.y_selector.selection_changed.connect(self._on_y_changed)
        self.colour_selector.selection_changed.connect(self._on_colour_changed)
        self.spectrogram_check.toggled.connect(self._on_spectrogram_toggled)
        self.trail_edit.editingFinished.connect(self._on_trail_edited)
        self.size_slider.valueChanged.connect(self._on_size_changed)

        self.set_config(self._config)

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

    # --- Edits -----------------------------------------------------------

    def _on_x_changed(self, keys):
        if self._updating:
            return
        self._apply(x=keys)

    def _on_y_changed(self, keys):
        if self._updating:
            return
        self._apply(y=keys)

    def _on_colour_changed(self, keys):
        if self._updating:
            return
        self._apply(colour=keys[0] if keys else None)

    def _on_spectrogram_toggled(self, checked):
        if self._updating:
            return
        self._apply(spectrogram=bool(checked))

    def _on_size_changed(self, value):
        if self._updating:
            return
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
            self.colour_selector.set_selection([config.colour] if config.colour else [])
            self.size_slider.setValue(int(config.point_size))
            self.trail_edit.setText(f"{config.trail_time:.2f}")

            is_slice = config.kind is PlotKind.SPECTRUM_SLICE
            is_trail = config.kind is PlotKind.TRAIL

            # X and Y each allow several series, but only one axis at a time.
            self.x_selector.setEnabled(not is_slice)
            self.y_selector.setEnabled(not is_slice)

            colour_ok = config.colour_allowed()
            self.colour_selector.setEnabled(colour_ok)
            self.colour_selector.setToolTip("" if colour_ok else COLOUR_DISABLED_HINT)
            self.colour_selector.set_available(colour_candidates(config.kind))

            spectrogram_ok = config.spectrogram_allowed()
            self.spectrogram_check.setEnabled(spectrogram_ok)
            self.spectrogram_check.setChecked(config.spectrogram)
            self.spectrogram_check.setToolTip("" if spectrogram_ok else SPECTROGRAM_DISABLED_HINT)

            self.trail_label.setVisible(is_trail)
            self.trail_edit.setVisible(is_trail)
        finally:
            self._updating = False
