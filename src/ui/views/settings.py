import os
from PySide6.QtWidgets import QWidget, QRadioButton
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QApplication

from src.ui.settings_manager import SettingsManager
from src.ui.theme import AppTheme
from src.core.logger import logger

class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.load_ui()
        self.initialize_state()
        self.setup_connections()
        logger.info("SettingsView initialized")

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "..", "forms", "settings.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open settings.ui at {ui_path}")
            raise RuntimeError("Cannot open settings.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Layout integration
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Bind Widgets
        self.radio_light = self.findChild(QRadioButton, "radio_light")
        self.radio_dark = self.findChild(QRadioButton, "radio_dark")

    def initialize_state(self):
        current_theme = self.settings_manager.get_setting("theme", AppTheme.LIGHT)
        if current_theme == AppTheme.LIGHT:
            self.radio_light.setChecked(True)
        else:
            self.radio_dark.setChecked(True)

    def setup_connections(self):
        self.radio_light.toggled.connect(self.on_theme_changed)
        self.radio_dark.toggled.connect(self.on_theme_changed)

    def on_theme_changed(self):
        # Determine selected theme
        if self.radio_light.isChecked():
            new_theme = AppTheme.LIGHT
        else:
            new_theme = AppTheme.DARK

        # Only apply if changed
        current_theme = self.settings_manager.get_setting("theme", AppTheme.LIGHT)
        if new_theme != current_theme:
            logger.info(f"Theme changing to {new_theme}")
            self.settings_manager.save_setting("theme", new_theme)
            AppTheme.apply_theme(QApplication.instance(), new_theme)
