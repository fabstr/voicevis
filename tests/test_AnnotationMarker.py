import os
import json
import pytest
import sys

from PyQt6.QtWidgets import QApplication
from ui.AnnotationMarker import AnnotationMarker


# --- Fixtures ---

@pytest.fixture(scope="session", autouse=True)
def qapp():
    """
    A session-scoped fixture to ensure a QApplication exists.
    PyQtGraph/Qt objects will crash if instantiated without a running application.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# --- Tests ---

def test_to_dict_serialization(mocker):
    """Test that the marker accurately serializes its state to a dictionary."""
    # Use pytest-mock's mocker fixture to create MagicMocks
    mock_plot_widget = mocker.MagicMock()
    mock_app_ref = mocker.MagicMock()

    marker = AnnotationMarker(
        x=1.5,
        y=200.0,
        text="Vowel Shift",
        plot_name="F1_Pitch",
        plot_widget=mock_plot_widget,
        app_ref=mock_app_ref
    )

    expected_dict = {
        "time": 1.5,
        "y": 200.0,
        "text": "Vowel Shift",
        "plot": "F1_Pitch"
    }

    # Pytest uses standard assert statements
    assert marker.to_dict() == expected_dict


def test_save_to_file(tmp_path, mocker):
    """Test that a list of markers correctly saves to a properly formatted JSON file."""
    # tmp_path is a built-in pytest fixture providing a temporary pathlib.Path
    json_filepath = tmp_path / "annotations.json"
    audio_filepath = tmp_path / "audio.wav"

    # Create a dummy audio file so the path exists
    audio_filepath.touch()

    mock_plot_widget = mocker.MagicMock()
    mock_app_ref = mocker.MagicMock()

    marker1 = AnnotationMarker(1.0, 100.0, "Start", "Plot A", mock_plot_widget, mock_app_ref)
    marker2 = AnnotationMarker(2.5, 150.5, "End\nMulti-line", "Plot B", mock_plot_widget, mock_app_ref)

    # Execute save (casting Paths to strings for compatibility)
    AnnotationMarker.save_to_file(str(json_filepath), [marker1, marker2], str(audio_filepath))

    # Verify file exists and parse it directly
    assert json_filepath.exists()

    with open(json_filepath, 'r') as f:
        data = json.load(f)

    assert data["original_audio"] == str(audio_filepath.resolve())
    assert data["fallback_audio"] == "audio.wav"
    assert len(data["annotations"]) == 2
    assert data["annotations"][1]["text"] == "End\nMulti-line"


def test_load_from_file_valid_original_audio(tmp_path):
    """Test loading annotations when the original audio file is intact and found."""
    json_filepath = tmp_path / "test_load.json"
    audio_filepath = tmp_path / "valid_audio.wav"

    # Create dummy audio file so os.path.exists() returns True
    audio_filepath.touch()

    # Mock a saved JSON structure
    mock_data = {
        "original_audio": str(audio_filepath.resolve()),
        "fallback_audio": "valid_audio.wav",
        "annotations": [
            {"time": 3.0, "y": 50.0, "text": "Test Note", "plot": "Plot C"}
        ]
    }

    json_filepath.write_text(json.dumps(mock_data))

    active_audio, annotations, original, fallback = AnnotationMarker.load_from_file(str(json_filepath))

    assert active_audio == str(audio_filepath.resolve())
    assert original == str(audio_filepath.resolve())
    assert fallback == "valid_audio.wav"
    assert len(annotations) == 1
    assert annotations[0]["text"] == "Test Note"


def test_load_from_file_fallback_audio(tmp_path):
    """Test loading when the original audio is missing, but the fallback audio exists."""
    json_filepath = tmp_path / "test_fallback.json"
    fallback_audio_name = "local_audio.wav"
    fallback_full_path = tmp_path / fallback_audio_name

    # Create ONLY the fallback audio file in the same directory as the JSON
    fallback_full_path.touch()

    mock_data = {
        "original_audio": "/fake/missing/path/local_audio.wav",
        "fallback_audio": fallback_audio_name,
        "annotations": []
    }

    json_filepath.write_text(json.dumps(mock_data))

    active_audio, annotations, original, fallback = AnnotationMarker.load_from_file(str(json_filepath))

    # Active audio should successfully resolve to the local fallback path
    assert active_audio == str(fallback_full_path.resolve())
    assert original == "/fake/missing/path/local_audio.wav"


def test_load_from_file_missing_audio(tmp_path):
    """Test that active_audio is None if neither original nor fallback paths exist."""
    json_filepath = tmp_path / "test_missing.json"

    mock_data = {
        "original_audio": "/fake/missing/path/audio.wav",
        "fallback_audio": "audio.wav",
        "annotations": []
    }

    json_filepath.write_text(json.dumps(mock_data))

    active_audio, _, _, _ = AnnotationMarker.load_from_file(str(json_filepath))

    assert active_audio is None


def test_load_from_file_not_found(tmp_path):
    """Test that a FileNotFoundError is raised for a non-existent JSON file."""
    missing_filepath = tmp_path / "does_not_exist.json"

    # pytest.raises handles expected exceptions cleanly
    with pytest.raises(FileNotFoundError):
        AnnotationMarker.load_from_file(str(missing_filepath))