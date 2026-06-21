import json
import pytest



def test_export_targets_successful(widget, mocker):
    """
    Business Logic: Ensures that the TargetConfig parameters are correctly
    serialized and exported to a JSON file format via the target config instance.
    """
    # 1. Update the widget's internal target_config state with known parameters
    from signal_processing.TargetConfig import TargetConfig
    widget.audioFeatureExtractor.target_config = TargetConfig(targets=[
        {"name": "f1_pitch", "min": 150.0, "max": 250.0, "enabled": True},
        {"name": "f2_pitch", "min": 800.0, "max": 1200.0, "enabled": False}
    ])

    # 2. Mock file dialog to simulate user selecting a save path
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getSaveFileName',
        return_value=('dummy_export.json', 'JSON Files (*.json)')
    )

    # 3. Mock file operations to capture the write execution
    mock_file = mocker.patch('builtins.open', mocker.mock_open())
    mock_json_dump = mocker.patch('json.dump')

    # Act
    widget.export_targets()

    # Assert
    mock_file.assert_called_once_with('dummy_export.json', 'w', encoding='utf-8')

    # Verify that the expected uniform data format was passed to json.dump
    expected_export_dict = {
        'targets': [
            {'name': 'f1_pitch', 'min': 150.0, 'max': 250.0, 'enabled': True},
            {'name': 'f2_pitch', 'min': 800.0, 'max': 1200.0, 'enabled': False}
        ]
    }

    mock_json_dump.assert_called_once()
    args, _ = mock_json_dump.call_args
    assert args[0] == expected_export_dict

def test_export_targets_cancelled(widget, mocker):
    """
    Business Logic: Ensures that if the user clicks "Cancel" on the save dialog,
    the application handles the empty path gracefully and does not attempt to write a file.
    """
    # Mock file dialog returning an empty string
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getSaveFileName',
        return_value=('', '')
    )

    mock_file = mocker.patch('builtins.open', mocker.mock_open())

    # Act
    widget.export_targets()

    # Assert
    mock_file.assert_not_called()


def test_import_targets_successful(widget, mocker):
    """
    Business Logic: Ensures that selecting a file from the import dialog correctly
    parses the JSON configuration and passes it to set_target_config.
    """
    # 1. Simulate the user selecting a file to open
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getOpenFileName',
        return_value=('dummy_import.json', 'JSON Files (*.json)')
    )

    # 2. Mock TargetConfig.from_json so it returns a dummy object instead of hitting the file system
    mock_config = mocker.MagicMock()
    mock_from_json = mocker.patch(
        'signal_processing.TargetConfig.TargetConfig.from_json',
        return_value=mock_config
    )

    # 3. Spy on or mock set_target_config to verify it receives the object
    mock_set_config = mocker.patch.object(widget, 'set_target_config')

    # Act
    widget.import_targets()

    # Assert
    # Verify from_json was called with our dummy path string
    mock_from_json.assert_called_once_with('dummy_import.json')
    # Verify the extracted configuration was forwarded to the widget's setter
    mock_set_config.assert_called_once_with(mock_config)


def test_import_targets_cancelled(widget, mocker):
    """
    Business Logic: Ensures that cancelling the import dialog halts execution
    before attempting to load any files.
    """
    # Simulate user cancelling the dialog
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getOpenFileName',
        return_value=('', '')
    )

    mock_loader = mocker.patch.object(widget, 'load_targets_from_path')

    # Act
    widget.import_targets()

    # Assert
    mock_loader.assert_not_called()

import json

def test_targets_propagate_to_feature_extractor(widget, mocker):
    """
    Business Logic: Ensures that when target settings are loaded, the specific
    min/max boundary limits are correctly parsed and assigned deep into the
    underlying AudioFeatureExtractor's target_config object, and a recalculation
    is triggered.
    """
    # 1. Setup a comprehensive fake JSON payload structured as a uniform list of target objects
    mock_json_data = {
        "targets": [
            {"name": "F1_Pitch", "enabled": True, "min": 300.0, "max": 600.0},
            {"name": "F2_Pitch", "enabled": True, "min": 1000.0, "max": 1500.0},
            {"name": "F3_Pitch", "enabled": False, "min": 2500.0, "max": 3000.0}
        ]
    }

    # Mock 'open' to simulate reading the file
    mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_json_data)))

    # Mock update_plots to prevent UI rendering logic from running
    mocker.patch.object(widget, 'update_plots')

    # Act
    widget.load_targets_from_path("dummy_path.json")

    # Assert - Reference the target config instance
    target_config = widget.audioFeatureExtractor.target_config

    # Verify propagation to the internal F1 limits
    f1_bounds = target_config.get_bounds("F1_Pitch")
    assert f1_bounds is not None
    assert f1_bounds[0] == 300.0
    assert f1_bounds[1] == 600.0
    assert f1_bounds[2] is True

    # Verify propagation to the internal F2 limits
    f2_bounds = target_config.get_bounds("F2_Pitch")
    assert f2_bounds is not None
    assert f2_bounds[0] == 1000.0
    assert f2_bounds[1] == 1500.0
    assert f2_bounds[2] is True

    # Verify propagation to the internal F3 limits
    f3_bounds = target_config.get_bounds("F3_Pitch")
    assert f3_bounds is not None
    assert f3_bounds[0] == 2500.0
    assert f3_bounds[1] == 3000.0
    assert f3_bounds[2] is False

    # Assert - Ensure the extractor was commanded to rebuild its sizes based on the new limits
    widget.audioFeatureExtractor.recalculate_size.assert_called_once()