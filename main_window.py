import os
from PySide6.QtWidgets import QMainWindow
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice

from project_config import ProjectConfigController
from execution import ExecutionController
from debug import DebugController
from results import ResultsController

from logs import logger, LogsController

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class MainWindow(QMainWindow):
    def __init__(self, role: str):
        super().__init__()
        self.role = role

        logger.info(f"Starting MainWindow with role='{role}'")

        self.load_ui()
        self.configure_by_role()

        # ================== GLOBAL LOG VIEW SETUP ==================
        self.ui.plainTextEdit_mainLogs.clear()
        # ===========================================================

        # Initialize Logs tab
        self.logs_controller = LogsController(self.tab_logs)
        logger.info("LogsController initialized")

        # ✅ Pass bottom one-line status widget to LogsController
        self.logs_controller.set_main_status_widget(
            self.ui.plainTextEdit_mainLogs
        )

        # Initialize Project Configuration
        self.project_config = ProjectConfigController(self.tab_project)
        logger.info("ProjectConfigController initialized")

        # Initialize Execution tab
        self.execution_controller = ExecutionController(self.tab_execution)
        logger.info("ExecutionController initialized")

        # Initialize Debug tab
        self.debug_controller     = DebugController(self.tab_debug)
        logger.info("DebugController initialized")

        # Initialize Results tab
        self.results_controller   = ResultsController(self.tab_results)
        logger.info("ResultsController initialized")

        self.showMaximized()
        logger.info("Main window maximized")

        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        logger.info("Main window initialized successfully")

    # -------------------------------------------------
    def load_ui(self):
        logger.info("Loading main.ui")

        loader = QUiLoader()
        ui_file = QFile(os.path.join(BASE_DIR, "main.ui"))

        if not ui_file.open(QIODevice.ReadOnly):
            raise RuntimeError("Cannot open main.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        if not self.ui:
            logger.error("Failed to load main.ui")
            raise RuntimeError("Failed to load main.ui")

        self.setCentralWidget(self.ui)
        self.setWindowTitle("PCB Tester – Main Window")

        # Tab references (UNCHANGED)
        self.tab_widget    = self.ui.tabWidget
        self.tab_project   = self.ui.tabProject
        self.tab_execution = self.ui.tabExecution
        self.tab_results   = self.ui.tabResults
        self.tab_logs      = self.ui.tabLogs
        self.tab_debug     = self.ui.tabDebug
        self.tab_settings  = self.ui.tabSettings

        print("Main UI loaded successfully")
        logger.info("Main UI loaded successfully")

    # -------------------------------------------------
    def configure_by_role(self):
        logger.info(f"Configuring UI for role='{self.role}'")

        if self.role.lower() == "user":
            index = self.tab_widget.indexOf(self.tab_settings)
            if index != -1:
                self.tab_widget.removeTab(index)
                logger.info("Settings tab removed for user role")

        self.tab_widget.setCurrentIndex(1)  # Execution default
        print("Execution tab set as default")
        logger.info("Execution tab set as default")

    # -------------------------------------------------
    def on_tab_changed(self, index):
        current_widget = self.tab_widget.widget(index)

        # ✅ Only when user SWITCHES to Execution tab
        if current_widget == self.tab_execution:
            print("[MAIN] Execution tab activated (real switch)")
            logger.info("Execution tab activated")
            self.execution_controller.load_selected_project()
