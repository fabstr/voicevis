import json
import pytest


# --- TESTS ---

def test_export_targets_successful(widget, mocker):
    """
    Business Logic: Ensures that the internal `target_bands` dictionary (which contains
    PyQtGraph UI elements) is safely stripped of UI references and correctly formatted
    into a JSON-compatible dictionary for exporting.
    """
    # 1. Setup fake internal target bands data containing UI items that cannot be JSON serialized
    mock_ui_item = mocker.MagicMock()
    widget.target_bands = {
        'Plot1': {
            'F1_Pitch': {
                'enabled': True,
                'min': 150.0,
                'max': 250.0,
                'item': mock_ui_item  # This should NOT be in the exported JSON
            }
        },
        'Plot2': {
            'F2_Pitch': {
                'enabled': False,
                'min': 800.0,
                'max': 1200.0,
                'item': mock_ui_item
            }
        }
    }

    # 2. Mock file dialog to simulate user selecting a save path
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getSaveFileName',
        return_value=('dummy_export.json', 'JSON Files (*.json)')
    )

    # 3. Mock file operations
    mock_file = mocker.patch('builtins.open', mocker.mock_open())
    mock_json_dump = mocker.patch('json.dump')

    # Act
    widget.export_targets()

    # Assert
    mock_file.assert_called_once_with('dummy_export.json', 'w')

    # Check exactly what data was passed to json.dump
    expected_export_dict = {
        'Plot1': {
            'F1_Pitch': {'enabled': True, 'min': 150.0, 'max': 250.0}
        },
        'Plot2': {
            'F2_Pitch': {'enabled': False, 'min': 800.0, 'max': 1200.0}
        }
    }

    mock_json_dump.assert_called_once()
    args, kwargs = mock_json_dump.call_args
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
    forwards the path to the internal `_load_targets_from_path` loading method.
    """
    # Simulate user selecting a file to open
    mocker.patch(
        'ui.LiveMultiPlotWidget.QtWidgets.QFileDialog.getOpenFileName',
        return_value=('dummy_import.json', 'JSON Files (*.json)')
    )

    # Mock the internal loader so we can intercept the call
    mock_loader = mocker.patch.object(widget, '_load_targets_from_path')

    # Act
    widget.import_targets()

    # Assert
    mock_loader.assert_called_once_with('dummy_import.json')


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

    mock_loader = mocker.patch.object(widget, '_load_targets_from_path')

    # Act
    widget.import_targets()

    # Assert
    mock_loader.assert_not_called()


def test_targets_propagate_to_feature_extractor(widget, mocker):
    """
    Business Logic: Ensures that when target settings are loaded, the specific
    min/max boundary limits are correctly parsed and assigned deep into the
    underlying AudioFeatureExtractor's target_config object, and a recalculation
    is triggered.
    """
    # 1. Setup a comprehensive fake JSON payload containing distinct values for all formants
    mock_json_data = {
        "F1_Pitch": {
            "F1_Pitch": {"enabled": True, "min": 300.0, "max": 600.0}
        },
        "F2_Pitch": {
            "F2_Pitch": {"enabled": True, "min": 1000.0, "max": 1500.0}
        },
        "F3_Pitch": {
            "F3_Pitch": {"enabled": False, "min": 2500.0, "max": 3000.0}
        }
    }

    # Mock 'open' to simulate reading the file
    mocker.patch('builtins.open', mocker.mock_open(read_data=json.dumps(mock_json_data)))

    # Mock update_plots to prevent UI rendering logic from running
    mocker.patch.object(widget, 'update_plots')

    # Act
    widget._load_targets_from_path("dummy_path.json")

    # Assert - Verify propagation to the internal F1 limits
    assert widget.audioFeatureExtractor.target_config.f1_pitch_min == 300.0
    assert widget.audioFeatureExtractor.target_config.f1_pitch_max == 600.0

    # Assert - Verify propagation to the internal F2 limits
    assert widget.audioFeatureExtractor.target_config.f2_pitch_min == 1000.0
    assert widget.audioFeatureExtractor.target_config.f2_pitch_max == 1500.0

    # Assert - Verify propagation to the internal F3 limits
    assert widget.audioFeatureExtractor.target_config.f3_pitch_min == 2500.0
    assert widget.audioFeatureExtractor.target_config.f3_pitch_max == 3000.0

    # Assert - Ensure the extractor was commanded to rebuild its sizes based on the new limits
    widget.audioFeatureExtractor.recalculate_size.assert_called_once()