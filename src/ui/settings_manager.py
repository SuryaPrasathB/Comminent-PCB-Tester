import json
import os
from src.core.logger import logger

SETTINGS_FILE = "user_settings.json"

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
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    self._settings = json.load(f)
                logger.info("User settings loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load settings from {SETTINGS_FILE}: {e}")
                self._settings = {}
        else:
            logger.info("No user settings file found. Using defaults.")
            self._settings = {}

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
