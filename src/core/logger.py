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
        self.history = []

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

        self.history.append(full_line)

        # Full log (Logs tab)
        self.log_signal.emit(full_line)

        # One-line status (Main UI bottom)
        #status_line = f"{cls} : {func} : {message}"
        self.status_signal.emit(message)

    # -------------------------------------------------
    def get_history(self):
        """Returns the list of all logs since application start."""
        return self.history

    def info(self, message: str):
        self._log("INFO", message)

    def warning(self, message: str):
        self._log("WARN", message)

    def error(self, message: str):
        self._log("ERROR", message)


# ✅ Global singleton
logger = AppLogger()