import os
import sys
from PySide6.QtWidgets import QMainWindow, QWidget, QStackedWidget, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QApplication, QSizePolicy
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QIcon, QPixmap

from new_ui.icons import IconHelper
from new_ui.theme import AppTheme
from new_ui.settings_manager import SettingsManager
from logs import logger, LogsController

from new_ui.execution import ExecutionView
from new_ui.project_config import ProjectConfigView
from new_ui.results import ResultsView
from new_ui.debug import DebugView
from new_ui.logs import LogsView
from new_ui.settings import SettingsView

class MainWindow(QMainWindow):
    def __init__(self, role):
        super().__init__()
        self.role = role
        self.wants_relogin = False
        
        self.settings_manager = SettingsManager()
        self.current_theme = self.settings_manager.get_setting("theme", AppTheme.LIGHT)
        
        # Ensure theme is applied (redundancy for re-login or direct instantiation)
        AppTheme.apply_theme(QApplication.instance(), self.current_theme)

        logger.info(f"Initializing New MainWindow with role={role}")

        self.load_ui()
        self.setup_icons()
        self.setup_navigation()

        # Set Window Icon
        icon_path = os.path.join("resources", "icons", "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            # Load into sidebar logo
            if hasattr(self, 'label_logo_icon'):
                pixmap = QPixmap(icon_path)
                self.label_logo_icon.setPixmap(pixmap)

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

        # Fix: If loaded UI is QMainWindow, extract its central widget
        if isinstance(loaded_widget, QMainWindow):
            self.ui = loaded_widget.centralWidget()
            self.ui.setParent(self)
        else:
            self.ui = loaded_widget

        self.setCentralWidget(self.ui)
        
        # Ensure the content area stretches
        if self.centralWidget() and self.centralWidget().layout():
            self.centralWidget().layout().setStretch(1, 1)

        self.setWindowTitle("PCB Tester Pro")

        # Bind Widgets
        self.stack = self.findChild(QStackedWidget, "stackedWidget_content")

        # Fix Layout: Force stack to expand and setup layout stretches
        if self.stack:
            self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Apply specific stretch factors to vertical layout (Header, Content, Footer)
        if self.centralWidget() and self.centralWidget().layout():
            h_layout = self.centralWidget().layout()
            # Index 1 is the verticalLayout_content (nested layout)
            if h_layout.count() > 1:
                content_item = h_layout.itemAt(1)
                if content_item and content_item.layout():
                    v_layout = content_item.layout()
                    # 0: Header, 1: Stack, 2: Status
                    v_layout.setStretch(0, 0)
                    v_layout.setStretch(1, 1)
                    v_layout.setStretch(2, 0)
        
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
        self.btn_logout = self.findChild(QPushButton, "btn_logout")
        
        # Bind Sidebar Header Components
        self.label_logo_icon = self.findChild(QLabel, "label_logo_icon")
        self.label_logo_text = self.findChild(QLabel, "label_logo_text")

        self.sidebar_buttons = [
            self.btn_exec, self.btn_proj, self.btn_res,
            self.btn_debug, self.btn_logs, self.btn_settings,
            self.btn_logout
        ]

        # Store original text for restoration
        for btn in self.sidebar_buttons:
            if btn:
                btn.setProperty("original_text", btn.text())

        self.btn_toggle_sidebar = self.findChild(QPushButton, "btn_toggle_sidebar")
        self.widget_sidebar = self.findChild(QWidget, "widget_sidebar")

        # Role Management
        if self.role.lower() != "admin":
            if self.btn_settings: self.btn_settings.setVisible(False)
            if self.btn_debug: self.btn_debug.setVisible(False)

    def setup_icons(self):
        # Apply icons using helper
        IconHelper.apply_icon(self.btn_exec, "execution", "white")
        IconHelper.apply_icon(self.btn_proj, "project", "white")
        IconHelper.apply_icon(self.btn_res, "results", "white")
        IconHelper.apply_icon(self.btn_debug, "debug", "white")
        IconHelper.apply_icon(self.btn_logs, "logs", "white")
        IconHelper.apply_icon(self.btn_settings, "settings", "white")
        IconHelper.apply_icon(self.btn_logout, "logout", "white")

    def setup_navigation(self):
        self.btn_exec.clicked.connect(lambda: self.navigate("execution"))
        self.btn_proj.clicked.connect(lambda: self.navigate("project"))
        self.btn_res.clicked.connect(lambda: self.navigate("results"))
        self.btn_debug.clicked.connect(lambda: self.navigate("debug"))
        self.btn_logs.clicked.connect(lambda: self.navigate("logs"))
        self.btn_settings.clicked.connect(lambda: self.navigate("settings"))

        self.btn_logout.clicked.connect(self.on_logout)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)

        # Initialize Views storage
        self.views = {}

        # Eager load logs so they capture everything
        self._get_or_create_view("logs")

        # Load Default
        self.navigate("execution")

    def on_logout(self):
        self.wants_relogin = True
        self.close()

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
            view = SettingsView()

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
        
        # Ensure buttons reflect selection visually (optional, if stylesheets handle it via 'checked' state)
        # The sidebar logic manages checkable buttons?
        # In .ui, buttons are autoExclusive=true. So clicking one unchecks others.
        # But programmatically we need to set checked state.
        
        btn_map = {
            "execution": self.btn_exec,
            "project": self.btn_proj,
            "results": self.btn_res,
            "debug": self.btn_debug,
            "logs": self.btn_logs,
            "settings": self.btn_settings
        }
        
        if page_name in btn_map and btn_map[page_name]:
            btn_map[page_name].setChecked(True)

    def toggle_sidebar(self):
        width = self.widget_sidebar.width()

        # Target width: Collapsed=50, Expanded=250
        target = 50 if width > 100 else 250

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

        # Toggle Text Visibility
        is_expanding = target > 100
        
        # Logo Text
        if self.label_logo_text:
            self.label_logo_text.setVisible(is_expanding)
            
        # Keep Logo Icon Always Visible (handled by layout)

        # Toggle Button Text
        for btn in self.sidebar_buttons:
            if not btn: continue
            if not is_expanding:
                # Collapsing: Hide text
                btn.setText("")
            else:
                # Expanding: Restore text
                original = btn.property("original_text")
                if original is not None:
                    btn.setText(original)
