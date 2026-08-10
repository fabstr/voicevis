"""A drop-down for picking one or several series."""

from PyQt6 import QtCore, QtWidgets

NONE_LABEL = "(none)"


class _CheckableMenu(QtWidgets.QMenu):
    """A menu that stays open while checkable items are being toggled."""

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action is not None and action.isEnabled() and action.isCheckable():
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MultiSeriesSelector(QtWidgets.QToolButton):
    """Picks series for one axis, or for the colour dimension.

    Series marked ``exclusive`` in the registry (time, frequency, magnitude)
    cannot share an axis, so checking one clears the rest and vice versa.
    """

    selection_changed = QtCore.pyqtSignal(list)

    def __init__(self, specs, allow_multi=True, allow_none=False, prefix="", parent=None):
        super().__init__(parent)
        self._specs = list(specs)
        self._allow_multi = allow_multi
        self._allow_none = allow_none
        self._prefix = prefix
        self._selection = []
        self._emitting = True

        self.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                           QtWidgets.QSizePolicy.Policy.Fixed)

        menu = _CheckableMenu(self) if allow_multi else QtWidgets.QMenu(self)
        self._actions = {}

        if allow_none:
            action = menu.addAction(NONE_LABEL)
            action.triggered.connect(lambda: self._set(([]), emit=True))
            menu.addSeparator()

        for spec in self._specs:
            action = menu.addAction(spec.label)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, key=spec.key: self._toggle(key, checked))
            self._actions[spec.key] = action

        self.setMenu(menu)
        self._update_text()

    # --- Selection -------------------------------------------------------

    def selection(self):
        return list(self._selection)

    def set_selection(self, keys):
        """Set the selection without emitting a change."""
        self._set([k for k in keys if k in self._actions], emit=False)

    def _toggle(self, key: str, checked: bool):
        spec = next(s for s in self._specs if s.key == key)
        selection = list(self._selection)

        if not checked:
            selection = [k for k in selection if k != key]
            if not selection and not self._allow_none:
                selection = [key]   # refuse to leave the axis empty
        elif not self._allow_multi or spec.exclusive:
            selection = [key]
        else:
            # A plain signal cannot coexist with an exclusive series.
            selection = [k for k in selection
                         if not next(s for s in self._specs if s.key == k).exclusive]
            selection.append(key)

        self._set(selection, emit=True)

    def _set(self, selection, emit: bool):
        ordered = [s.key for s in self._specs if s.key in set(selection)]
        changed = ordered != self._selection
        self._selection = ordered

        for key, action in self._actions.items():
            action.blockSignals(True)
            action.setChecked(key in self._selection)
            action.blockSignals(False)

        self._update_text()
        if emit and changed:
            self.selection_changed.emit(list(self._selection))

    # --- Presentation ----------------------------------------------------

    def _update_text(self):
        labels = [s.label for s in self._specs if s.key in self._selection]
        text = ", ".join(labels) if labels else NONE_LABEL
        self.setText(f"{self._prefix}{text}" if self._prefix else text)
        self.setToolTip(self.text())

    def set_available(self, keys):
        """Grey out every series not in ``keys``."""
        allowed = set(keys)
        for key, action in self._actions.items():
            action.setEnabled(key in allowed)
