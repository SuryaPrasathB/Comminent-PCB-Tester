import os
import inspect
import threading
from datetime import datetime




# =====================================================
# CENTRAL LOGGER
# =====================================================
class AppLogger:
    """
    Central application logger
    - New log file per app start
    - Dynamic Class : Method name
    """

    def __init__(self, app_name="pcb_tester"):
        from src.core.paths import get_log_dir
        self.log_dir = get_log_dir()
        
        self.lock = threading.Lock()

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(
            self.log_dir, f"{app_name}_{timestamp}.log"
        )
        self.history = []

        self.info(f"AppLogger initialized at {self.log_dir}")

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

        with self.lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(full_line + "\n")
                    f.flush()  # Force write to disk
            except Exception:
                pass

        self.history.append(full_line)

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

    def debug(self, message: str):
        self._log("DEBUG", message)

    def critical(self, message: str):
        self._log("CRITICAL", message)


# ✅ Global singleton
logger = AppLogger()