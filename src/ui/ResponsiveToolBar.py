"""A toolbar whose groups fold into dropdowns when the window gets narrow.

Each group is a row of related controls. While there is room they sit inline;
when there is not, the least important group folds into a single button whose
menu holds the very same widgets -- so nothing is duplicated and no state has to
be kept in sync.
"""

import logging

import qtawesome as qta
from PyQt6 import QtCore, QtWidgets

#: Space between groups, and around the row.
GROUP_SPACING = 10
MARGIN = 4


class ToolbarGroup(QtWidgets.QWidget):
    """Related controls that can collapse into one dropdown button."""

    def __init__(self, title, icon_name=None, collapsible=True, parent=None):
        super().__init__(parent)
        self.title = title
        self.icon_name = icon_name
        self.collapsible = collapsible
        self._collapsed = False
        self._action = None

        # Everything lives on `content`, which moves wholesale between the
        # toolbar and the dropdown. Moving the container rather than each
        # control keeps the widgets -- and their signal connections -- intact.
        self.content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QHBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)

        self.button = QtWidgets.QToolButton()
        self.button.setToolTip(title)
        self.button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(QtWidgets.QMenu(self.button))
        self.button.hide()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.content)
        layout.addWidget(self.button)

        # A group takes the width it asks for and no more. A child that wants to
        # expand -- a QLineEdit or a slider -- otherwise drags the row's spare
        # space into the group, where it lands on the label and leaves it
        # stranded away from the field it names. Slack belongs to the stretches.
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum,
                           QtWidgets.QSizePolicy.Policy.Preferred)

    # --- Contents --------------------------------------------------------

    def add(self, *widgets):
        for widget in widgets:
            self.content_layout.addWidget(widget)
        return self

    def add_spacing(self, amount):
        self.content_layout.addSpacing(amount)
        return self

    # --- Collapsing ------------------------------------------------------

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        collapsed = bool(collapsed) and self.collapsible
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed

        if collapsed:
            self._action = QtWidgets.QWidgetAction(self.button.menu())
            self._action.setDefaultWidget(self.content)
            self.button.menu().addAction(self._action)
            self.button.show()
        else:
            self.button.menu().removeAction(self._action)
            self._action.releaseWidget(self.content)
            self._action = None
            self.layout().insertWidget(0, self.content)
            self.content.show()
            self.button.hide()

        self.updateGeometry()

    # --- Measurement -----------------------------------------------------

    def expanded_width(self) -> int:
        """What this group needs inline, whether or not it is collapsed now.

        A hidden group needs nothing: it is out of the row entirely, and its
        content keeps a size hint that would otherwise reserve room for a group
        nobody can see.
        """
        if self.isHidden():
            return 0
        return self.content.sizeHint().width()

    def collapsed_width(self) -> int:
        if self.isHidden():
            return 0
        return self.button.sizeHint().width() if self.collapsible else self.expanded_width()

    # --- Appearance ------------------------------------------------------

    def apply_icon(self, colour):
        if not self.icon_name:
            self.button.setText(self.title)
            return
        try:
            self.button.setIcon(qta.icon(self.icon_name, color=colour))
            self.button.setIconSize(QtCore.QSize(18, 18))
        except Exception as exc:                      # unknown icon name
            logging.debug("No icon %r for %r: %s", self.icon_name, self.title, exc)
            self.button.setText(self.title)


class ResponsiveToolBar(QtWidgets.QWidget):
    """Lays groups out in a row, collapsing them when the row will not fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._groups = []          # in the order they were added
        self._order = []           # collapse order: first to fold, first here
        self._relayouting = False

        # One row, as tall as its contents and no taller. Without this the
        # toolbar and the plot area both have a Preferred height and Qt hands
        # them a share each of any spare vertical space, so maximising the
        # window stretches the toolbar instead of the plots.
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                           QtWidgets.QSizePolicy.Policy.Fixed)

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self._layout.setSpacing(GROUP_SPACING)

    def add_group(self, group: ToolbarGroup, collapse_priority=None):
        """Add a group. Lower ``collapse_priority`` folds away sooner."""
        self._groups.append(group)
        self._layout.addWidget(group)
        if group.collapsible:
            self._order.append((collapse_priority if collapse_priority is not None
                                else len(self._groups), group))
            self._order.sort(key=lambda pair: pair[0])
        return group

    def add_stretch(self):
        self._layout.addStretch()

    def apply_icons(self, colour):
        for group in self._groups:
            group.apply_icon(colour)

    # --- Fitting ---------------------------------------------------------

    def refit(self):
        """Fit the row again after a group's contents changed width.

        Resizing the window is the usual trigger, but a control that appears or
        disappears -- the gain readout, which is only there while a gain is in
        force -- changes what has to fit without the toolbar being resized at
        all, and nothing else would notice.
        """
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self):
        if self._relayouting or not self._groups:
            return

        available = self.width() - 2 * MARGIN
        shown = [g for g in self._groups if not g.isHidden()]
        needed = sum(g.expanded_width() for g in shown)
        needed += GROUP_SPACING * max(0, len(shown) - 1)

        # Fold the least important groups away until the row fits.
        collapse = set()
        for _, group in self._order:
            if needed <= available:
                break
            needed -= group.expanded_width() - group.collapsed_width()
            collapse.add(group)

        wanted = {group: (group in collapse) for group in self._groups}
        if all(group.collapsed == state for group, state in wanted.items()):
            return

        self._relayouting = True
        try:
            for group, state in wanted.items():
                group.set_collapsed(state)
        finally:
            self._relayouting = False

    def sizeHint(self):
        hint = super().sizeHint()
        # Never demand the full expanded width: the point is to fit in less.
        shown = [g for g in self._groups if not g.isHidden()]
        smallest = sum(g.collapsed_width() for g in shown)
        smallest += GROUP_SPACING * max(0, len(shown) - 1) + 2 * MARGIN
        return QtCore.QSize(max(smallest, 1), hint.height())

    def minimumSizeHint(self):
        return self.sizeHint()
