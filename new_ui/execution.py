import os
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QVBoxLayout, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent

from serial.tools import list_ports

from db_utils import load_projects, load_test_cases
from test_runner import TestRunner
from raw_serial_driver import RawSerial
from config import SLAVE_DEVICES

from logs import logger
from new_ui.icons import IconHelper

class ExecutionView(QWidget):
    def __init__(self, parent_stack=None):
        super().__init__()
        # self.parent_stack is just for reference if needed, though usually strict separation is better.

        logger.info("Initializing New ExecutionView")
        self.runner = None
        self._loaded_project = None

        self.load_ui()
        self.setup_icons()
        self.connect_signals()

        # Initial Setup
        self._load_com_ports()
        self.refresh_projects()

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "execution.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open execution.ui at {ui_path}")
            raise RuntimeError("Cannot open execution.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Layout Setup
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Widget Binding
        self.cmb_projects = self.findChild(QWidget, "comboBox_projects")
        self.cmb_comPort = self.findChild(QWidget, "comboBox_comPort")
        self.txt_pcb_serial = self.findChild(QWidget, "lineEdit_pcbSerial")
        self.table_results = self.findChild(QWidget, "tableWidget_results")

        self.btn_start = self.findChild(QWidget, "pushButton_start")
        self.btn_stop = self.findChild(QWidget, "pushButton_stop")
        self.btn_reset = self.findChild(QWidget, "pushButton_reset")
        self.btn_run_one = self.findChild(QWidget, "pushButton_runOne")

        # Table Config
        self.table_results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        # Event Filters for refreshing on click
        self.cmb_comPort.installEventFilter(self)
        self.cmb_projects.installEventFilter(self)

    def setup_icons(self):
        IconHelper.apply_icon(self.btn_start, "start", "white")
        IconHelper.apply_icon(self.btn_stop, "stop", "white")
        IconHelper.apply_icon(self.btn_reset, "refresh")
        IconHelper.apply_icon(self.btn_run_one, "start")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if obj == self.cmb_comPort:
                self._load_com_ports()
            elif obj == self.cmb_projects:
                self.refresh_projects()
        return super().eventFilter(obj, event)

    def connect_signals(self):
        self.cmb_projects.currentIndexChanged.connect(self.load_selected_project)
        self.btn_start.clicked.connect(self.start_tests)
        self.btn_stop.clicked.connect(self.stop_tests)
        self.btn_reset.clicked.connect(self.reset_table)
        self.btn_run_one.clicked.connect(self.run_single_test)

    # =========================================================================
    # LOGIC (Ported)
    # =========================================================================

    def _load_com_ports(self):
        logger.info("Scanning COM ports")
        self.cmb_comPort.blockSignals(True)
        self.cmb_comPort.clear()
        self.cmb_comPort.addItem("-- Select COM --")

        for p in list_ports.comports():
            self.cmb_comPort.addItem(p.device)

        self.cmb_comPort.blockSignals(False)

    def refresh_projects(self):
        logger.info("Refreshing projects")
        current = self.cmb_projects.currentText()

        self.cmb_projects.blockSignals(True)
        self.cmb_projects.clear()
        self.cmb_projects.addItem("-- Select Project --")

        for p in load_projects():
            self.cmb_projects.addItem(p)

        self.cmb_projects.setCurrentText(current)
        self.cmb_projects.blockSignals(False)

    def load_selected_project(self):
        project_name = self.cmb_projects.currentText()
        if project_name.startswith("--") or project_name == self._loaded_project:
            return

        logger.info(f"Loading project: {project_name}")
        test_cases = load_test_cases(project_name)
        self.populate_results_table(test_cases)
        self._loaded_project = project_name

    def populate_results_table(self, test_cases):
        self.table_results.setRowCount(0)
        for row, tc in enumerate(test_cases):
            self.table_results.insertRow(row)
            self.table_results.setItem(row, 0, QTableWidgetItem(tc['desc']))
            self.table_results.setItem(row, 1, QTableWidgetItem(tc['r']))
            self.table_results.setItem(row, 2, QTableWidgetItem(tc['y']))
            self.table_results.setItem(row, 3, QTableWidgetItem(tc['b']))
            self.table_results.setItem(row, 4, QTableWidgetItem(tc['n']))
            self.table_results.setItem(row, 5, QTableWidgetItem(tc['v']))
            self.table_results.setItem(row, 6, QTableWidgetItem(tc['i']))

            # Placeholders for results
            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    def start_tests(self):
        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()

        if project_name.startswith("--"):
            QMessageBox.warning(self, "Error", "Select project")
            return
        if com_port.startswith("--"):
            QMessageBox.warning(self, "Error", "Select COM port")
            return

        # QR Code Logic
        try:
            qr = SLAVE_DEVICES["QR_SCANNER"]
            cmd_str = qr["read_cmd"]
            raw = RawSerial(port=com_port)
            pcb_serial_bytes = raw.write_read(cmd_str)
            raw.close()
            pcb_serial_num = pcb_serial_bytes.decode(errors="ignore").strip()

            logger.info(f"QR Scanned: {pcb_serial_num}")

            if pcb_serial_num == "NG":
                QMessageBox.warning(self, "Error", "QR Read Failed")
                return

            self.txt_pcb_serial.setText(pcb_serial_num)

        except Exception as e:
            logger.error(f"QR Error: {e}")
            QMessageBox.warning(self, "Error", f"QR Scan Error: {e}")
            return

        test_cases = load_test_cases(project_name)
        start_row = self.table_results.currentRow()
        if start_row < 0: start_row = 0

        self.clear_results_from_row(start_row)

        self.runner = TestRunner(
            project_name=project_name,
            pcb_serial=pcb_serial_num,
            test_cases=test_cases,
            com_port=com_port,
            start_index=start_row,
            run_single=False
        )

        self.runner.running_sn_signal.connect(self.highlight_running_row)
        self.runner.result_signal.connect(self.update_ui_row)
        self.runner.finished_signal.connect(self.on_tests_finished)
        self.runner.error_signal.connect(self.on_test_error)
        self.runner.start()

    def run_single_test(self):
        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()
        row = self.table_results.currentRow()

        if row < 0 or project_name.startswith("--") or com_port.startswith("--"):
            QMessageBox.warning(self, "Error", "Select Project, COM, and Row")
            return

        self.clear_results_from_row(row)

        pcb_serial = self.txt_pcb_serial.text().strip() or "SINGLE_RUN"
        test_cases = load_test_cases(project_name)

        self.runner = TestRunner(
            project_name=project_name,
            pcb_serial=pcb_serial,
            test_cases=test_cases,
            com_port=com_port,
            start_index=row,
            run_single=True
        )
        self.runner.result_signal.connect(self.update_ui_row)
        self.runner.finished_signal.connect(self.on_tests_finished)
        self.runner.error_signal.connect(self.on_test_error)
        self.runner.start()

    def stop_tests(self):
        if self.runner:
            self.runner.stop()

    def reset_table(self):
        for row in range(self.table_results.rowCount()):
            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    def clear_results_from_row(self, start_row):
        for row in range(start_row, self.table_results.rowCount()):
            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    def update_ui_row(self, data):
        sn = data["sn"]
        for row in range(self.table_results.rowCount()):
            if row + 1 == sn:
                if "r_v" in data: self.table_results.setItem(row, 7, QTableWidgetItem(str(data["r_v"])))
                if "y_v" in data: self.table_results.setItem(row, 8, QTableWidgetItem(str(data["y_v"])))
                if "b_v" in data: self.table_results.setItem(row, 9, QTableWidgetItem(str(data["b_v"])))
                self.table_results.setItem(row, 10, QTableWidgetItem(str(data["measured_v"])))
                self.table_results.setItem(row, 11, QTableWidgetItem(str(data["measured_i"])))
                self.table_results.setItem(row, 12, QTableWidgetItem(data["result"]))
                break

    def highlight_running_row(self, sn):
        row = sn - 1
        if 0 <= row < self.table_results.rowCount():
            self.table_results.setCurrentCell(row, 0)
            self.table_results.scrollToItem(self.table_results.item(row, 0), QAbstractItemView.PositionAtCenter)

    def on_tests_finished(self, status):
        QMessageBox.information(self, "Done", f"Tests finished: {status}")

    def on_test_error(self, msg):
        QMessageBox.critical(self, "Error", msg)
