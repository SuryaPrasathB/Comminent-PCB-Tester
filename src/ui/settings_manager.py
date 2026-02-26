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
            "pcb_serial": "",
            "overall_status": "",
            "date": "",
            "time": "",
            "description": "A6",
            "r": "B6",
            "y": "C6",
            "b": "D6",
            "n": "E6",
            "expected_v": "F6",
            "expected_i": "G6",
            "measured_v": "H6",
            "measured_i": "I6",
            "result": "J6"
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
