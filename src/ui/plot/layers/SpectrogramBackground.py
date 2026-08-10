"""The spectrogram drawn as a coloured background behind a time plot.

This capability was lost when the old monolithic controller was split up: the
plot spec still advertised ``is_spectrogram`` but nothing created an
``ImageItem`` any more, so selecting the spectrogram fed a scatter two arrays of
unrelated lengths.

The image is drawn in true Hz on the Y axis so it lines up with formant and
pitch tracks rather than being stretched to fill whatever range the plot
happens to have. Rows outside the visible range are dropped before upload --
at nperseg=4096/nfft=8192 the matrix is 4097 rows by ~43 columns per second,
so a few minutes of audio is hundreds of megabytes in float64 if left whole.
"""

import time

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore

from ui.plot.ColourMapping import viridis

#: Below the target bands, which are at -20.
Z_VALUE = -30
#: Percentile used as the black point, so a few loud frames cannot wash the image out.
FLOOR_PERCENTILE = 5
#: Minimum seconds between rebuilds while recording.
RECORDING_THROTTLE = 0.2


class SpectrogramBackground:
    """A viridis image behind one plot's curves."""

    def __init__(self, plot_item):
        self.plot_item = plot_item
        self.image = pg.ImageItem()
        # Set explicitly rather than relying on the global imageAxisOrder config.
        self.image.setOpts(axisOrder='col-major')
        self.image.setColorMap(viridis())
        self.image.setZValue(Z_VALUE)
        self.image.setVisible(False)

        self._attached = False
        self._visible = False
        self._seen_revision = -1
        self._seen_range = None
        self._last_rebuild = 0.0

    # --- Visibility ------------------------------------------------------

    @property
    def visible(self) -> bool:
        return self._visible

    def set_visible(self, visible: bool):
        self._visible = bool(visible)

        if self._visible and not self._attached:
            self.plot_item.addItem(self.image)
            self._attached = True
        elif not self._visible and self._attached:
            self.plot_item.removeItem(self.image)
            self._attached = False

        self.image.setVisible(self._visible)
        if not self._visible:
            self._seen_revision = -1

    def detach(self):
        self.set_visible(False)

    # --- Drawing ---------------------------------------------------------

    def refresh(self, hub, freq_range, throttle=False):
        """Redraw if the data or the visible frequency range has changed."""
        if not self._visible:
            return

        if throttle and (time.monotonic() - self._last_rebuild) < RECORDING_THROTTLE:
            return

        if hub.revision == self._seen_revision and freq_range == self._seen_range:
            return

        spectrogram = hub.spectrogram()
        if spectrogram is None:
            self.image.clear()
            return

        self._seen_revision = hub.revision
        self._seen_range = freq_range
        self._last_rebuild = time.monotonic()
        self._draw(spectrogram, freq_range)

    def _draw(self, spectrogram, freq_range):
        times = np.asarray(spectrogram.x, dtype=float)
        frequencies = np.asarray(spectrogram.y, dtype=float)
        magnitudes = spectrogram.magnitude_db

        if times.size == 0 or frequencies.size == 0 or np.size(magnitudes) == 0:
            self.image.clear()
            return

        rows = min(len(frequencies), magnitudes.shape[0])
        columns = min(len(times), magnitudes.shape[1])
        frequencies, times = frequencies[:rows], times[:columns]
        magnitudes = magnitudes[:rows, :columns]

        low, high = freq_range if freq_range else (frequencies[0], frequencies[-1])
        keep = (frequencies >= low) & (frequencies <= high)
        if not keep.any():
            self.image.clear()
            return

        cropped = np.asarray(magnitudes[keep, :], dtype=np.float32)
        kept_frequencies = frequencies[keep]

        # Fix the levels explicitly. Letting them auto-scale makes the contrast
        # jump on every update, which is very visible while recording.
        finite = cropped[np.isfinite(cropped)]
        if finite.size == 0:
            self.image.clear()
            return
        floor = float(np.percentile(finite, FLOOR_PERCENTILE))
        ceiling = float(np.max(finite))
        if ceiling <= floor:
            ceiling = floor + 1.0

        self.image.setImage(cropped.T, autoLevels=False)
        self.image.setLevels((floor, ceiling))
        self.image.setRect(self._bin_rect(times, kept_frequencies))

    @staticmethod
    def _bin_rect(times, frequencies) -> QtCore.QRectF:
        """The image's extent, offset by half a bin.

        Bin values name the centre of their cell, so the image starts half a
        bin before the first one. The pre-split code anchored the rect at the
        origin instead, shifting everything by half a bin on both axes.
        """
        dt = float(times[1] - times[0]) if len(times) > 1 else 1.0
        df = float(frequencies[1] - frequencies[0]) if len(frequencies) > 1 else 1.0

        left = float(times[0]) - dt / 2.0
        bottom = float(frequencies[0]) - df / 2.0
        width = float(times[-1] - times[0]) + dt
        height = float(frequencies[-1] - frequencies[0]) + df
        return QtCore.QRectF(left, bottom, width, height)
