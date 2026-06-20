import pytest
import json
import numpy as np

from ui.LiveMultiPlotWidget import LiveMultiPlotWidget


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


def test_clear_annotations(widget, mocker):
    """
    Business Logic: Ensures that clearing annotations empties the memory array
    and invokes the UI removal method for each item.
    """
    # Setup mock UI plots and mock annotation markers using pytest's mocker
    mock_plot_1 = mocker.MagicMock()
    mock_plot_2 = mocker.MagicMock()
    mock_marker_1 = mocker.MagicMock()
    mock_marker_2 = mocker.MagicMock()

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


def test_load_targets_from_path(widget, mocker):
    """
    Business Logic: Verifies that parsing a JSON target file correctly updates
    the internal audioFeatureExtractor configuration and triggers a recalculation.
    """
    # Setup a fake JSON payload representing the exported targets
    mock_json_data = {
        "targets": [
            {"name": "F1_Pitch", "enabled": True, "min": 250.0, "max": 450.0}
        ]
    }

    # Mock 'open' to simulate reading a file, and mock the UI update method
    mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_json_data)))
    mock_update_plots = mocker.patch.object(widget, 'update_plots')

    # Act
    widget.load_targets_from_path("dummy_path.json")

    # Assert
    # Query using the updated config API returning (min, max, enabled)
    target_config = widget.audioFeatureExtractor.target_config
    bounds = target_config.get_bounds("F1_Pitch")

    assert bounds is not None, "F1_Pitch target was not loaded into the config!"

    min_val, max_val, is_enabled = bounds
    assert min_val == 250.0
    assert max_val == 450.0
    assert is_enabled is True

    # Ensure recalculate_size and update_plots were triggered
    widget.audioFeatureExtractor.recalculate_size.assert_called_once()
    mock_update_plots.assert_called_once()


def test_append_live_data(widget, mocker):
    """
    Business Logic: Ensures that incoming live stream packets correctly append
    their numpy values into the master data containers.
    """
    # 1. Setup dynamic mock plot controllers
    mock_controller = mocker.MagicMock()
    mock_controller.curves.keys.return_value = ['Curve1']
    widget.plot_controllers = {'TestPlot': mock_controller}

    # 2. Setup mock layout structure for update_playhead
    mock_playhead = mocker.MagicMock()
    widget.plots = {
        'TestPlot': {
            'playhead': mock_playhead,
            'plot': mocker.MagicMock()
        }
    }

    # Setup mock data containers inside the widget's results
    mock_data_container = mocker.MagicMock()
    widget.analysedAudioFeatures.TestMetric = mock_data_container

    # Create a mock incoming FeatureSnapshot packet
    mock_snapshot = mocker.MagicMock()
    mock_snapshot.time = 0.2
    mock_snapshot.TestMetric = 15.0

    # Mock update_plots so we don't trigger pyqtgraph rendering logic during the test
    mocker.patch.object(widget, 'update_plots')

    # Act
    widget.append_live_data(mock_snapshot)

    # Assert
    mock_controller.append_curve_point.assert_called_once_with(
        curve_name='Curve1',
        snapshot=mock_snapshot,
        audio_features_ctx=widget.analysedAudioFeatures
    )


# Create dummy classes to mimic your data structures for `isinstance` checks
class DummyTimeSeries:
    pass


class DummyBandwidthTimeSeries(DummyTimeSeries):
    pass


def test_update_plots_skips_invalid_data(widget, mocker):
    """
    Ensures the method safely skips features that don't exist, are missing x/y arrays,
    or have mismatched x/y lengths.
    """
    mock_controller = mocker.MagicMock()
    mock_controller.curves.items.return_value = [
        ('MissingFeature', {'analysisResult': 'DoesNotExist'}),
        ('MissingXY', {'analysisResult': 'BadDataFeature'}),
        ('MismatchLength', {'analysisResult': 'MismatchFeature'})
    ]

    widget.plot_controllers = {'TestPlot': mock_controller}

    # 1. Missing XY
    bad_data = DummyTimeSeries()
    widget.analysedAudioFeatures.BadDataFeature = bad_data

    # 2. Mismatched Lengths
    mismatch_data = DummyTimeSeries()
    mismatch_data.x = np.array([1.0, 2.0])
    mismatch_data.y = np.array([10.0])  # Only 1 Y value
    widget.analysedAudioFeatures.MismatchFeature = mismatch_data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert - set_curve_data should never have been triggered because paths should 'continue'
    mock_controller.set_curve_data.assert_not_called()


def test_update_plots_standard_drawing(widget, mocker):
    """
    Tests the default path where standard solid colors are drawn without bandwidth or Z-axis mapping.
    """
    mock_controller = mocker.MagicMock()
    mock_controller.curves.items.return_value = [
        ('StandardCurve', {'analysisResult': 'F0'})
    ]
    widget.plot_controllers = {'TestPlot': mock_controller}

    data = DummyTimeSeries()
    data.x = np.array([0.1, 0.2])
    data.y = np.array([100.0, 110.0])
    widget.analysedAudioFeatures.F0 = data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert
    mock_controller.set_curve_data.assert_called_once_with(
        curve_name='StandardCurve',
        x=data.x,
        y=data.y,
        data_container=data,
        audio_features_ctx=widget.analysedAudioFeatures
    )


def test_update_plots_bandwidth_and_gaps(widget, mocker):
    """
    Tests the upper/lower bandwidth calculations path.
    """
    mock_controller = mocker.MagicMock()
    mock_controller.curves.items.return_value = [
        ('BWCurve', {'analysisResult': 'F1', 'has_bw': True})
    ]
    widget.plot_controllers = {'TestPlot': mock_controller}

    data = DummyBandwidthTimeSeries()
    data.x = np.array([0.1, 0.2, 0.5])
    data.y = np.array([10.0, 10.0, 10.0])
    data.BW = np.array([4.0, 4.0, 4.0])
    widget.analysedAudioFeatures.F1 = data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert
    mock_controller.set_curve_data.assert_called_once_with(
        curve_name='BWCurve',
        x=data.x,
        y=data.y,
        data_container=data,
        audio_features_ctx=widget.analysedAudioFeatures
    )


def test_update_plots_dynamic_colors(widget, mocker):
    """
    Verifies that target data maps out onto dynamic colors loop metrics.
    """
    mock_controller = mocker.MagicMock()
    mock_controller.curves.items.return_value = [
        ('ColorCurve', {'analysisResult': 'F2', 'colorSource': 'Weight'})
    ]
    widget.plot_controllers = {'TestPlot': mock_controller}

    data = DummyTimeSeries()
    data.x = np.array([1.0, 2.0, 3.0])
    data.y = np.array([100, 200, 300])
    widget.analysedAudioFeatures.F2 = data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert
    mock_controller.set_curve_data.assert_called_once_with(
        curve_name='ColorCurve',
        x=data.x,
        y=data.y,
        data_container=data,
        audio_features_ctx=widget.analysedAudioFeatures
    )


def test_update_plots_multiple_plots_and_curves(widget, mocker):
    """
    Business Logic: Verifies that the nested loops iterate through multiple plots,
    and multiple curves per plot, applying the correct rendering logic to each.
    """
    mock_controller_1 = mocker.MagicMock()
    mock_controller_1.curves.items.return_value = [
        ('Standard_A', {'analysisResult': 'Feature_A'}),
        ('Bandwidth_A', {'analysisResult': 'Feature_B', 'has_bw': True})
    ]

    mock_controller_2 = mocker.MagicMock()
    mock_controller_2.curves.items.return_value = [
        ('Standard_B', {'analysisResult': 'Feature_C'}),
        ('Color_B', {'analysisResult': 'Feature_D', 'colorSource': 'Weight'})
    ]

    widget.plot_controllers = {
        'Plot_One': mock_controller_1,
        'Plot_Two': mock_controller_2
    }

    # Setup Data Containers
    data_a = DummyTimeSeries(); data_a.x = np.array([1.0]); data_a.y = np.array([10.0])
    data_b = DummyBandwidthTimeSeries(); data_b.x = np.array([2.0]); data_b.y = np.array([20.0]); data_b.BW = np.array([4.0])
    data_c = DummyTimeSeries(); data_c.x = np.array([3.0]); data_c.y = np.array([30.0])
    data_d = DummyTimeSeries(); data_d.x = np.array([4.0]); data_d.y = np.array([40.0])

    widget.analysedAudioFeatures.Feature_A = data_a
    widget.analysedAudioFeatures.Feature_B = data_b
    widget.analysedAudioFeatures.Feature_C = data_c
    widget.analysedAudioFeatures.Feature_D = data_d

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert calls onto controller delegation patterns
    mock_controller_1.set_curve_data.assert_any_call(
        curve_name='Standard_A', x=data_a.x, y=data_a.y, data_container=data_a, audio_features_ctx=widget.analysedAudioFeatures
    )
    mock_controller_1.set_curve_data.assert_any_call(
        curve_name='Bandwidth_A', x=data_b.x, y=data_b.y, data_container=data_b, audio_features_ctx=widget.analysedAudioFeatures
    )
    mock_controller_2.set_curve_data.assert_any_call(
        curve_name='Standard_B', x=data_c.x, y=data_c.y, data_container=data_c, audio_features_ctx=widget.analysedAudioFeatures
    )
    mock_controller_2.set_curve_data.assert_any_call(
        curve_name='Color_B', x=data_d.x, y=data_d.y, data_container=data_d, audio_features_ctx=widget.analysedAudioFeatures
    )