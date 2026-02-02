import os
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QVBoxLayout, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent, Qt

from serial.tools import list_ports

from src.core.db_utils import load_projects, load_test_cases
from src.core.test_runner import TestRunner
from src.core.drivers.raw_serial_driver import RawSerial
from src.core.config import SLAVE_DEVICES

from src.core.logger import logger
from src.ui.icons import IconHelper

class ExecutionView(QWidget):
    def __init__(self, parent_stack=None):
        super().__init__()
        # self.parent_stack is just for reference if needed, though usually strict separation is better.

        logger.info("Initializing New ExecutionView (Dual PCB)")
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
        ui_path = os.path.join(base_dir, "..", "forms", "execution.ui")

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

        # Dual PCB Inputs
        self.txt_pcb_serial_1 = self.findChild(QWidget, "lineEdit_pcbSerial_1")
        self.txt_pcb_serial_2 = self.findChild(QWidget, "lineEdit_pcbSerial_2")

        # Dual PCB Tables
        self.table_results_1 = self.findChild(QWidget, "tableWidget_results_1")
        self.table_results_2 = self.findChild(QWidget, "tableWidget_results_2")

        self.btn_start = self.findChild(QWidget, "pushButton_start")
        self.btn_stop = self.findChild(QWidget, "pushButton_stop")
        self.btn_reset = self.findChild(QWidget, "pushButton_reset")
        # runOne removed from UI

        # Configure Both Tables
        self.configure_table(self.table_results_1)
        self.configure_table(self.table_results_2)

        # Event Filters for refreshing on click
        self.cmb_comPort.installEventFilter(self)
        self.cmb_projects.installEventFilter(self)

    def configure_table(self, table):
        if not table: return
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setWordWrap(True)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Column Sizing
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Description
        for col in range(1, 12):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(12, QHeaderView.Stretch)  # Result

        # Styles
        table.setStyleSheet("""
            QTableWidget::item {
                padding-left: 10px;
                padding-right: 10px;
            }
            QTableWidget::item:selected {
                background-color: #0078d7;
                color: white;
                font-weight: bold;
            }
        """)

    def setup_icons(self):
        IconHelper.apply_icon(self.btn_start, "start", "white")
        IconHelper.apply_icon(self.btn_stop, "stop", "white")
        IconHelper.apply_icon(self.btn_reset, "refresh")

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

    # =========================================================================
    # LOGIC
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
        # Populate both tables
        for table in [self.table_results_1, self.table_results_2]:
            if not table: continue
            table.setRowCount(0)
            for row, tc in enumerate(test_cases):
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(tc['desc']))

                # Center align intermediate columns
                vals = [tc['r'], tc['y'], tc['b'], tc['n'], tc['v'], tc['i']]
                for i, val in enumerate(vals):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, i + 1, item)

                # Placeholders for results
                for col in range(7, 13):
                    item = QTableWidgetItem("")
                    if col < 12:
                        item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row, col, item)

    def start_tests(self):
        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()

        if project_name.startswith("--"):
            QMessageBox.warning(self, "Error", "Select project")
            return
        if com_port.startswith("--"):
            QMessageBox.warning(self, "Error", "Select COM port")
            return

        sn1 = self.txt_pcb_serial_1.text().strip()
        sn2 = self.txt_pcb_serial_2.text().strip()

        # Allow running if at least one SN is provided, or just default to empty
        if not sn1 and not sn2:
             QMessageBox.warning(self, "Error", "Enter at least one PCB Serial Number")
             return

        # Combine SNs for the runner (e.g. "SN1,SN2") or just pass primary
        # For now, we treat SN1 as primary for DB, but the UI shows both.
        # Ideally, we pass both to the runner.
        pcb_serial_combined = f"{sn1},{sn2}" if sn2 else sn1

        test_cases = load_test_cases(project_name)

        start_row = self.table_results_1.currentRow()
        if start_row < 0: start_row = 0

        self.clear_results_from_row(start_row)

        # NOTE: TestRunner is currently Single-PCB.
        # We will instantiate it, but in the future it needs to be updated to handle 2 PCBs.
        # For this UI task, we will mirror the outputs to both tables to demonstrate the layout.

        self.runner = TestRunner(
            project_name=project_name,
            pcb_serial=pcb_serial_combined,
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

    def stop_tests(self):
        if self.runner:
            self.runner.stop()

    def reset_table(self):
        for table in [self.table_results_1, self.table_results_2]:
            if not table: continue
            for row in range(table.rowCount()):
                for col in range(7, 13):
                    table.setItem(row, col, QTableWidgetItem(""))

    def clear_results_from_row(self, start_row):
        for table in [self.table_results_1, self.table_results_2]:
            if not table: continue
            for row in range(start_row, table.rowCount()):
                for col in range(7, 13):
                    table.setItem(row, col, QTableWidgetItem(""))

    def update_ui_row(self, data):
        # Data Format: {sn, r_v, y_v, ... result}
        # Ideally data should have 'pcb_index'

        sn = data.get("sn")
        if not sn: return

        # Update ONLY table 1 to avoid deceptive mirroring.
        # Once backend supports dual PCB, we can update table 2 based on pcb_index.
        self._update_single_table(self.table_results_1, sn, data)

    def _update_single_table(self, table, sn, data):
        if not table: return
        # table row is 0-indexed, sn is 1-indexed usually
        row = sn - 1
        if 0 <= row < table.rowCount():
            if "r_v" in data: table.setItem(row, 7, QTableWidgetItem(str(data["r_v"])))
            if "y_v" in data: table.setItem(row, 8, QTableWidgetItem(str(data["y_v"])))
            if "b_v" in data: table.setItem(row, 9, QTableWidgetItem(str(data["b_v"])))
            table.setItem(row, 10, QTableWidgetItem(str(data["measured_v"])))
            table.setItem(row, 11, QTableWidgetItem(str(data["measured_i"])))

            res_item = QTableWidgetItem(data["result"])
            # Optional: Color code result
            if data["result"] == "Pass":
                res_item.setForeground(Qt.darkGreen)
            elif data["result"] == "Fail":
                res_item.setForeground(Qt.red)

            table.setItem(row, 12, res_item)

    def highlight_running_row(self, sn):
        row = sn - 1
        # Sync Scroll Both (optional, but harmless to scroll empty table)
        for table in [self.table_results_1, self.table_results_2]:
            if not table: continue
            if 0 <= row < table.rowCount():
                table.setCurrentCell(row, 0)
                table.scrollToItem(table.item(row, 0), QAbstractItemView.PositionAtCenter)

    def on_tests_finished(self, status):
        QMessageBox.information(self, "Done", f"Tests finished: {status}")

    def on_test_error(self, msg):
        QMessageBox.critical(self, "Error", msg)
