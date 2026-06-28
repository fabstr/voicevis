import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class TargetConfig:
    # Now tracking min, max, and explicit enabled parameters per target uniform list
    targets: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "loudness", "min": 0.0, "max": 1.0, "enabled": True},
        {"name": "pitch", "min": 0.0, "max": 350.0, "enabled": True},
        {"name": "f1", "min": 300.0, "max": 500.0, "enabled": True},
        {"name": "f2", "min": 1300.0, "max": 1700.0, "enabled": True},
        {"name": "f3", "min": 2550.0, "max": 2750.0, "enabled": True},
        {"name": "f1_pitch", "min": 1.0, "max": 15.0, "enabled": True},
        {"name": "f2_pitch", "min": 1.0, "max": 30.0, "enabled": True},
        {"name": "f3_pitch", "min": 1.0, "max": 50.0, "enabled": True},
        {"name": "size", "min": -500.0, "max": 1000.0, "enabled": True},
        {"name": "size2", "min": -500.0, "max": 500.0, "enabled": True},
        {"name": "weight", "min": 0.0, "max": 4.0e-7, "enabled": True},
        {"name": "H1_H2", "min": -10, "max": 20, "enabled": True},
        {"name": "H1_A3", "min": 0, "max": 30, "enabled": True},
    ])

    def get_bounds(self, name: str) -> Optional[tuple]:
        """Utility to safely pull out min, max, and enabled values by target name."""
        name_lower = name.lower()
        for t in self.targets:
            if t["name"].lower() == name_lower:
                return t["min"], t["max"], t.get("enabled", True)
        return None

    def set_bounds(self, name: str, min_val: float, max_val: float, enabled: bool = True):
        """Utility to safely modify boundaries and target toggles by name."""
        name_lower = name.lower()
        for t in self.targets:
            if t["name"].lower() == name_lower:
                t["min"] = min_val
                t["max"] = max_val
                t["enabled"] = enabled
                return
        # Append dynamically if it doesn't exist
        self.targets.append({"name": name_lower, "min": min_val, "max": max_val, "enabled": enabled})

    def _round_floats(self, target_list: list) -> list:
        """Formats target dictionary floats to 4 significant digits."""
        rounded = []
        for t in target_list:
            t_copy = t.copy()
            if "min" in t_copy and isinstance(t_copy["min"], (int, float)):
                t_copy["min"] = float(f"{t_copy['min']:.4g}")
            if "max" in t_copy and isinstance(t_copy["max"], (int, float)):
                t_copy["max"] = float(f"{t_copy['max']:.4g}")
            rounded.append(t_copy)
        return rounded

    def __str__(self):
        return json.dumps({"targets": self._round_floats(self.targets)}, indent=4)

    def to_json(self, file_path: str, indent: int = 4) -> None:
        """Serializes the configuration instance to a JSON file."""
        clean_data = {"targets": self._round_floats(self.targets)}
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(clean_data, f, indent=indent)

    @classmethod
    def from_json(cls, file_path: str) -> 'TargetConfig':
        """Loads a JSON configuration and returns a new TargetConfig instance."""
        with open(file_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        return cls(targets=config_dict.get("targets", []))