import math

import pyqtgraph as pg

MAX_DECIMALS = 3


class TimeAxisItem(pg.AxisItem):
    """Formats raw seconds as mm:ss, with as much precision as the zoom needs."""

    def tickStrings(self, values, scale, spacing):
        decimals = 0
        if spacing and spacing < 1:
            decimals = min(MAX_DECIMALS, max(1, int(math.ceil(-math.log10(spacing)))))

        # Two digits for the seconds, plus the point and its decimals.
        width = 2 + (decimals + 1 if decimals else 0)

        strings = []
        for value in values:
            seconds = max(0.0, float(value))
            strings.append(f"{int(seconds // 60):02d}:{seconds % 60:0{width}.{decimals}f}")
        return strings
