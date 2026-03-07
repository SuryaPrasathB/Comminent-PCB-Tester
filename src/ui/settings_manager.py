import json
import os
from src.core.logger import logger
from src.ui.theme import AppTheme

SETTINGS_FILE = "user_settings.json"

DEFAULT_SETTINGS = {
    "theme": AppTheme.LIGHT,
    "report_export": {
        "template_path": "Report Export/template/active_template.xlsx",
        "export_path": "Report Export",
        "mappings": {
            "project_name": "",
            "pcb_serial": "",
            "overall_status": "",
            "timestamp": "",
            "sn": "A6",
            "description": "B6",
            "r": "C6",
            "y": "D6",
            "b": "E6",
            "n": "F6",
            "expected_v": "G6",
            "expected_i": "H6",
            "measured_v": "I6",
            "measured_i": "J6",
            "result": "K6"
        }
    },
    "test_parameters": {
        "stabilization_time": 2.0,
        "current_tolerance_percent": 20.0,
        "zero_current_limit": 0.2,
        "limit_table": {
            "0.0": {"v_upper": 5.75, "v_lower": 5.40},
            "0.5": {"v_upper": 5.75, "v_lower": 5.40},
            "1.25": {"v_upper": 5.75, "v_lower": 5.30},
            "2.5": {"v_upper": 5.75, "v_lower": 5.10}
        }
    }
}

class SettingsManager:
    """
    Manages application user settings, persisted to a JSON file.
    """
    _instance = None
    _settings = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._load_settings()
        return cls._instance

    def _load_settings(self):
        """Loads settings from the JSON file into memory."""
        self._settings = DEFAULT_SETTINGS.copy()

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge loaded settings into defaults (shallow merge)
                    self._settings.update(loaded)

                    # Deep merge for report_export to preserve new keys if any
                    if "report_export" in loaded and isinstance(loaded["report_export"], dict):
                        default_report = DEFAULT_SETTINGS["report_export"]
                        merged_report = default_report.copy()
                        merged_report.update(loaded["report_export"])

                        # Deep merge mappings too
                        if "mappings" in loaded["report_export"]:
                             merged_mappings = default_report["mappings"].copy()
                             merged_mappings.update(loaded["report_export"]["mappings"])
                             merged_report["mappings"] = merged_mappings

                        self._settings["report_export"] = merged_report

                    # Deep merge for test_parameters
                    if "test_parameters" in loaded and isinstance(loaded["test_parameters"], dict):
                        default_test = DEFAULT_SETTINGS["test_parameters"]
                        merged_test = default_test.copy()
                        merged_test.update(loaded["test_parameters"])

                        if "limit_table" in loaded["test_parameters"]:
                            merged_limit = default_test["limit_table"].copy()
                            for k, v in loaded["test_parameters"]["limit_table"].items():
                                if k in merged_limit:
                                    merged_limit[k].update(v)
                                else:
                                    merged_limit[k] = v
                            merged_test["limit_table"] = merged_limit

                        self._settings["test_parameters"] = merged_test

                logger.info("User settings loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load settings from {SETTINGS_FILE}: {e}")
                # Fallback to defaults (already set)
        else:
            logger.info("No user settings file found. Using defaults.")

    def get_setting(self, key, default=None):
        """Retrieves a setting value."""
        return self._settings.get(key, default)

    def save_setting(self, key, value):
        """Saves a setting value and persists to file."""
        self._settings[key] = value
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self._settings, f, indent=4)
            logger.info(f"Setting saved: {key}={value}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
