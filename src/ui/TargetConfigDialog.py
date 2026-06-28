from PyQt6 import QtWidgets
import pyqtgraph as pg
import copy

from signal_processing.TargetConfig import TargetConfig


class TargetConfigDialog(QtWidgets.QDialog):
    """Extracted dialog component for managing acoustic target bounds via TargetConfig."""

    def __init__(self, current_config: TargetConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Targets")
        self.setMinimumWidth(400)

        # Keep a deep copy of the original config so updates only commit on 'Accept'
        self.config = copy.deepcopy(current_config)
        self.gui_elements = {}

        self._init_ui()
        self._load_config_into_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QGridLayout()
        layout.addLayout(form_layout)

        # Form Headers
        form_layout.addWidget(QtWidgets.QLabel("<b>Enable</b>"), 0, 0)
        form_layout.addWidget(QtWidgets.QLabel("<b>Target Field</b>"), 0, 1)
        form_layout.addWidget(QtWidgets.QLabel("<b>Target min</b>"), 0, 2)
        form_layout.addWidget(QtWidgets.QLabel("<b>Target max</b>"), 0, 3)

        # Define structural mapping between TargetConfig properties and User-Facing Labels
        # Layout: field_prefix: (Display Label, default_min, default_max)
        self.fields_definition = {
            "loudness": ("Loudness", 0.0, 1.0),
            "pitch": ("Pitch", 0.0, 350.0),
            "f1": ("F1", 300.0, 500.0),
            "f2": ("F2", 1300.0, 1700.0),
            "f3": ("F3", 2550.0, 2750.0),
            "f1_pitch": ("F1_Pitch", 1.0, 15.0),
            "f2_pitch": ("F2_Pitch", 1.0, 30.0),
            "f3_pitch": ("F3_Pitch", 1.0, 50.0),
            "size": ("Size", -30.0, 30.0),
            "size2": ("Size2", -500.0, 500.0),
            "weight": ("Weight", 0.0, 4.0e-7),
            "H1_H2": ("H1_H2", -10.0, 20),
            "H1_A3": ("H1_A3", 0.0, 30),
        }

        row = 1
        for field_prefix, (label_text, _, _) in self.fields_definition.items():
            cb = QtWidgets.QCheckBox()
            lbl = QtWidgets.QLabel(label_text)

            min_spin = pg.SpinBox(bounds=[-100000, 100000], decimals=4 if field_prefix == "weight" else 2)
            max_spin = pg.SpinBox(bounds=[-100000, 100000], decimals=4 if field_prefix == "weight" else 2)

            form_layout.addWidget(cb, row, 0)
            form_layout.addWidget(lbl, row, 1)
            form_layout.addWidget(min_spin, row, 2)
            form_layout.addWidget(max_spin, row, 3)

            # Store widget references mapped directly to the target config prefix identifier
            self.gui_elements[field_prefix] = {
                'cb': cb,
                'min': min_spin,
                'max': max_spin
            }
            row += 1

        # Dialog Controls Action Bar
        btn_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Apply && Close")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def _load_config_into_ui(self):
        """Populates UI Elements dynamically straight from TargetConfig properties."""
        for field_prefix, (_, default_min, default_max) in self.fields_definition.items():
            bounds = self.config.get_bounds(field_prefix)

            if bounds is not None:
                min_val, max_val, is_enabled = bounds
            else:
                min_val, max_val, is_enabled = default_min, default_max, True

            self.gui_elements[field_prefix]['cb'].setChecked(is_enabled)
            self.gui_elements[field_prefix]['min'].setValue(min_val)
            self.gui_elements[field_prefix]['max'].setValue(max_val)

    def get_confirmed_config(self) -> TargetConfig:
        """Saves current GUI states back to target config payload attributes."""
        for field_prefix in self.fields_definition.keys():
            widgets = self.gui_elements[field_prefix]
            self.config.set_bounds(
                field_prefix,
                widgets['min'].value(),
                widgets['max'].value(),
                widgets['cb'].isChecked()
            )
        return self.config