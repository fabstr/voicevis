"""Undo and redo for everything that changes the recording.

States rather than commands: each entry is a copy of the whole audio buffer as
it was *before* an action. That costs memory but it is impossible to get wrong,
and it makes recording and clearing undoable on exactly the same footing as an
edit, without either of them having to describe how to reverse itself.

An entry carries the gains in force at the same moment. They are not audio, and
setting one is not an undoable action -- but a cut or a move takes them along
with the audio they cover, so restoring one state without the other would leave
a gain describing a stretch that is no longer there.
"""

import logging

from PyQt6 import QtCore
from PyQt6.QtCore import QByteArray

#: Most steps kept. Beyond this the oldest is dropped.
MAX_ENTRIES = 30

#: ...and a ceiling on the total, so a long recording cannot eat the machine.
#: 16-bit mono at 44.1 kHz is about 5 MB a minute.
MAX_BYTES = 256 * 1024 * 1024


class _Entry:
    __slots__ = ("audio", "audio_file", "label", "gains")

    def __init__(self, audio, audio_file, label, gains=None):
        self.audio = QByteArray(audio)      # a copy: the original keeps changing
        self.audio_file = audio_file
        self.label = label
        self.gains = gains

    @property
    def size(self) -> int:
        return self.audio.size()


class AudioHistory(QtCore.QObject):
    """A stack of states the recording can be put back to."""

    changed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo = []
        self._redo = []

    # --- Recording history -----------------------------------------------

    def capture(self, audio, audio_file=None, label="Edit", gains=None):
        """Remember the state before an action. Call this *before* changing it."""
        self._undo.append(_Entry(audio, audio_file, label, gains))
        self._redo.clear()
        self._trim()
        self.changed.emit()

    def reset(self, ):
        """Forget everything, e.g. when a different file is loaded."""
        if not self._undo and not self._redo:
            return
        self._undo.clear()
        self._redo.clear()
        self.changed.emit()

    # --- Stepping --------------------------------------------------------

    def undo(self, audio, audio_file=None, gains=None):
        """Return the previous state, or None. ``audio`` is the current one."""
        if not self._undo:
            return None
        entry = self._undo.pop()
        self._redo.append(_Entry(audio, audio_file, entry.label, gains))
        self.changed.emit()
        return entry

    def redo(self, audio, audio_file=None, gains=None):
        """Return the state undone most recently, or None."""
        if not self._redo:
            return None
        entry = self._redo.pop()
        self._undo.append(_Entry(audio, audio_file, entry.label, gains))
        self.changed.emit()
        return entry

    # --- State -----------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self):
        return self._undo[-1].label if self._undo else None

    @property
    def redo_label(self):
        return self._redo[-1].label if self._redo else None

    def depth(self):
        return len(self._undo), len(self._redo)

    # --- Housekeeping ----------------------------------------------------

    def _trim(self):
        while len(self._undo) > MAX_ENTRIES:
            dropped = self._undo.pop(0)
            logging.debug("Dropping the oldest undo step (%s)", dropped.label)

        total = sum(entry.size for entry in self._undo)
        while total > MAX_BYTES and len(self._undo) > 1:
            total -= self._undo.pop(0).size
