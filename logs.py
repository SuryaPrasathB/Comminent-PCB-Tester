import os
import inspect
from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice


# =====================================================
# CENTRAL LOGGER
# =====================================================
class AppLogger(QObject):
    """
    Central application logger
    - New log file per app start
    - Dynamic Class : Method name
    - Emits logs to UI
    """

    log_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, log_dir="logs", app_name="pcb_tester"):
        super().__init__()

        base_dir = os.getcwd()
        self.log_dir = os.path.join(base_dir, log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(
            self.log_dir, f"{app_name}_{timestamp}.log"
        )

        self.info("AppLogger initialized")

    # -------------------------------------------------
    def _get_context(self):
        """
        Returns: (ClassName, FunctionName)
        """
        try:
            frame = inspect.currentframe()
            outer = inspect.getouterframes(frame, 4)
            caller = outer[3].frame

            func_name = caller.f_code.co_name

            cls_name = "GLOBAL"
            if "self" in caller.f_locals:
                cls_name = caller.f_locals["self"].__class__.__name__

            return cls_name, func_name
        except Exception:
            return "UNKNOWN", "UNKNOWN"

    # -------------------------------------------------
    def _log(self, level: str, message: str):
        cls, func = self._get_context()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_line = f"[{timestamp}] [{level}] {cls} : {func} : {message}"

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(full_line + "\n")
        except Exception:
            pass

        # Full log (Logs tab)
        self.log_signal.emit(full_line)

        # One-line status (Main UI bottom)
        #status_line = f"{cls} : {func} : {message}"
        self.status_signal.emit(message)

    # -------------------------------------------------
    def info(self, message: str):
        self._log("INFO", message)

    def warning(self, message: str):
        self._log("WARN", message)

    def error(self, message: str):
        self._log("ERROR", message)


# ✅ Global singleton
logger = AppLogger()


# =====================================================
# LOGS TAB CONTROLLER
# =====================================================
class LogsController(QWidget):
    """
    Logs tab controller
    - Shows full logs
    - Updates main one-line status
    """

    def __init__(self, parent_tab: QWidget):
        super().__init__(parent_tab)

        self.parent_tab = parent_tab
        self._main_status_widget = None

        logger.info("Initializing LogsController")

        self.load_ui()

        # Connect signals
        logger.log_signal.connect(self.append_log)
        logger.status_signal.connect(self.update_main_status)

        logger.info("Logs tab initialized")

    # -------------------------------------------------

    def load_ui(self):
        logger.info("Loading logs.ui")

        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "logs.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Unable to open logs.ui: {ui_path}")

        self.ui = loader.load(ui_file, self.parent_tab)
        ui_file.close()

        if not self.ui:
            raise RuntimeError("Failed to load logs.ui")

        layout = self.parent_tab.layout()
        if layout is None:
            layout = QVBoxLayout(self.parent_tab)
            self.parent_tab.setLayout(layout)

        layout.addWidget(self.ui)
        self.txt_logs = self.ui.plainTextEdit_logs
        #self.search_box = self.ui.lineEdit_search
        #self.search_box.textChanged.connect(self.search_logs)

        logger.info("Logs UI loaded successfully")

    # -------------------------------------------------
    def append_log(self, line: str):
        """
        Append log line to UI and auto-scroll
        """
        self.txt_logs.appendPlainText(line)
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
    # -------------------------------------------------
    def set_main_status_widget(self, widget):
        """
        Called by MainWindow to pass bottom status field
        """
        self._main_status_widget = widget

    # -------------------------------------------------
    def update_main_status(self, line: str):
        """
        One-line overwrite status (Main UI bottom)
        """
        if self._main_status_widget:
            self._main_status_widget.setPlainText(line)

'''
    def search_logs(self, text: str):
        """
        Highlight matching log text
        """
        cursor = self.txt_logs.textCursor()
        document = self.txt_logs.document()

        # Clear previous highlights
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        clear_format = QTextCharFormat()
        clear_format.setBackground(QColor("transparent"))

        while not cursor.isNull() and not cursor.atEnd():
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
            cursor.setCharFormat(clear_format)
        cursor.endEditBlock()

        if not text:
            return

        # Highlight matches
        highlight_format = QTextCharFormat()
        highlight_format.setBackground(QColor("#ffe066"))

        cursor = document.find(text, 0)
        if cursor.isNull():
            return

        self.txt_logs.setTextCursor(cursor)

        while not cursor.isNull():
            cursor.mergeCharFormat(highlight_format)
            cursor = document.find(text, cursor.position())
'''