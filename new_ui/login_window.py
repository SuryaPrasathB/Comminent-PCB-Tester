import os
import sys
from PySide6.QtWidgets import (
    QDialog, QMessageBox, QLineEdit, QPushButton, QComboBox, QVBoxLayout
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice

from new_ui.icons import IconHelper
from new_ui.theme import AppTheme
from db_utils import authenticate_user
from logs import logger

class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.logged_in_role = None

        logger.info("Initializing New LoginWindow")
        self.load_ui()
        self.apply_styles()
        self.connect_signals()

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "login.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open login.ui at {ui_path}")
            raise RuntimeError("Cannot open login.ui")

        self.ui = loader.load(ui_file)
        ui_file.close()

        # Set layout correctly
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Bind Widgets
        self.txt_username = self.findChild(QLineEdit, "lineEdit_username")
        self.txt_password = self.findChild(QLineEdit, "lineEdit_password")
        self.cmb_role = self.findChild(QComboBox, "comboBox_role")
        self.btn_login = self.findChild(QPushButton, "btn_primary")

        # Set Title
        self.setWindowTitle("Login - PCB Tester")

        # Set Defaults (Dev Convenience)
        self.txt_username.setText("Admin")
        self.txt_password.setText("Admin")

    def apply_styles(self):
        # Apply Light Theme for Login Screen explicitly (or use system default if complex)
        # Here we just ensure icons are set if needed.
        self.btn_login.setIcon(IconHelper.get("logout", "white"))
        # Using 'logout' icon for 'login' button isn't ideal, let's stick to text or use a key/check icon
        self.btn_login.setIcon(IconHelper.get("check", "white"))

    def connect_signals(self):
        self.btn_login.clicked.connect(self.handle_login)

    def handle_login(self):
        username = self.txt_username.text().strip()
        password = self.txt_password.text()
        role = self.cmb_role.currentText()

        logger.info(f"Login attempt: {username} as {role}")

        if not username or not password:
            QMessageBox.warning(self, "Required", "Please enter username and password")
            return

        success, message = authenticate_user(username, password, role)

        if success:
            self.logged_in_role = role
            logger.info("Login successful")
            self.accept()
        else:
            logger.warning(f"Login failed: {message}")
            QMessageBox.critical(self, "Login Failed", message)
