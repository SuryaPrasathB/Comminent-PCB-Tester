from PySide6.QtWidgets import (
    QDialog, QMessageBox, QComboBox, QLineEdit, QPushButton, QApplication
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice
import sys

# We'll assume db_utils.py exists with this function, as per the problem description.
from db_utils import authenticate_user
from logs import logger  


class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.logged_in_role = None

        logger.info("LoginWindow initialized")  

        # Load the UI and set it up
        ui_file_name = "login.ui"
        ui_file = QFile(ui_file_name)
        if not ui_file.open(QIODevice.ReadOnly):
            # Handle error
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            logger.error(f"Failed to open login.ui: {ui_file.errorString()}")  
            return

        loader = QUiLoader()
        # Load the UI into a temporary widget
        temp_widget = loader.load(ui_file)
        ui_file.close()

        # Set the layout from the temporary widget to this dialog
        if not temp_widget:
            logger.error("Failed to load login UI")  
            return

        self.setLayout(temp_widget.layout())
        self.setStyleSheet(temp_widget.styleSheet())

        # Copy window properties
        self.setWindowTitle(temp_widget.windowTitle())
        self.setFixedSize(400, 400)  # The size might not transfer, so set it. From the UI file.

        # Find the children widgets of self. The layout transfer reparents them.
        self.mode_combo = self.findChild(QComboBox, "mode_combo")
        self.username_input = self.findChild(QLineEdit, "username_input")
        self.password_input = self.findChild(QLineEdit, "password_input")
        self.login_button = self.findChild(QPushButton, "login_button")

        # Set default values
        self.username_input.setText("Admin")
        self.password_input.setText("Admin")

        # Connect signals

        logger.info("Login UI widgets initialized")  

        self.login_button.clicked.connect(self.handle_login)
        logger.info("Login button signal connected")  

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        role = self.mode_combo.currentText()

        logger.info(
            f"Login attempt | user='{username}' | role='{role}'"
        )  

        if not username or not password:
            logger.warning("Login failed: empty username or password")  
            QMessageBox.warning(self, "Input Error", "Please enter username and password.")
            return

        success, message = authenticate_user(username, password, role)

        if success:
            self.logged_in_role = role
            logger.info(
                f"Login successful | user='{username}' | role='{role}'"
            )  
            self.accept()
        else:
            logger.warning(
                f"Login failed | user='{username}' | role='{role}' | reason='{message}'"
            )  
            QMessageBox.critical(self, "Login Failed", message)


if __name__ == '__main__':
    logger.info("LoginWindow launched as standalone application")  

    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())
