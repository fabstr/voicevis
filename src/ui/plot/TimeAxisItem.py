import pyqtgraph as pg

class TimeAxisItem(pg.AxisItem):
    """Custom AxisItem to format raw seconds into mm:ss.xxx string format."""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            val = max(0.0, float(v))
            minutes = int(val // 60)
            seconds = val % 60
            strings.append(f"{minutes:02d}:{seconds:06.2f}")
        return strings