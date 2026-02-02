import sys
from PySide6.QtWidgets import QApplication
from new_ui.login_window import LoginWindow
from new_ui.main_window import MainWindow
from new_ui.settings_manager import SettingsManager
from new_ui.theme import AppTheme
from db_utils import create_tables

from logs import logger


if __name__ == "__main__":
    logger.info("Application startup initiated")

    # Create database tables once on startup
    create_tables()
    logger.info("Database tables checked/created")

    app = QApplication(sys.argv)
    logger.info("QApplication created")

    # Apply saved theme
    settings = SettingsManager()
    saved_theme = settings.get_setting("theme", AppTheme.LIGHT)
    AppTheme.apply_theme(app, saved_theme)
    logger.info(f"Applied saved theme: {saved_theme}")

    print("Starting application...")
    try:
        while True:
            login = LoginWindow()
            logger.info("LoginWindow instance created")

            print("Login dialog created")
            result = login.exec()
            print(f"Login dialog result: {result}")

            logger.info(f"Login dialog closed with result={result}")

            if result == LoginWindow.Accepted:
                role = login.logged_in_role
                print(f"Login successful - role: {role}")

                logger.info(f"Login successful, role='{role}'")

                main_win = MainWindow(role)
                logger.info("MainWindow instance created")

                main_win.showMaximized()
                logger.info("MainWindow shown maximized")

                # Block until main window closes
                app.exec()

                # Check if logout was requested
                if hasattr(main_win, 'wants_relogin') and main_win.wants_relogin:
                    logger.info("Logout requested - restarting login")
                    continue
                else:
                    logger.info("Application closed by user")
                    break

            else:
                print("Login cancelled")
                logger.warning("Login cancelled by user")
                break

        sys.exit(0)

    except Exception as e:
        print(f"Application error: {e}")
        logger.error(f"Fatal application error: {e}")
        sys.exit(1)
