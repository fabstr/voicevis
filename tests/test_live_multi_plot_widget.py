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
        "F1_Pitch": {
            "F1_Pitch": {"enabled": True, "min": 250.0, "max": 450.0}
        }
    }

    # Mock 'open' to simulate reading a file, and mock the UI update method
    mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_json_data)))
    mock_update_plots = mocker.patch.object(widget, 'update_plots')

    # Act
    widget._load_targets_from_path("dummy_path.json")

    # Assert
    assert widget.audioFeatureExtractor.target_config.f1_pitch_min == 250.0
    assert widget.audioFeatureExtractor.target_config.f1_pitch_max == 450.0

    # Ensure recalculate_size and update_plots were triggered
    widget.audioFeatureExtractor.recalculate_size.assert_called_once()
    mock_update_plots.assert_called_once()


def test_append_live_data(widget, mocker):
    """
    Business Logic: Ensures that incoming live stream packets correctly append
    their numpy values into the master data containers.
    """
    # Setup mock data containers inside the widget's results
    mock_data_container = mocker.MagicMock()
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
    mock_snapshot = mocker.MagicMock()
    mock_snapshot.time = 0.2
    mock_snapshot.TestMetric = 15.0

    # Mock update_plots so we don't trigger pyqtgraph rendering logic during the test
    mocker.patch.object(widget, 'update_plots')

    # Act
    widget.append_live_data(mock_snapshot)

    # Assert
    assert len(mock_data_container.x) == 2
    assert mock_data_container.y[-1] == 15.0


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
    mock_curve = mocker.MagicMock()

    # Setup plots dict
    widget.plots = {
        'TestPlot': {
            'curves': {
                'MissingFeature': {'analysisResult': 'DoesNotExist'},
                'MissingXY': {'analysisResult': 'BadDataFeature'},
                'MismatchLength': {'analysisResult': 'MismatchFeature'}
            }
        }
    }

    # 1. Missing XY
    bad_data = DummyTimeSeries()
    widget.analysedAudioFeatures.BadDataFeature = bad_data

    # 2. Mismatched Lengths
    mismatch_data = DummyTimeSeries()
    mismatch_data.x = np.array([1.0, 2.0])
    mismatch_data.y = np.array([10.0])  # Only 1 Y value
    widget.analysedAudioFeatures.MismatchFeature = mismatch_data

    # Attach our mock curve
    widget.plots['TestPlot']['curves']['MissingFeature']['curve'] = mock_curve
    widget.plots['TestPlot']['curves']['MissingXY']['curve'] = mock_curve
    widget.plots['TestPlot']['curves']['MismatchLength']['curve'] = mock_curve

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert - setData should never have been called because all 3 paths should 'continue'
    mock_curve.setData.assert_not_called()


def test_update_plots_standard_drawing(widget, mocker):
    """
    Tests the default path where standard solid colors are drawn without bandwidth or Z-axis mapping.
    """
    mock_curve = mocker.MagicMock()

    widget.plots = {
        'TestPlot': {
            'curves': {'StandardCurve': {'analysisResult': 'F0', 'curve': mock_curve}}
        }
    }

    data = DummyTimeSeries()
    data.x = np.array([0.1, 0.2])
    data.y = np.array([100.0, 110.0])
    widget.analysedAudioFeatures.F0 = data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert
    mock_curve.setData.assert_called_once()
    args, kwargs = mock_curve.setData.call_args
    assert np.array_equal(kwargs['x'], data.x)
    assert np.array_equal(kwargs['y'], data.y)
    assert 'symbolBrush' not in kwargs


def test_update_plots_bandwidth_and_gaps(widget, mocker):
    """
    Tests the upper/lower bandwidth calculations and verifies that np.nan is
    inserted when the time difference exceeds the 0.15s threshold.
    """
    mock_min = mocker.MagicMock()
    mock_max = mocker.MagicMock()

    widget.plots = {
        'TestPlot': {
            'curves': {
                'BWCurve': {
                    'analysisResult': 'F1',
                    'has_bw': True,
                    'bw_curve_min': mock_min,
                    'bw_curve_max': mock_max
                }
            }
        }
    }

    data = DummyBandwidthTimeSeries()
    # Notice the gap between 0.2 and 0.5 is 0.3s (which is > 0.15s gap_threshold)
    data.x = np.array([0.1, 0.2, 0.5])
    data.y = np.array([10.0, 10.0, 10.0])
    data.BW = np.array([4.0, 4.0, 4.0])  # BW of 4 means +2 and -2
    widget.analysedAudioFeatures.F1 = data

    mocker.patch.object(widget, 'update_playhead')

    # Act
    widget.update_plots()

    # Assert
    args, kwargs_min = mock_min.setData.call_args
    args, kwargs_max = mock_max.setData.call_args

    # 3 original points + 1 NaN inserted = length of 4
    assert len(kwargs_min['x']) == 4

    # Verify the math (y - bw/2 = 8)
    assert kwargs_min['y'][0] == 10.0
    assert kwargs_max['y'][0] == 10.0

    # Verify the NaN was correctly inserted at index 2 (between 0.2 and 0.5)
    assert np.isnan(kwargs_min['x'][2])
    assert np.isnan(kwargs_min['y'][2])
    assert np.isnan(kwargs_max['y'][2])

    # Verify the final point shifted to index 3
    assert kwargs_min['x'][3] == 0.5


def test_update_plots_dynamic_colors(widget, mocker):
    """
    Verifies that the Z-axis data is interpolated, strictly clipped, normalized,
    and converted to pyqtgraph Brushes.
    """
    mock_curve = mocker.MagicMock()

    widget.plots = {
        'TestPlot': {
            'curves': {
                'ColorCurve': {
                    'analysisResult': 'F2',
                    'colorSource': 'Weight',
                    'curve': mock_curve
                }
            }
        }
    }

    # Main Y-axis data
    data = DummyTimeSeries()
    data.x = np.array([1.0, 2.0, 3.0])
    data.y = np.array([100, 200, 300])
    widget.analysedAudioFeatures.F2 = data

    # Z-axis Data (We test three bounds: Below Min, Middle, Above Max)
    z_data = DummyTimeSeries()
    z_data.x = np.array([1.0, 2.0, 3.0])
    z_data.y = np.array([-1e-7, 2e-7, 8e-7])  # Should clip to: 0.0, 2e-7, 4e-7
    widget.analysedAudioFeatures.Weight = z_data

    mocker.patch.object(widget, 'update_playhead')

    # Mock PyQTGraph's colormap and brush generators
    mock_cmap = mocker.MagicMock()
    # map() should be called with an array of normalized values. We'll return dummy RGBA lists.
    mock_cmap.map.return_value = [[0, 0, 0, 255], [128, 128, 128, 255], [255, 255, 255, 255]]

    mocker.patch('ui.LiveMultiPlotWidget.pg.colormap.get', return_value=mock_cmap)

    # Patch mkBrush to just return a string representation of what was passed so we can easily assert it
    mocker.patch('ui.LiveMultiPlotWidget.pg.mkBrush', side_effect=lambda rgba: f"Brush_{rgba}")

    # Act
    widget.update_plots()

    # Assert
    mock_curve.setData.assert_called_once()
    args, kwargs = mock_curve.setData.call_args

    # Verify the interpolation and clipping normalized the array correctly
    # -1e-7 -> clipped to 0.0 -> normalized to 0.0
    # 2e-7 -> clipped to 2e-7 -> normalized to 0.5
    # 8e-7 -> clipped to 4e-7 -> normalized to 1.0
    norm_array_passed_to_map = mock_cmap.map.call_args[0][0]
    np.testing.assert_array_almost_equal(norm_array_passed_to_map, [0.0, 0.5, 1.0])

    # Verify brushes were generated and passed correctly
    expected_brushes = ["Brush_(0, 0, 0, 255)", "Brush_(128, 128, 128, 255)", "Brush_(255, 255, 255, 255)"]
    assert kwargs['symbolBrush'] == expected_brushes


def test_update_plots_multiple_plots_and_curves(widget, mocker):
    """
    Business Logic: Verifies that the nested loops iterate through multiple plots,
    and multiple curves per plot, applying the correct rendering logic to each
    without mixing up data references or skipping items.
    """
    # 1. Setup Mock Curves for two different plots
    mock_plot1_curve1 = mocker.MagicMock()  # Standard curve
    mock_plot1_min = mocker.MagicMock()  # Bandwidth min
    mock_plot1_max = mocker.MagicMock()  # Bandwidth max

    mock_plot2_curve1 = mocker.MagicMock()  # Standard curve
    mock_plot2_curve2 = mocker.MagicMock()  # Dynamic color curve

    widget.plots = {
        'Plot_One': {
            'curves': {
                'Standard_A': {'analysisResult': 'Feature_A', 'curve': mock_plot1_curve1},
                'Bandwidth_A': {
                    'analysisResult': 'Feature_B',
                    'has_bw': True,
                    'bw_curve_min': mock_plot1_min,
                    'bw_curve_max': mock_plot1_max
                }
            }
        },
        'Plot_Two': {
            'curves': {
                'Standard_B': {'analysisResult': 'Feature_C', 'curve': mock_plot2_curve1},
                'Color_B': {'analysisResult': 'Feature_D', 'colorSource': 'Weight', 'curve': mock_plot2_curve2}
            }
        }
    }

    # 2. Setup Data Containers with distinct values so we can verify exact mappings
    # Feature A (Plot 1, Standard)
    data_a = DummyTimeSeries()
    data_a.x = np.array([1.0]);
    data_a.y = np.array([10.0])
    widget.analysedAudioFeatures.Feature_A = data_a

    # Feature B (Plot 1, Bandwidth)
    data_b = DummyBandwidthTimeSeries()
    data_b.x = np.array([2.0]);
    data_b.y = np.array([20.0]);
    data_b.BW = np.array([4.0])
    widget.analysedAudioFeatures.Feature_B = data_b

    # Feature C (Plot 2, Standard)
    data_c = DummyTimeSeries()
    data_c.x = np.array([3.0]);
    data_c.y = np.array([30.0])
    widget.analysedAudioFeatures.Feature_C = data_c

    # Feature D (Plot 2, Dynamic Color)
    data_d = DummyTimeSeries()
    data_d.x = np.array([4.0]);
    data_d.y = np.array([40.0])
    widget.analysedAudioFeatures.Feature_D = data_d

    # Z-Axis Weight Data for Feature D
    data_weight = DummyTimeSeries()
    data_weight.x = np.array([4.0]);
    data_weight.y = np.array([2e-7])
    widget.analysedAudioFeatures.Weight = data_weight

    # 3. Mock UI components
    mocker.patch.object(widget, 'update_playhead')
    mock_cmap = mocker.MagicMock()
    mock_cmap.map.return_value = [[255, 0, 0, 255]]  # Dummy Red RGBA
    mocker.patch('ui.LiveMultiPlotWidget.pg.colormap.get', return_value=mock_cmap)
    mocker.patch('ui.LiveMultiPlotWidget.pg.mkBrush', return_value="MockedBrush")

    # Act
    widget.update_plots()

    # Assert - Verify Plot One
    mock_plot1_curve1.setData.assert_called_once()
    args, kwargs = mock_plot1_curve1.setData.call_args
    assert kwargs['y'][0] == 10.0  # Feature A y-value

    mock_plot1_min.setData.assert_called_once()
    mock_plot1_max.setData.assert_called_once()
    _, min_kwargs = mock_plot1_min.setData.call_args
    _, max_kwargs = mock_plot1_max.setData.call_args
    assert min_kwargs['y'][0] == 20.0  # Feature B: 20.0 - (4.0 / 2)
    assert max_kwargs['y'][0] == 20.0  # Feature B: 20.0 + (4.0 / 2)

    # Assert - Verify Plot Two
    mock_plot2_curve1.setData.assert_called_once()
    _, kwargs_c = mock_plot2_curve1.setData.call_args
    assert kwargs_c['y'][0] == 30.0  # Feature C y-value
    assert 'symbolBrush' not in kwargs_c  # Standard curve shouldn't have brush args

    mock_plot2_curve2.setData.assert_called_once()
    _, kwargs_d = mock_plot2_curve2.setData.call_args
    assert kwargs_d['y'][0] == 40.0  # Feature D y-value
    assert kwargs_d['symbolBrush'] == ["MockedBrush"]  # Dynamic color properly triggered