import numpy as np
import pyqtgraph as pg

class FrequencyAxisItem(pg.AxisItem):
    """Custom AxisItem to force exact X-tick positions and labels for frequency plots."""

    def __init__(self, *args, **kwargs):
        # Safely extract our custom variables before initializing the parent AxisItem
        self.x_ticks = kwargs.pop('x_ticks', None)
        self.is_log_x = kwargs.pop('is_log_x', False)

        super().__init__(*args, **kwargs)

        # Force the axis to allocate 35 pixels of vertical space.
        # This prevents the axis from collapsing to a height of 0 during initialization.
        self.setHeight(35)

    def tickValues(self, minVal, maxVal, size):
        # Fallback to default pyqtgraph behavior if no custom ticks are provided
        if not self.x_ticks:
            return super().tickValues(minVal, maxVal, size)

        # Map the configured tick frequencies to their plot positions
        positions = [np.log10(v) if self.is_log_x else v for v in self.x_ticks]

        # PyQtGraph expects a list of tuples: [(level, [positions]), ...]
        # Using Level 0 designates these as major ticks.
        return [(0, positions)]

    def tickStrings(self, values, scale, spacing):
        if not self.x_ticks:
            return super().tickStrings(values, scale, spacing)

        strings = []
        for v in values:
            # Reverse the log mapping to get the original raw frequency value
            val = (10 ** v) if self.is_log_x else v

            # Snap to the nearest predefined tick to prevent floating-point inaccuracies
            closest_tick = min(self.x_ticks, key=lambda x: abs(x - val))

            # Format nicely for a cleaner UI (e.g., 1000 -> 1k, 10000 -> 10k)
            if closest_tick >= 1000:
                strings.append(f"{closest_tick // 1000}k")
            else:
                strings.append(str(closest_tick))

        return strings