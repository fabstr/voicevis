import os
import json
import pyqtgraph as pg


class AnnotationMarker(pg.ScatterPlotItem):
    def __init__(self, x, y, text, plot_name, plot_widget, app_ref):
        # Draw a yellow star at the exact coordinates
        super().__init__(
            x=[x], y=[y],
            symbol='star', size=20, pen=pg.mkPen('k'), brush=pg.mkBrush('w')
        )
        self.x_val = x
        self.y_val = y
        self.text_val = text
        self.plot_name = plot_name
        self.plot_widget = plot_widget
        self.app_ref = app_ref

        # Native Qt ToolTip: Automatically displays text when hovered!
        self.setToolTip(text)

    def to_dict(self):
        """Serializes the marker instance into a dictionary."""
        return {
            "time": self.x_val,
            "y": self.y_val,
            "text": self.text_val,
            "plot": self.plot_name
        }

    @staticmethod
    def save_to_file(filepath, markers, audio_path):
        """Serializes a list of AnnotationMarker objects to a JSON file."""
        data = {
            "original_audio": os.path.abspath(audio_path) if audio_path else "",
            "fallback_audio": os.path.basename(audio_path) if audio_path else "",
            "annotations": [marker.to_dict() for marker in markers]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_from_file(filepath):
        """
        Deserializes annotations from a JSON file.
        Returns:
            active_audio_path (str | None)
            annotations (list of dicts)
            original_audio_path (str)
            fallback_audio_path (str)
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Annotation file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        original_audio_path = data.get("original_audio", "")
        fallback_audio_path = data.get("fallback_audio", "")
        annotations = data.get("annotations", [])

        # Determine the best available audio path
        active_audio_path = None
        if original_audio_path and os.path.exists(original_audio_path):
            active_audio_path = original_audio_path
        elif fallback_audio_path:
            possible_path = os.path.join(os.path.dirname(filepath), fallback_audio_path)
            if os.path.exists(possible_path):
                active_audio_path = possible_path

        return active_audio_path, annotations, original_audio_path, fallback_audio_path