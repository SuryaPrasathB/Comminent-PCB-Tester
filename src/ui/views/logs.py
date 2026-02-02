import os
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice
from src.core.logger import logger

class LogsView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New LogsView")
        self.load_ui()

        # Connect to global logger
        logger.log_signal.connect(self.append_log)

        # Load existing history
        for line in logger.get_history():
            self.append_log(line)

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "..", "forms", "logs.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open logs.ui at {ui_path}")
            raise RuntimeError("Cannot open logs.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        self.txt_logs = self.findChild(QWidget, "plainTextEdit_logs")

    def append_log(self, line):
        self.txt_logs.appendPlainText(line)
        # Auto scroll
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
