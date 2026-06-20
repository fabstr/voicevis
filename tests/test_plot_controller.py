import pytest
from PyQt6 import QtWidgets
import pyqtgraph as pg
from ui.PlotController import PlotController  # Adjust import based on your folder structure

# A minimal spec fixture to mock what PlotController expects
@pytest.fixture
def mock_plot_spec():
    return {
        'title': 'Test Plot',
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'Test Curve': {
                'analysisResult': 'test_result',
                'colour': 'r',    # --- FIX: Added required color key ---
                'size': 3         # --- FIX: Added required size key ---
            }
        },
        'y_min': 0,
        'y_max': 100
    }

def dummy_callback(event, widget, title):
    pass

def test_plot_controller_initialization(qtbot, mock_plot_spec):
    """Verifies that the controller initializes components correctly."""
    controller = PlotController("TestPlot", mock_plot_spec, dummy_callback)
    qtbot.addWidget(controller.widget)

    assert isinstance(controller.widget, pg.PlotWidget)
    assert isinstance(controller.playhead, pg.InfiniteLine)
    # The playhead should default to 0 on initialization
    assert controller.playhead.value() == 0

def test_set_playhead_value(qtbot, mock_plot_spec):
    """Tests if the setter correctly updates the infinite line's position."""
    controller = PlotController("TestPlot", mock_plot_spec, dummy_callback)
    qtbot.addWidget(controller.widget)

    # Move playhead to 2.5 seconds
    target_time = 2.5
    controller.set_playhead_value(target_time)

    # Assert that the underlying pyqtgraph item moved to the correct coordinate
    assert controller.playhead.value() == target_time

def test_set_plot_visible(qtbot, mock_plot_spec):
    """Tests the widget visibility toggles."""
    controller = PlotController("TestPlot", mock_plot_spec, dummy_callback)
    qtbot.addWidget(controller.widget)

    controller.set_plot_visible(False)
    assert controller.widget.isVisible() is False

    controller.set_plot_visible(True)
    assert controller.widget.isVisible() is True