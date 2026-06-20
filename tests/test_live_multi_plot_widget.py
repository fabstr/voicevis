import pytest
import json
import numpy as np
import time

from ui.LiveMultiPlotWidget import LiveMultiPlotWidget


@pytest.fixture
def patch_dependencies(monkeypatch):
    """Uses pytest's native monkeypatch to isolate the widget from
    hardware dependencies and local file system specs.
    """
    # 1. Mock the UI Spec configurations dictionary completely
    mock_spec = {
        "Pitch": {
            "title": "Vocal Pitch",
            "curves": {"f0": {"analysisResult": "pitch_series", "colour": "r", "size": 3}},
            "stretch": 1
        }
    }

    # Try to apply specs to all likely import pathways
    try:
        monkeypatch.setattr("ui.LiveMultiPlotWidget.spec", mock_spec)
    except Exception:
        pass
    try:
        monkeypatch.setattr("src.ui.LiveMultiPlotWidget.spec", mock_spec)
    except Exception:
        pass

    monkeypatch.setattr("PlotsSpec.spec", mock_spec)

    # 2. BULLETPROOF FIX: Patch the PyQt6 classes directly at the module where they are imported
    class DummyAudioDevice:
        pass

    class DummyAudioSource:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *args):
            pass

        def stop(self):
            pass

    # ---> CHANGED HERE <---
    # Patch the local namespace of LiveMultiPlotWidget, not the PyQt6 module.
    monkeypatch.setattr("ui.LiveMultiPlotWidget.QMediaDevices.defaultAudioInput", lambda: DummyAudioDevice())
    monkeypatch.setattr("ui.LiveMultiPlotWidget.QAudioSource", DummyAudioSource)

# --- FIX: Added missing widget fixture that safely initializes the Qt environment ---
@pytest.fixture
def widget(qtbot, patch_dependencies):
    """Initializes the live widget within the Qt event loop context."""
    live_widget = LiveMultiPlotWidget()
    qtbot.addWidget(live_widget)
    return live_widget


# --- TESTS ---

def test_playback_state_toggles(widget):
    """Business Logic: Ensures that stopping playback resets the correct
    boolean states and halts the application timers.
    """
    widget.is_playing = True
    widget.timer.start()

    # Act
    widget.stop_playback()

    # Assert
    assert widget.is_playing is False
    assert not widget.timer.isActive()


def test_clear_annotations(widget, mocker):
    """Business Logic: Ensures that clearing annotations empties the memory array
    and invokes the UI removal method via the new plot_controllers dictionary.
    """
    # --- FIX: Mock PlotControllers instead of the legacy self.plots dictionary ---
    mock_controller_1 = mocker.MagicMock()
    mock_controller_2 = mocker.MagicMock()
    mock_marker_1 = mocker.MagicMock()
    mock_marker_2 = mocker.MagicMock()

    widget.plot_controllers = {
        'Plot1': mock_controller_1,
        'Plot2': mock_controller_2
    }

    widget.annotations = [
        {'marker': mock_marker_1, 'plot': 'Plot1'},
        {'marker': mock_marker_2, 'plot': 'Plot2'}
    ]

    # Act
    widget.clear_annotations()

    # Assert
    assert len(widget.annotations) == 0
    mock_controller_1.widget.removeItem.assert_called_once_with(mock_marker_1)
    mock_controller_2.widget.removeItem.assert_called_once_with(mock_marker_2)


def test_load_targets_from_path(widget, mocker):
    """Business Logic: Verifies that parsing a JSON target file correctly updates
    the internal audioFeatureExtractor configuration and triggers a recalculation.
    """
    mock_json_data = {
        "targets": [
            {"name": "F1_Pitch", "enabled": True, "min": 250.0, "max": 450.0},
            {"name": "F2_Pitch", "enabled": True, "min": 250.0, "max": 450.0},
            {"name": "F3_Pitch", "enabled": True, "min": 250.0, "max": 450.0}
        ]
    }

    mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_json_data)))

    # --- FIX: audioFeatureExtractor is a real instance, spy on recalculate_size instead of asserting on an unmocked call ---
    spy_recalc = mocker.spy(widget.audioFeatureExtractor, 'recalculate_size')
    mock_update_plots = mocker.patch.object(widget, 'update_plots')

    # Act
    widget.load_targets_from_path("dummy_path.json")

    # Assert
    target_config = widget.audioFeatureExtractor.target_config
    bounds = target_config.get_bounds("F1_Pitch")

    assert bounds is not None, "F1_Pitch target was not loaded into the config!"

    min_val, max_val, is_enabled = bounds
    assert min_val == 250.0
    assert max_val == 450.0
    assert is_enabled is True

    spy_recalc.assert_called_once()