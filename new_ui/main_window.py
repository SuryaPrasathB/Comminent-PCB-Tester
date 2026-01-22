import os
import sys
from PySide6.QtWidgets import QMainWindow, QWidget, QStackedWidget, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QApplication
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QEasingCurve, QPropertyAnimation

from new_ui.icons import IconHelper
from new_ui.theme import AppTheme
from logs import logger, LogsController

from new_ui.execution import ExecutionView
from new_ui.project_config import ProjectConfigView
from new_ui.results import ResultsView
from new_ui.debug import DebugView
from new_ui.logs import LogsView
# SettingsView is placeholder for now or we reuse project config?
# Let's create a placeholder for settings.

class MainWindow(QMainWindow):
    def __init__(self, role):
        super().__init__()
        self.role = role
        self.current_theme = AppTheme.LIGHT  # Default

        logger.info(f"Initializing New MainWindow with role={role}")

        self.load_ui()
        self.setup_icons()
        self.setup_navigation()

        # Apply initial theme
        self.toggle_theme(force_theme=self.current_theme)

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "main_window.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open main_window.ui at {ui_path}")
            raise RuntimeError("Cannot open main_window.ui")

        loaded_widget = loader.load(ui_file)
        ui_file.close()

        # Fix: If loaded UI is QMainWindow, extract its central widget to avoid nesting MainWindows
        if isinstance(loaded_widget, QMainWindow):
            self.ui = loaded_widget.centralWidget()
            # Ensure we keep a reference to loaded_widget if needed, or rely on reparenting.
            # Reparenting the central widget to self is sufficient.
            self.ui.setParent(self)
        else:
            self.ui = loaded_widget

        self.setCentralWidget(self.ui)
        self.setWindowTitle("PCB Tester Pro")
        self.showMaximized()

        # Bind Widgets
        self.stack = self.findChild(QStackedWidget, "stackedWidget_content")
        self.lbl_title = self.findChild(QLabel, "label_page_title")
        self.lbl_user = self.findChild(QLabel, "label_user_info")
        self.status_bar = self.findChild(QPlainTextEdit, "plainTextEdit_status")

        self.lbl_user.setText(f"User: {self.role}")

        # Bind Nav Buttons
        self.btn_exec = self.findChild(QPushButton, "btn_nav_execution")
        self.btn_proj = self.findChild(QPushButton, "btn_nav_project")
        self.btn_res = self.findChild(QPushButton, "btn_nav_results")
        self.btn_debug = self.findChild(QPushButton, "btn_nav_debug")
        self.btn_logs = self.findChild(QPushButton, "btn_nav_logs")
        self.btn_settings = self.findChild(QPushButton, "btn_nav_settings")

        self.btn_theme = self.findChild(QPushButton, "btn_theme_toggle")
        self.btn_logout = self.findChild(QPushButton, "btn_logout")

        self.btn_toggle_sidebar = self.findChild(QPushButton, "btn_toggle_sidebar")
        self.widget_sidebar = self.findChild(QWidget, "widget_sidebar")

        # Role Management
        if self.role.lower() != "admin":
            self.btn_settings.setVisible(False)
            self.btn_debug.setVisible(False) # Maybe hide debug for non-admins?

    def setup_icons(self):
        # Apply icons using helper
        IconHelper.apply_icon(self.btn_exec, "execution", "white")
        IconHelper.apply_icon(self.btn_proj, "project", "white")
        IconHelper.apply_icon(self.btn_res, "results", "white")
        IconHelper.apply_icon(self.btn_debug, "debug", "white")
        IconHelper.apply_icon(self.btn_logs, "logs", "white")
        IconHelper.apply_icon(self.btn_settings, "settings", "white")
        IconHelper.apply_icon(self.btn_theme, "theme_light", "white")
        IconHelper.apply_icon(self.btn_logout, "logout", "white")

    def setup_navigation(self):
        self.btn_exec.clicked.connect(lambda: self.navigate("execution"))
        self.btn_proj.clicked.connect(lambda: self.navigate("project"))
        self.btn_res.clicked.connect(lambda: self.navigate("results"))
        self.btn_debug.clicked.connect(lambda: self.navigate("debug"))
        self.btn_logs.clicked.connect(lambda: self.navigate("logs"))
        self.btn_settings.clicked.connect(lambda: self.navigate("settings"))

        self.btn_theme.clicked.connect(lambda: self.toggle_theme())
        self.btn_logout.clicked.connect(self.close)

        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)

        # Initialize Views storage
        self.views = {}

        # Load Default
        self.navigate("execution")

    def _get_or_create_view(self, page_name):
        if page_name in self.views:
            return self.views[page_name]

        view = None
        if page_name == "execution":
            view = ExecutionView()
        elif page_name == "project":
            view = ProjectConfigView()
        elif page_name == "results":
            view = ResultsView()
        elif page_name == "debug":
            view = DebugView()
        elif page_name == "logs":
            view = LogsView()
        elif page_name == "settings":
            # Placeholder for now
            view = QWidget()
            lbl = QLabel("Settings Placeholder", view)
            lbl.setAlignment(Qt.AlignCenter)

        if view:
            self.views[page_name] = view
            self.stack.addWidget(view)
            return view
        return None

    def navigate(self, page_name):
        logger.info(f"Navigating to {page_name}")

        # Update Title
        titles = {
            "execution": "Execution Dashboard",
            "project": "Project Configuration",
            "results": "Test Results & History",
            "debug": "Hardware Debugging",
            "logs": "System Logs",
            "settings": "System Settings"
        }
        self.lbl_title.setText(titles.get(page_name, "PCB Tester"))

        view = self._get_or_create_view(page_name)
        if view:
            self.stack.setCurrentWidget(view)

    def toggle_sidebar(self):
        width = self.widget_sidebar.width()

        # Target width: Collapsed=60, Expanded=250
        target = 60 if width > 100 else 250

        self.animation = QPropertyAnimation(self.widget_sidebar, b"minimumWidth")
        self.animation.setDuration(300)
        self.animation.setStartValue(width)
        self.animation.setEndValue(target)
        self.animation.setEasingCurve(QEasingCurve.InOutQuart)
        self.animation.start()

        # We also animate maximumWidth to force the resize
        self.anim2 = QPropertyAnimation(self.widget_sidebar, b"maximumWidth")
        self.anim2.setDuration(300)
        self.anim2.setStartValue(width)
        self.anim2.setEndValue(target)
        self.anim2.setEasingCurve(QEasingCurve.InOutQuart)
        self.anim2.start()

        # Toggle Logo Visibility if collapsing
        self.findChild(QLabel, "label_app_logo").setVisible(target > 100)

        # Toggle Button Text (Show icon only if collapsed)
        # We implemented buttons as text with icons, so they might look weird when collapsed.
        # Ideally we would hide the text part or use QToolButton with textBesideIcon.
        # For this rapid prototype, we'll accept the clipping or implement a simple loop to hide text.

        # Simple loop to hide text in sidebar buttons if collapsed
        # (Assuming buttons are direct children of sidebar layout)
        # This is a bit advanced for a quick fix, let's just stick to width animation.
        # The CSS padding-left might need adjustment.

    def toggle_theme(self, force_theme=None):
        if force_theme:
            self.current_theme = force_theme
        else:
            self.current_theme = AppTheme.DARK if self.current_theme == AppTheme.LIGHT else AppTheme.LIGHT

        logger.info(f"Switching theme to {self.current_theme}")

        # Update Toggle Button Icon/Text
        if self.current_theme == AppTheme.LIGHT:
            self.btn_theme.setText(" Dark Mode")
            IconHelper.apply_icon(self.btn_theme, "theme_dark", "white")
        else:
            self.btn_theme.setText(" Light Mode")
            IconHelper.apply_icon(self.btn_theme, "theme_light", "white")

        # Apply Global Theme
        AppTheme.apply_theme(QApplication.instance(), self.current_theme)
