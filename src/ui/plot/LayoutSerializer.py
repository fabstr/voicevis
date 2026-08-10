"""Reading and writing plot-grid layouts.

Layout files describe which plots are in the grid and how big they are. Version
2 stores each cell's series selection; earlier versions stored the name of a
plot preset. Both are readable, so layouts saved by older builds -- including
the one auto-restored from QSettings -- keep working.
"""

from dataclasses import dataclass, field
from typing import List

from SeriesRegistry import DEFAULT_POINT_SIZE
from ui.plot.PlotConfig import PlotConfig

LAYOUT_VERSION = 2


@dataclass
class LayoutColumn:
    configs: List[PlotConfig] = field(default_factory=list)
    sizes: List[int] = field(default_factory=list)


@dataclass
class Layout:
    global_size: int = DEFAULT_POINT_SIZE
    main_splitter_sizes: List[int] = field(default_factory=list)
    columns: List[LayoutColumn] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(column.configs for column in self.columns)


def detect_version(data: dict) -> int:
    """1 for anything predating per-series configs, 2 for the current schema."""
    if data.get("version"):
        return int(data["version"])

    for column in data.get("columns", []):
        entries = column if isinstance(column, list) else column.get("plots", [])
        for entry in entries:
            if isinstance(entry, dict) and "x" in entry:
                return 2
    return 1


def load(data: dict, default_point_size: int = DEFAULT_POINT_SIZE) -> Layout:
    """Parse any layout format this app has ever written."""
    if not isinstance(data, dict) or "columns" not in data:
        raise ValueError("Invalid layout configuration format.")

    global_size = int(data.get("global_size", default_point_size) or default_point_size)
    layout = Layout(
        global_size=global_size,
        main_splitter_sizes=list(data.get("main_splitter_sizes", [])),
    )

    for column in data["columns"]:
        # The oldest format stored each column as a bare list of plot names.
        entries = column if isinstance(column, list) else column.get("plots", [])
        sizes = [] if isinstance(column, list) else list(column.get("sizes", []))
        layout.columns.append(LayoutColumn(
            configs=[PlotConfig.from_layout_entry(entry, global_size) for entry in entries],
            sizes=sizes,
        ))

    return layout


def dump(layout: Layout) -> dict:
    return {
        "version": LAYOUT_VERSION,
        "global_size": int(layout.global_size),
        "main_splitter_sizes": list(layout.main_splitter_sizes),
        "columns": [
            {
                "plots": [config.to_dict() for config in column.configs],
                "sizes": list(column.sizes),
            }
            for column in layout.columns
        ],
    }
