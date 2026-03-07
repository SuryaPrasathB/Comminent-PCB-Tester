import os
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QFrame, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QTimer, Qt

class TestCompletionDialog(QDialog):
    def __init__(self, results_data, parent=None):
        super().__init__(parent)

        # Load UI
        ui_file_path = os.path.join(os.path.dirname(__file__), "..", "forms", "test_completion.ui")
        ui_file = QFile(ui_file_path)
        if not ui_file.open(QFile.ReadOnly):
            print(f"Cannot open {ui_file_path}: {ui_file.errorString()}")
            return

        loader = QUiLoader()
        # Do not pass 'self' to loader.load() when the root widget in the .ui file
        # is the same type as this class (QDialog), otherwise it creates a QDialog inside a QDialog.
        # But since we inherit from QDialog, loading it into self might be tricky with QUiLoader.
        # Let's extract its layout and set it to self.
        ui_widget = loader.load(ui_file)
        ui_file.close()

        # Steal the layout from the loaded widget
        layout = ui_widget.layout()
        # Reparent layout to self
        self.setLayout(layout)

        self.setWindowTitle("Test Completed")
        self.setFixedSize(900, 600)

        # Bind UI elements using self since the widgets are now children of self's layout
        self.frame_pcb1 = self.findChild(QFrame, "frame_pcb1")
        self.frame_pcb2 = self.findChild(QFrame, "frame_pcb2")
        self.lbl_pcb1_sn = self.findChild(QLabel, "lbl_pcb1_sn")
        self.lbl_pcb2_sn = self.findChild(QLabel, "lbl_pcb2_sn")
        self.lbl_pcb1_status = self.findChild(QLabel, "lbl_pcb1_status")
        self.lbl_pcb2_status = self.findChild(QLabel, "lbl_pcb2_status")
        self.btn_close = self.findChild(QPushButton, "btn_close")

        # Connect close button
        self.btn_close.clicked.connect(self.accept)

        # Initialize UI based on results
        self._init_ui(results_data)

        # Set up auto-close timer (120 seconds = 120000 ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.accept)
        self.timer.start(120000)

    def _init_ui(self, results_data):
        if 1 in results_data:
            self.frame_pcb1.show()
            self._configure_pcb_frame(
                self.frame_pcb1,
                self.lbl_pcb1_sn,
                self.lbl_pcb1_status,
                results_data[1]["sn"],
                results_data[1]["status"]
            )
        else:
            self.frame_pcb1.hide()

        if 2 in results_data:
            self.frame_pcb2.show()
            self._configure_pcb_frame(
                self.frame_pcb2,
                self.lbl_pcb2_sn,
                self.lbl_pcb2_status,
                results_data[2]["sn"],
                results_data[2]["status"]
            )
        else:
            self.frame_pcb2.hide()

    def _configure_pcb_frame(self, frame, lbl_sn, lbl_status, sn, status):
        lbl_sn.setText(f"SN: {sn}")
        lbl_status.setText(status)

        # Dark green / dark red background depending on PASS / FAIL
        if status == "PASS":
            bg_color = "#2e7d32"
        else:
            bg_color = "#c62828"

        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 10px;
            }}
            QLabel {{
                color: white;
                background: transparent;
                border: none;
            }}
            QLabel#lbl_pcb1_title, QLabel#lbl_pcb2_title {{
                font-size: 38px;
                font-weight: bold;
            }}
            QLabel#lbl_pcb1_sn, QLabel#lbl_pcb2_sn {{
                font-size: 26px;
                font-weight: normal;
            }}
            QLabel#lbl_pcb1_status, QLabel#lbl_pcb2_status {{
                font-size: 140px;
                font-weight: bold;
            }}
        """)
