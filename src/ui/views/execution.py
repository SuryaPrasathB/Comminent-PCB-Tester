import os
import time
import threading
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QVBoxLayout, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent, Qt, QTimer, QThread, Signal

from serial.tools import list_ports

from src.core.db_utils import load_projects, load_test_cases
from src.core.test_runner import TestRunner
from src.core.drivers.raw_serial_driver import RawSerial
from src.core.config import SLAVE_DEVICES, SIMULATION_MODE

from src.core.logger import logger
from src.ui.icons import IconHelper


class StartPoller(QThread):
    start_signal = Signal()

    def __init__(self, port, slave_id, coil_addr):
        super().__init__()
        self.setObjectName("StartPoller")
        self.port = port
        self.slave_id = slave_id
        self.coil_addr = coil_addr
        self.running = True
        self.client = None
        self.t_name = "Unknown"

    def run(self):
        threading.current_thread().name = "StartPoller"
        self.t_name = threading.current_thread().name
        logger.info(f"StartPoller [{self.t_name}] : STARTED on {self.port}")
        try:
            from src.core.drivers.modbus_manager import ModbusManager
            self.client = ModbusManager.get_client(self.port, timeout=0.8)
            
            while self.running:
                try:
                    if not self.running:
                        break

                    # Use a local check to avoid race conditions during stop
                    coils = self.client.read_coils(self.slave_id, self.coil_addr, 1)
                    
                    if coils and coils[0] is True:
                        if not self.running: break
                        logger.info(f"StartPoller [{self.t_name}] : Coil {self.coil_addr} detected ACTIVE")
                        self.start_signal.emit()
                        self.running = False
                        break

                except Exception as e:
                    # Log error periodically if desired, but don't spam
                    pass

                # Increased sleep for bus stability
                self.msleep(1000) 

        except Exception as e:
            logger.error(f"StartPoller [{self.t_name}] failed: {e}")
        finally:
            logger.info(f"StartPoller [{self.t_name}] : EXITED")

    def stop(self):
        logger.info(f"StartPoller [{self.t_name}] : Stop requested")
        self.running = False


class ExecutionView(QWidget):
    def __init__(self, parent_stack=None):
        super().__init__()
        # self.parent_stack is just for reference if needed, though usually strict separation is better.

        logger.info("Initializing New ExecutionView (Dual PCB)")
        self.runner = None
        self.poller = None
        self._loaded_project = None
        
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._blink_label)

        self.load_ui()
        self.setup_icons()
        self.connect_signals()

        # Default UI state
        self._set_running_state(False)

        # Initial Setup
        self._load_com_ports()
        self.refresh_projects()

    # =========================================================================
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
        #self.btn_run_selected = self.findChild(QWidget, "pushButton_runSelected")
        self.btn_run_selected_1 = self.findChild(QWidget, "pushButton_runSelected_1")
        self.btn_run_selected_2 = self.findChild(QWidget, "pushButton_runSelected_2")

        self.lbl_waiting = None


        # runOne removed from UI


        # Configure Both Tables
        self.configure_table(self.table_results_1)
        self.configure_table(self.table_results_2)

        # Event Filters for refreshing on click
        self.cmb_comPort.installEventFilter(self)
        self.cmb_projects.installEventFilter(self)
    # =========================================================================
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
    # =========================================================================
    def setup_icons(self):
        IconHelper.apply_icon(self.btn_start, "start", "white")
        IconHelper.apply_icon(self.btn_stop, "stop", "white")
        IconHelper.apply_icon(self.btn_reset, "refresh")
        #IconHelper.apply_icon(self.btn_run_selected, "execution")
        IconHelper.apply_icon(self.btn_run_selected_1, "execution")
        IconHelper.apply_icon(self.btn_run_selected_2, "execution")
    # =========================================================================
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if obj == self.cmb_comPort:
                self._load_com_ports()
            elif obj == self.cmb_projects:
                self.refresh_projects()
        return super().eventFilter(obj, event)
    # =========================================================================
    def connect_signals(self):
        self.cmb_projects.currentIndexChanged.connect(self.load_selected_project)
        self.btn_start.clicked.connect(self.start_tests)
        self.btn_stop.clicked.connect(self.stop_tests)
        self.btn_reset.clicked.connect(self.reset_table)
        #self.btn_run_selected.clicked.connect(self.run_selected_test)
        self.btn_run_selected_1.clicked.connect(
            lambda: self.run_selected_test(self.table_results_1))
        self.btn_run_selected_2.clicked.connect(
            lambda: self.run_selected_test(self.table_results_2))
        
        self.cmb_comPort.currentIndexChanged.connect(self._on_com_port_changed)


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

        if SIMULATION_MODE:
            self.cmb_comPort.addItem("SIM_COM")

        self.cmb_comPort.blockSignals(False)
    # =========================================================================

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
    # =========================================================================

    def load_selected_project(self):
        project_name = self.cmb_projects.currentText()
        if project_name.startswith("--"):
            return

        logger.info(f"Loading project: {project_name}")
        # ==============================
        # 1️⃣ Reload test cases
        # ==============================
        test_cases = load_test_cases(project_name)
        self.populate_results_table(test_cases)

        # ==============================
        # 2️⃣ Clear PCB serial fields
        # ==============================
        self.txt_pcb_serial_1.clear()
        self.txt_pcb_serial_2.clear()

        # ==============================
        # 3️⃣ Reset runner reference
        # ==============================
        self.runner = None

        self._loaded_project = project_name
    # =========================================================================

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
    # -------------------------------------------------
    def start_tests(self):
        print("[EXEC] Start tests clicked")
        logger.info("Start tests clicked")

        if self.runner and self.runner.isRunning():
            logger.warning("Start clicked while TestRunner already running")
            return

        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()

        if project_name.startswith("--"):
            logger.warning("Start aborted: project not selected")
            QMessageBox.warning(self, "Error", "Select project")
            return

        if com_port.startswith("--"):
            logger.warning("Start aborted: COM port not selected")
            QMessageBox.warning(self, "Error", "Select COM port")
            return

        # Stop polling before starting any test
        self._stop_polling()

        # =====================================================

        # =====================================================
        # SAFETY PRE-CHECK & QR READ
        # =====================================================
        try:
            safety_err = self.check_safety_pre_start(com_port)
            if safety_err:
                self.show_safety_popup(safety_err)
                return

            # AUTO READ BOTH PCB SERIAL NUMBERS
            sn1 = self._read_qr("QR_SCANNER_1", com_port)
            sn2 = self._read_qr("QR_SCANNER_2", com_port)

            fail_msgs = []
            if not sn1: fail_msgs.append("PCB-1 QR Scanner failed")
            if not sn2: fail_msgs.append("PCB-2 QR Scanner failed")

            if fail_msgs:
                logger.warning("QR read failed")
                QMessageBox.warning(self, "QR Error", "\n".join(fail_msgs) + "\n\nTip: Check cables or try 'Reset Bus' if hardware is unresponsive.")
                return

        except Exception as e:
            logger.error(f"Hardware communication error during start: {e}")
            res = QMessageBox.question(
                self, "Hardware Error", 
                f"Hardware is not responding correctly:\n{e}\n\nWould you like to RESET the bus connection?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                from src.core.drivers.modbus_manager import ModbusManager
                ModbusManager.clear_client(com_port)
                QMessageBox.information(self, "Reset", "Bus connection cleared. Please try starting again.")
            return

        # Update UI
        self.txt_pcb_serial_1.setText(sn1)
        self.txt_pcb_serial_2.setText(sn2)

        pcb_serial_tuple = (sn1, sn2)

        # =====================================================
        # Determine Start Row (ONLY from Table 1)
        # =====================================================
        start_row = self.table_results_1.currentRow()

        if (
                start_row < 0 or
                start_row == self.table_results_1.rowCount() - 1
        ):
            start_row = 0

        logger.info(
            f"Starting execution | Project={project_name}, "
            f"COM={com_port}, StartRow={start_row}"
        )

        # =====================================================
        # CLEAR BOTH TABLES FROM start_row
        # =====================================================
        self.clear_results_from_row(start_row)

        # =====================================================
        # LOAD TEST CASES
        # =====================================================
        test_cases = load_test_cases(project_name)

        # =====================================================
        # CREATE RUNNER
        # =====================================================
        self.runner = TestRunner(
            project_name=project_name,
            pcb_serial=pcb_serial_tuple,
            test_cases=test_cases,
            com_port=com_port,
            start_index=start_row,
            active_pcbs=(1, 2),
            run_single=False
        )

        self.runner.running_sn_signal.connect(self.highlight_running_row)
        self.runner.result_signal.connect(self.update_ui_row)
        self.runner.finished_signal.connect(self.on_tests_finished)
        self.runner.error_signal.connect(self.on_test_error)
        self.runner.safety_stop_signal.connect(self.show_safety_popup)

        self._set_running_state(True)

        self.runner.start()
        logger.info("TestRunner thread started")

    # -------------------------------------------------
    def run_selected_test(self, table):
        project_name = self.cmb_projects.currentText()
        com_port = self.cmb_comPort.currentText()

        if project_name.startswith("--"):
            QMessageBox.warning(self, "Error", "Select project")
            return

        if com_port.startswith("--"):
            QMessageBox.warning(self, "Error", "Select COM port")
            return

        # Stop polling before starting any test
        self._stop_polling()

        # SAFETY PRE-CHECK
        safety_err = self.check_safety_pre_start(com_port)
        if safety_err:
            self.show_safety_popup(safety_err)
            return

        # Ensure we pass a tuple of serials, even for single run
        sn1 = self.txt_pcb_serial_1.text().strip() or "SINGLE_1"
        sn2 = self.txt_pcb_serial_2.text().strip() or "SINGLE_2"
        pcb_serials = (sn1, sn2)

        test_cases = load_test_cases(project_name)

        pcb_index = 1 if table is self.table_results_1 else 2

        # Get selected row from the given table
        selected_row = table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Warning", "Please select a row to run.")
            return

        # Clear only this row in this table
        for col in range(7, 13):
            table.setItem(selected_row, col, QTableWidgetItem(""))

        # Create runner
        self.runner = TestRunner(
            project_name=project_name,
            pcb_serial=pcb_serials, # Pass tuple
            test_cases=test_cases,
            com_port=com_port,
            start_index=selected_row,
            active_pcbs=(pcb_index,),
            run_single=True
        )

        # Connect signals (table-aware)
        self.runner.running_sn_signal.connect(
            lambda sn: self.highlight_running_row(sn, table)
        )
        self.runner.result_signal.connect(self.update_ui_row)

        self.runner.finished_signal.connect(self.on_tests_finished)
        self.runner.error_signal.connect(self.on_test_error)
        self.runner.safety_stop_signal.connect(self.show_safety_popup)

        self._set_running_state(True)
        self.runner.start()

    # -------------------------------------------------
    def _read_qr(self, device_key, com_port):
        try:
            qr = SLAVE_DEVICES[device_key]
            print(f"[QR] Reading {qr['display_name']} → CMD {qr['read_cmd']}")

            from src.core.drivers.modbus_manager import ModbusManager
            mb = ModbusManager.get_client(port=com_port)
            data = mb.send_raw_receive(qr["read_cmd"], delay=0.5, baudrate=115200)
            
            if not data:
                 return None

            serial = data.decode(errors="ignore").strip()
            print(f"[QR] {qr['display_name']} → {serial}")

            if serial == "" or serial.upper() == "NG":
                raise Exception("Invalid QR")

            return serial

        except Exception as e:
            logger.error(f"{device_key} read failed: {e}")
            return None

    # -------------------------------------------------

    def stop_tests(self):
        if self.runner:
            self.runner.stop()
        self._set_running_state(False)

    # -------------------------------------------------

    def reset_table(self):

        # Safety: do not allow reset while running
        if self.runner and self.runner.isRunning():
            QMessageBox.warning(self, "Warning", "Cannot reset while test is running.")
            return

        # Stop polling before starting any test
        self._stop_polling()

        # ==============================
        # 1️⃣ Reset UI tables
        # ==============================
        for table in [self.table_results_1, self.table_results_2]:
            if not table:
                continue

            for row in range(table.rowCount()):
                for col in range(7, 13):
                    table.setItem(row, col, QTableWidgetItem(""))

        # ==============================
        # 2️⃣ Reset ALL PLC coils
        # ==============================
        try:
            com_port = self.cmb_comPort.currentText()
            if com_port.startswith("--"):
                QMessageBox.warning(self, "Error", "Select COM port to reset PLC")
                return

            from src.core.drivers.modbus_manager import ModbusManager

            mb = ModbusManager.get_client(port=com_port)

            plc = SLAVE_DEVICES["PLC"]
            slave_id = plc["slave_id"]

            logger.info("Performing batch relay reset (Addresses 1-31)")
            try:
                # Reset relays 1-31 in one go
                reset_vals = [False] * 31
                mb.write_coils(slave_id, 1, reset_vals)
            except Exception as batch_e:
                logger.warning(f"Batch reset failed, falling back to sequential: {batch_e}")
                for name, addr in plc["coils"].items():
                    try:
                        if addr <= 31:
                            mb.write_coil(slave_id, addr, False)
                    except Exception: pass

            # mb.close() # DO NOT CLOSE SHARED CLIENT

            logger.info("All PLC coils reset successfully")
            QMessageBox.information(self, "Done", "Tables and PLC relays reset.")

            # Start polling after reset
            self._start_polling()

        except Exception as e:
            logger.error(f"PLC Reset failed: {e}")
            QMessageBox.warning(self, "Error", f"PLC Reset failed:\n{e}")

    # -------------------------------------------------

    def clear_results_from_row(self, start_row):
        for table in [self.table_results_1, self.table_results_2]:
            if not table: continue
            for row in range(start_row, table.rowCount()):
                for col in range(7, 13):
                    table.setItem(row, col, QTableWidgetItem(""))

    # -------------------------------------------------
    def update_ui_row(self, data: dict) -> None:
        if not isinstance(data, dict):
            return

        sn = data.get("sn")
        pcb_index = data.get("pcb_index")

        if sn is None or pcb_index is None:
            logger.warning("update_ui_row: missing sn or pcb_index")
            return

        table = (
            self.table_results_1
            if pcb_index == 1
            else self.table_results_2
        )

        self._update_single_table(table, sn, data)

    # -------------------------------------------------

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

    # -------------------------------------------------
    def highlight_running_row(self, sn, table=None):
        row = sn - 1

        tables = [table] if table else [self.table_results_1, self.table_results_2]

        for t in tables:
            if 0 <= row < t.rowCount():
                t.setCurrentCell(row, 0)
                t.scrollToItem(t.item(row, 0), QAbstractItemView.PositionAtCenter)

    # -------------------------------------------------
    def _set_running_state(self, running: bool):
        """
        running = True  → test is running
        running = False → test is stopped / finished
        """

        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_reset.setEnabled(not running)

    def on_tests_finished(self, status):
        self._set_running_state(False)

        # Determine active PCBs and project
        project_name = ""
        pcb_serials = []
        active_pcbs = []

        if self.runner:
            project_name = self.runner.project_name
            pcb_serials = self.runner.pcb_serials
            active_pcbs = self.runner.active_pcbs

        if status == "success":
            print("[EXEC] All tests completed.")
            logger.info("All tests completed")

            # --- Auto Report Export ---
            try:
                from src.core.report_generator import ReportGenerator
                from src.core.report_uploader import ReportUploader
                from src.core.db_utils import get_test_results
                from src.ui.views.test_completion import TestCompletionDialog

                export_folder = None

                # Dictionary to hold data for the test completion dialog
                popup_results = {}

                for pcb_idx in active_pcbs:
                    try:
                        # pcb_serials is tuple/list, 0-indexed. pcb_idx is 1-based (1 or 2).
                        if pcb_idx > len(pcb_serials):
                            logger.warning(f"PCB Index {pcb_idx} out of range for serials {pcb_serials}")
                            continue

                        sn = pcb_serials[pcb_idx - 1]
                        if not sn: continue

                        # 1. Calculate Status
                        results = get_test_results(project_name, sn)

                        all_passed = True
                        if not results:
                            # No results?
                            all_passed = False
                        else:
                            for r in results:
                                if "Pass" not in str(r.get("result", "")):
                                    all_passed = False
                                    break

                        overall = "PASS" if all_passed else "FAIL"
                        popup_results[pcb_idx] = {"sn": sn, "status": overall}

                        # 2. Generate Report
                        folder = ReportGenerator.generate_report(project_name, sn, overall)
                        if folder:
                            export_folder = folder

                    except Exception as e_pcb:
                        logger.error(f"Failed to generate report for PCB {pcb_idx}: {e_pcb}")

                # 3. Update Uploader
                if export_folder:
                    try:
                        ReportUploader().update_folder(export_folder)
                    except Exception as e_upl:
                        logger.error(f"Failed to update report uploader: {e_upl}")

            except Exception as e:
                logger.error(f"Report generation block failed: {e}")
            # --------------------------

            # Show the new Test Completion popup
            # Do not display if running a single test (Run Selected)
            is_run_single = getattr(self.runner, 'run_single', False) if self.runner else False
            
            if not is_run_single:
                if popup_results:
                    dialog = TestCompletionDialog(popup_results, self.ui)
                    dialog.exec_()
                else:
                    QMessageBox.information(self.ui, "Test Completed", "All tests have been completed successfully.\nReports generated.")

            self._start_polling()

        elif status == "error":
            print("[EXEC] on_tests_finished : error")
            logger.info("[EXEC] on_tests_finished : error")
            QMessageBox.information(self.ui, "Test Failed", "Error")
            self._start_polling()
        elif status == "stop_requested":
            print("[EXEC] on_tests_finished : stopped")
            logger.info("[EXEC] on_tests_finished : stopped")
            QMessageBox.information(self.ui, "Test Completed", "All tests have been stopped successfully.")
            self._start_polling()


    # -------------------------------------------------
    def on_test_error(self, msg):
        QMessageBox.critical(self, "Error", msg)

    # -------------------------------------------------
    def check_safety_pre_start(self, com_port):
        mb = None
        try:
            print(f"[SAFETY] Pre-check on {com_port}")

            if SIMULATION_MODE and com_port == "SIM_COM":
                return None

            from src.core.drivers.modbus_manager import ModbusManager
            
            # Temporary connection
            mb = ModbusManager.get_client(port=com_port)
            plc = SLAVE_DEVICES["PLC"]
            slave = plc["slave_id"]

            # Batch read coils 102, 103, 104
            # 102: PCB, 103: CURTAIN, 104: ESTOP
            # Start at 102, count 3
            bits = mb.read_coils(slave, 102, 3)
            
            if not bits or len(bits) < 3:
                return "Safety Sensors Read Failed"

            pcb_active = bits[0]      # 102
            curtain_active = bits[1]  # 103
            estop_active = bits[2]    # 104

            if not pcb_active:
                return "PCB Not Placed"
            
            if estop_active:
                return "Emergency Stop Active"
                
            if curtain_active:
                return "Curtain Sensor Active"
            
            return None
            
        except Exception as e:
            logger.error(f"Safety pre-check failed: {e}")
            return f"Safety Check Error: {e}"
        finally:
            # if mb: mb.close() # DO NOT CLOSE SHARED CLIENT
            pass

    def show_safety_popup(self, reason):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Safety Alert")
        msg.setText(f"Operation Stopped!\n\nReason: {reason}")
        msg.setStandardButtons(QMessageBox.Close)
        msg.exec()

    # =========================================================
    # POLLING LOGIC
    # =========================================================
    def _blink_label(self):
        if not self.lbl_waiting: return
        
        # We toggle between BLUE and TRANSPARENT text
        # Update style for header placement (14pt, margin-right 20px)
        STYLE_VISIBLE = "font-size: 14pt; font-weight: bold; color: #0078d7; margin-right: 20px;"
        STYLE_HIDDEN = "font-size: 14pt; font-weight: bold; color: transparent; margin-right: 20px;"
        
        current = self.lbl_waiting.styleSheet()
        if "transparent" in current:
            self.lbl_waiting.setStyleSheet(STYLE_VISIBLE)
        else:
            self.lbl_waiting.setStyleSheet(STYLE_HIDDEN)

    def _start_polling(self):
        # If STOP button is enabled, it means a test is running.
        if self.btn_stop.isEnabled(): 
            return
            
        # Try to find label if not linked
        if not self.lbl_waiting:
            self.lbl_waiting = self.window().findChild(QWidget, "label_waiting_status")
        
        com_port = self.cmb_comPort.currentText()
        if com_port.startswith("--"): 
            if self.lbl_waiting: self.lbl_waiting.setVisible(False)
            self.blink_timer.stop()
            return
            
        if not self.isVisible(): 
            self._stop_polling()
            return

        if self.poller:
            if self.poller.isRunning():
                return
            else:
                # Thread object exists but not running - cleanup
                self.poller = None
            
        if SIMULATION_MODE and com_port == "SIM_COM":
            return

        try:
            plc = SLAVE_DEVICES.get("PLC")
            if not plc: return
            
            slave_id = plc["slave_id"]
            start_coil = plc["coils"].get("START")
            
            if not start_coil: return
            
            self.poller = StartPoller(com_port, slave_id, start_coil)
            self.poller.start_signal.connect(self._handle_start_from_coil)
            self.poller.start()
            
            self.blink_timer.start(800)
            if self.lbl_waiting:
                STYLE_VISIBLE = "font-size: 14pt; font-weight: bold; color: #0078d7; margin-right: 20px;"
                self.lbl_waiting.setText("Waiting for START...")
                self.lbl_waiting.setStyleSheet(STYLE_VISIBLE)
                self.lbl_waiting.setVisible(True)

        except Exception as e:
            logger.error(f"Cannot start poller: {e}")


    def _stop_polling(self):
        self.blink_timer.stop()
        
        # Ensure label exists and hide it
        if not self.lbl_waiting:
            if self.window():
                self.lbl_waiting = self.window().findChild(QWidget, "label_waiting_status")

        if self.lbl_waiting: 
            self.lbl_waiting.setVisible(False)

        if self.poller:
            self.poller.stop()
            import time
            from PySide6.QtWidgets import QApplication
            timeout = time.time() + 5.0
            while self.poller.isRunning() and time.time() < timeout:
                QApplication.processEvents()
                time.sleep(0.1)
            if self.poller.isRunning():
                logger.warning("Poller did not stop in time. Leaving to OS.")
            self.poller = None

    def _handle_start_from_coil(self):
        logger.info("--- PHYSICAL START DETECTED ---")
        self._stop_polling()
        
        # Reset START Coil (Using QTimer to avoid blocking main thread and ensure separation)
        QTimer.singleShot(200, self._deferred_coil_reset_and_start)

    def _deferred_coil_reset_and_start(self):
        try:
            com_port = self.cmb_comPort.currentText()
            if not com_port.startswith("--"):
                from src.core.drivers.modbus_manager import ModbusManager
                mb = ModbusManager.get_client(port=com_port)
                plc = SLAVE_DEVICES.get("PLC")
                if plc:
                    slave_id = plc["slave_id"]
                    start_coil = plc["coils"].get("START")
                    if start_coil is not None:
                        logger.info(f"Resetting START Coil (Addr {start_coil})")
                        mb.write_coil(slave_id, start_coil, False)
        except Exception as e:
            logger.error(f"Failed to reset START Coil: {e}")

        # Final small delay before triggering tests to ensure bus is clear
        QTimer.singleShot(300, self.start_tests)

    def _on_com_port_changed(self):
        self._stop_polling()
        self._start_polling()

    def showEvent(self, event):
        super().showEvent(event)
        self._start_polling()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._stop_polling()
        
    def closeEvent(self, event):
        self._stop_polling()
        super().closeEvent(event)

