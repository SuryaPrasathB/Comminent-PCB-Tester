from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QVBoxLayout, QAbstractItemView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent

from serial.tools import list_ports

from db_utils import load_projects, load_test_cases
from test_runner import TestRunner
from raw_serial_driver import RawSerial
from config import SLAVE_DEVICES

from logs import logger  


class ExecutionController(QWidget):
    def __init__(self, parent_tab: QWidget):
        super().__init__(parent_tab)

        print("[EXEC] ExecutionController __init__ called")
        logger.info("ExecutionController initialized")  

        self.parent_tab = parent_tab
        self.runner = None
        self.raw_serial = None

        self._loaded_project = None

        self.load_ui()
        self.connect_signals()
        self.refresh_projects()

    # -------------------------------------------------
    def showEvent(self, event):
        print("[EXEC] Execution tab activated (showEvent)")
        logger.info("Execution tab activated (showEvent)")  
        super().showEvent(event)

    # -------------------------------------------------
    def load_ui(self):
        import os

        print("[EXEC] load_ui() called")
        logger.info("Execution UI load started")  

        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "execution.ui")

        print(f"[EXEC] Loading UI from: {ui_path}")
        logger.info(f"Loading execution UI from {ui_path}")  

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Unable to open execution.ui: {ui_path}")  
            raise RuntimeError(f"Unable to open/read ui device: {ui_path}")

        self.ui = loader.load(ui_file, self.parent_tab)
        ui_file.close()

        if not self.ui:
            logger.error("Failed to load execution.ui")  
            raise RuntimeError("Failed to load execution.ui")

        old_layout = self.parent_tab.layout()
        if old_layout:
            QWidget().setLayout(old_layout)

        layout = QVBoxLayout(self.parent_tab)
        layout.addWidget(self.ui)
        layout.setStretch(0, 1)
        self.parent_tab.setLayout(layout)

        # ---- Widgets ----
        self.cmb_projects = self.ui.comboBox_projects
        self.cmb_comPort = self.ui.comboBox_comPort
        self.txt_pcb_serial = self.ui.lineEdit_pcbSerial
        self.table_results = self.ui.tableWidget_results

        self.btn_start = self.ui.pushButton_start
        self.btn_stop = self.ui.pushButton_stop
        self.btn_reset = self.ui.pushButton_reset
        self.btn_run_one = self.ui.pushButton_runOne

        # =================================================
        # TABLE BEHAVIOR
        # =================================================
        self.table_results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_results.setSelectionMode(QAbstractItemView.SingleSelection)

        self.table_results.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #cce5ff;
                color: black;
            }
        """)

        # Initial COM scan
        self._load_com_ports()

        # 🔴 Install event filters (ONLY CHANGE)
        self.cmb_comPort.installEventFilter(self)
        self.cmb_projects.installEventFilter(self)

        print("[EXEC] Execution UI loaded successfully")
        logger.info("Execution UI loaded successfully")  

    # -------------------------------------------------
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:

            if obj == self.cmb_comPort:
                print("[EXEC] COM dropdown clicked → rescanning ports")
                logger.info("COM dropdown clicked → rescanning ports")  
                self._load_com_ports()

            elif obj == self.cmb_projects:
                print("[EXEC] Project dropdown clicked → refreshing projects")
                logger.info("Project dropdown clicked → refreshing projects")  
                self.refresh_projects()

        return super().eventFilter(obj, event)

    # -------------------------------------------------
    def _load_com_ports(self):
        print("[EXEC] Scanning available COM ports...")
        logger.info("Scanning available COM ports")  

        self.cmb_comPort.blockSignals(True)
        self.cmb_comPort.clear()
        self.cmb_comPort.addItem("-- Select COM --")

        ports = list_ports.comports()
        for p in ports:
            print(f"[EXEC] Found COM port: {p.device}")
            logger.info(f"Found COM port: {p.device}")  
            self.cmb_comPort.addItem(p.device)

        self.cmb_comPort.blockSignals(False)

    # -------------------------------------------------
    def connect_signals(self):
        print("[EXEC] Connecting signals")
        logger.info("Connecting Execution tab signals")  

        self.cmb_projects.currentIndexChanged.connect(self.load_selected_project)
        self.btn_start.clicked.connect(self.start_tests)
        self.btn_stop.clicked.connect(self.stop_tests)
        self.btn_reset.clicked.connect(self.reset_table)
        self.btn_run_one.clicked.connect(self.run_single_test)
        self.cmb_comPort.currentTextChanged.connect(self.on_com_selected)

    # -------------------------------------------------
    def on_com_selected(self, com):
        if com.startswith("--"):
            return
        print(f"[EXEC] COM selected: {com}")
        logger.info(f"COM selected: {com}")  

    # -------------------------------------------------
    def refresh_projects(self):
        print("[EXEC] Refreshing project list")
        logger.info("Refreshing project list")  

        current = self.cmb_projects.currentText()

        self.cmb_projects.blockSignals(True)
        self.cmb_projects.clear()
        self.cmb_projects.addItem("-- Select Project --")

        for p in load_projects():
            print(f"[EXEC] Found project: {p}")
            logger.info(f"Found project: {p}")  
            self.cmb_projects.addItem(p)

        self.cmb_projects.setCurrentText(current)
        self.cmb_projects.blockSignals(False)

    # -------------------------------------------------
    def load_selected_project(self):
        project_name = self.cmb_projects.currentText()
        print(f"[EXEC] Project selected: {project_name}")
        logger.info(f"Project selected: {project_name}")  

        if project_name.startswith("--"):
            return

        # 🔑 IMPORTANT: Only reload if project changed
        if project_name == self._loaded_project:
            print("[EXEC] Same project reselected → keeping existing results")
            logger.info("Same project reselected → UI not reset")
            return

        print("[EXEC] New project detected → loading fresh results")
        logger.info("New project detected → loading fresh results")

        test_cases = load_test_cases(project_name)

        logger.info(f"Loaded {len(test_cases)} enabled test cases")  
        self.populate_results_table(test_cases)

        # UPDATE Currently Loaded Project
        self._loaded_project = project_name

    # -------------------------------------------------
    def populate_results_table(self, test_cases):
        logger.info("Populating execution results table")  
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

            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    # -------------------------------------------------
    def start_tests(self):
        print("[EXEC] Start tests clicked")
        logger.info("Start tests clicked")  

        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()

        if project_name.startswith("--"):
            logger.warning("Start test aborted: project not selected")  
            QMessageBox.warning(self.ui, "Error", "Select project")
            return

        if com_port.startswith("--"):
            logger.warning("Start test aborted: COM port not selected")  
            QMessageBox.warning(self.ui, "Error", "Select COM port")
            return

        qr = SLAVE_DEVICES["QR_SCANNER"]
        print(f"[EXEC] Command : {qr["read_cmd"]}")
        cmd_str = qr["read_cmd"]  # "015404"
        
        raw = RawSerial(port=com_port)
        pcb_serial_bytes = raw.write_read(cmd_str)  # raw.write_read(cmd_bytes, rx_len=256)
        raw.close()
        # Convert bytes → string
        pcb_serial_num = pcb_serial_bytes.decode(errors="ignore").strip()

        print(f"[EXEC] pcb_serial_num : {pcb_serial_num}")
        logger.info(f"[INFO] pcb_serial_num : {pcb_serial_num}")
        
        #pcb_serial_num = "LSCS1234"
        
        if pcb_serial_num == "NG":
            logger.warning("QR code read Task is failed")
            QMessageBox.warning(self.ui, "Error", "QR code read task is failed")
            return

        self.txt_pcb_serial.setText(pcb_serial_num)

        test_cases = load_test_cases(project_name)

        start_row = self.table_results.currentRow()
        if start_row < 0 or start_row == self.table_results.rowCount() - 1:
            #if start_row < 0:
            start_row = 0

        # ✅ CLEAR FROM START ROW TILL END
        logger.info(
            f"Starting test execution | Project={project_name}, COM={com_port}, StartRow={start_row}"
        )

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
        logger.info("TestRunner thread started")

    # -------------------------------------------------
    def run_single_test(self):
        logger.info("Run single test requested")

        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()
        row = self.table_results.currentRow()

        if project_name.startswith("--") or row < 0:
            logger.warning("Run single test aborted: project or row not selected")
            QMessageBox.warning(self.ui, "Error", "Select project and row")
            return

        if com_port.startswith("--"):
            logger.warning("Run single test aborted: COM port not selected")
            QMessageBox.warning(self.ui, "Error", "Select COM port")
            return

            # ✅ CLEAR ONLY SELECTED ROW
        self.clear_results_from_row(row)

        pcb_serial = self.txt_pcb_serial.text().strip() or "SINGLE_RUN"
        test_cases = load_test_cases(project_name)

        logger.info(
            f"Starting single test | Project={project_name}, Row={row + 1}, COM={com_port}"
        )

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

    # -------------------------------------------------
    def stop_tests(self):
        if self.runner:
            logger.warning("Stop tests requested by user")
            self.runner.stop()

    # -------------------------------------------------
    def reset_table(self):
        logger.info("Resetting execution result table")
        for row in range(self.table_results.rowCount()):
            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    # -------------------------------------------------
    def update_ui_row(self, data):
        sn = data["sn"]
        logger.info(f"Updating UI for test SN={sn}")

        for row in range(self.table_results.rowCount()):
            if row + 1 == sn:
                # --- AC Phase Voltages ---
                if "r_v" in data:
                    self.table_results.setItem(row, 7, QTableWidgetItem(str(data["r_v"])))
                if "y_v" in data:
                    self.table_results.setItem(row, 8, QTableWidgetItem(str(data["y_v"])))
                if "b_v" in data:
                    self.table_results.setItem(row, 9, QTableWidgetItem(str(data["b_v"])))

                # --- DC Measurements ---
                self.table_results.setItem(row, 10, QTableWidgetItem(str(data["measured_v"])))
                self.table_results.setItem(row, 11, QTableWidgetItem(str(data["measured_i"])))

                # --- Result ---
                self.table_results.setItem(row, 12, QTableWidgetItem(data["result"]))

                logger.info(
                    f"Result updated | SN={sn}, Result={data['result']}"
                )
                break

    # -------------------------------------------------
    def on_test_error(self, message):
        logger.error(f"Test execution error: {message}")
        QMessageBox.critical(self.ui, "Communication Error", message)

    # -------------------------------------------------
    def on_tests_finished(self, status):
        if status == "success":
            print("[EXEC] All tests completed.")
            logger.info("All tests completed")
            QMessageBox.information(self.ui, "Test Completed", "All tests have been completed successfully.")
        elif status == "error":
            print("[EXEC] All tests completed.")
            logger.info("All tests completed")
            QMessageBox.information(self.ui, "Test Completed", "All tests have been completed successfully.")
        elif status == "stop_requested":
            print("[EXEC] All tests completed.")
            logger.info("All tests completed")
            QMessageBox.information(self.ui, "Test Completed", "All tests have been completed successfully.")

    # -------------------------------------------------
    def clear_results_from_row(self, start_row: int):
        """
        Clear result columns (7–12) starting from start_row till end
        """

        logger.info(f"Clearing results from row {start_row + 1}")
        for row in range(start_row, self.table_results.rowCount()):
            for col in range(7, 13):
                self.table_results.setItem(row, col, QTableWidgetItem(""))

    # -------------------------------------------------
    def highlight_running_row(self, sn: int):
        """
        Highlight currently running test row
        sn is 1-based (from DB / test case)
        """
        logger.info(f"Highlighting running test SN={sn}")

        row = sn - 1

        if row < 0 or row >= self.table_results.rowCount():
            return

        # Select row
        self.table_results.setCurrentCell(row, 0)
        self.table_results.selectRow(row)

        # Ensure visible
        self.table_results.scrollToItem(
            self.table_results.item(row, 0),
            QAbstractItemView.PositionAtCenter
        )
