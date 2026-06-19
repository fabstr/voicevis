import pytest
import json
import numpy as np
from unittest.mock import MagicMock, patch, mock_open

from ui.LiveMultiPlotWidget import LiveMultiPlotWidget


# --- FIXTURES ---

@pytest.fixture
def mock_dependencies():
    """
    Mocks out the hardware-level audio sources, external threads, and
    bypasses the UI plot generation by providing an empty spec.
    """
    with patch('ui.LiveMultiPlotWidget.QMediaDevices'), \
         patch('ui.LiveMultiPlotWidget.QAudioSource'), \
         patch('ui.LiveMultiPlotWidget.AudioFeatureExtractor'), \
         patch('ui.LiveMultiPlotWidget.RealTimeAnalysisWorker'), \
         patch('ui.LiveMultiPlotWidget.spec', {}):  # <-- Set spec to empty dict
        yield


@pytest.fixture
def widget(qtbot, mock_dependencies):
    """
    Uses pytest-qt's qtbot to safely initialize the PyQt widget.
    """
    w = LiveMultiPlotWidget()
    qtbot.addWidget(w)
    return w


# --- TESTS ---

def test_playback_state_toggles(widget):
    """
    Business Logic: Ensures that stopping playback resets the correct
    boolean states and halts the application timers.
    """
    # Force a playing state
    widget.is_playing = True
    widget.timer.start()

    # Act
    widget.stop_playback()

    # Assert
    assert widget.is_playing is False
    assert not widget.timer.isActive()


def test_clear_annotations(widget):
    """
    Business Logic: Ensures that clearing annotations empties the memory array
    and invokes the UI removal method for each item.
    """
    # Setup mock UI plots and mock annotation markers
    mock_plot_1 = MagicMock()
    mock_plot_2 = MagicMock()
    mock_marker_1 = MagicMock()
    mock_marker_2 = MagicMock()

    widget.plots = {
        'Plot1': {'plot': mock_plot_1},
        'Plot2': {'plot': mock_plot_2}
    }

    widget.annotations = [
        {'marker': mock_marker_1, 'plot': 'Plot1'},
        {'marker': mock_marker_2, 'plot': 'Plot2'}
    ]

    # Act
    widget.clear_annotations()

    # Assert
    assert len(widget.annotations) == 0
    mock_plot_1.removeItem.assert_called_once_with(mock_marker_1)
    mock_plot_2.removeItem.assert_called_once_with(mock_marker_2)


def test_load_targets_from_path(widget):
    """
    Business Logic: Verifies that parsing a JSON target file correctly updates
    the internal audioFeatureExtractor configuration and triggers a recalculation.
    """
    # Setup a fake JSON payload representing the exported targets
    mock_json_data = {
        "F1_Pitch": {
            "F1_Pitch": {"enabled": True, "min": 250.0, "max": 450.0}
        }
    }

    # Mock 'open' to simulate reading a file, and mock the UI update methods
    with patch('builtins.open', mock_open(read_data=json.dumps(mock_json_data))), \
            patch.object(widget, 'update_plots') as mock_update_plots:
        # Act
        widget._load_targets_from_path("dummy_path.json")

        # Assert
        assert widget.audioFeatureExtractor.target_config.f1_pitch_min == 250.0
        assert widget.audioFeatureExtractor.target_config.f1_pitch_max == 450.0

        # Ensure recalculate_size and update_plots were triggered
        widget.audioFeatureExtractor.recalculate_size.assert_called_once()
        mock_update_plots.assert_called_once()


def test_append_live_data(widget):
    """
    Business Logic: Ensures that incoming live stream packets correctly append
    their numpy values into the master data containers.
    """
    # Setup mock data containers inside the widget's results
    mock_data_container = MagicMock()
    mock_data_container.x = np.array([0.1])
    mock_data_container.y = np.array([10.0])

    widget.analysedAudioFeatures.TestMetric = mock_data_container

    # Setup the plot routing dictionary to look for 'TestMetric'
    widget.plots = {
        'TestPlot': {
            'curves': {
                'Curve1': {'analysisResult': 'TestMetric'}
            }
        }
    }

    # Create a mock incoming FeatureSnapshot packet
    mock_snapshot = MagicMock()
    mock_snapshot.time = 0.2
    mock_snapshot.TestMetric = 15.0

    # Mock update_plots so we don't trigger pyqtgraph rendering logic during the test
    with patch.object(widget, 'update_plots'):
        # Act
        widget.append_live_data(mock_snapshot)

        # Assert
        assert len(mock_data_container.x) == 2
        assert mock_data_container.y[-1] == 15.0