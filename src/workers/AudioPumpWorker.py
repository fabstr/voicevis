"""Drains the microphone on a thread of its own.

The pull used to be a ``QTimer`` on the GUI thread. Everything the plots do
while recording costs time in the number of frames analysed so far -- a
coloured scatter rebuilds one brush per point across the whole recording on
every redraw -- so once a redraw takes longer than a frame, the timer stops
firing on time and the microphone goes unread for as long as the grid is busy.

Monitoring loses those samples outright: Qt hands over a device in pull mode
and overruns it while nobody reads. Recording keeps them -- they are pushed
into a buffer of ours -- but they then reach the live analysis in one burst,
and a burst longer than its half-second window leaves a gap in the live
curves where the GUI thread was busy.

Reading here keeps the microphone drained at a steady rate whatever the GUI
thread is doing. The pump owns the read while it runs: it is started after the
audio source and stopped -- and waited for -- before it, so no two threads
ever hold the device at once.
"""

import logging

from PyQt6 import QtCore

#: How often the microphone is drained. Kept at the interval the GUI timer
#: used, because it also sets how often the analysis runs: a pass covers
#: whatever has arrived since the last one, so draining more often would buy
#: latency at the price of running openSMILE over its window more times a
#: second.
POLL_MILLISECONDS = 33


class AudioPumpWorker(QtCore.QThread):
    """Calls ``read`` every :data:`POLL_MILLISECONDS` until stopped."""

    def __init__(self, read):
        super().__init__()
        self._read = read
        self._is_running = True

    def run(self):
        while self._is_running:
            try:
                self._read()
            except Exception:
                # A failed read must not take the thread down with it: the
                # microphone would then stay unread for the rest of the take.
                logging.exception("Reading the microphone failed")
            self.msleep(POLL_MILLISECONDS)

    def stop(self):
        self._is_running = False
