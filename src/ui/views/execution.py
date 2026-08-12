import os
import time
import threading
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QMessageBox, QAbstractItemView, QVBoxLayout, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent, Qt, QTimer, QObject, Signal

from serial.tools import list_ports

from src.core.db_utils import load_projects, load_test_cases
from src.core.test_runner import TestRunner
from src.core.drivers.raw_serial_driver import RawSerial
from src.core.config import SLAVE_DEVICES, SIMULATION_MODE, START_PUSH_BUTTON_POLLING_FEATURE

from src.core.logger import logger
from src.ui.icons import IconHelper


class StartPollerSignals(QObject):
    start_signal = Signal()
    finished = Signal()

_poller_signal_refs = []

class StartPoller:
    def __init__(self, port, slave_id, coil_addr):
        self.signals = StartPollerSignals()
        _poller_signal_refs.append(self.signals)
        self.port = port
        self.slave_id = slave_id
        self.coil_addr = coil_addr
        self.running = True
        self.stop_event = threading.Event()
        self.client = None
        self.t_name = "Unknown"
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self):
        self._thread.start()
        
    def stop(self):
        self.running = False
        self.stop_event.set()

    def wait(self, timeout=None):
        if timeout:
            self._thread.join(timeout / 1000.0)
            return not self._thread.is_alive()
        else:
            self._thread.join()
            return True

    def isRunning(self):
        return self._thread.is_alive()

    def _run_loop(self):
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
                        try:
                            self.signals.start_signal.emit()
                        except RuntimeError:
                            pass # Object was safely deleted
                        self.running = False
                        break

                except Exception as e:
                    # Log error periodically if desired, but don't spam
                    pass

                # Increased sleep for bus stability, interruptible
                if self.stop_event.wait(1.0):
                    break

        except Exception as e:
            logger.error(f"Error in StartPoller: {e}")
            
        logger.info(f"StartPoller [{self.t_name}] : STOPPED on {self.port}")
        try:
            self.signals.finished.emit()
        except RuntimeError:
            pass

    def stop(self):
        logger.info(f"StartPoller [{self.t_name}] : Stop requested")
        self.running = False
        self.stop_event.set()


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
        self.refresh_projects()

    # =========================================================================
    def load_ui(self):
        loader = QUiLoader()
        from src.core.paths import get_resource_path
        ui_path = get_resource_path("src/ui/forms/execution.ui")

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
            if obj == self.cmb_projects:
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


    # =========================================================================
    # LOGIC
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

        if getattr(self, '_is_starting', False):
            return
        
        if self.runner and self.runner.isRunning():
            logger.warning("Start clicked while TestRunner already running")
            return

        self._is_starting = True
        try:
            self._do_start_tests()
        finally:
            self._is_starting = False

    def _do_start_tests(self):
        project_name = self.cmb_projects.currentText()
        from src.ui.settings_manager import SettingsManager
        com_port = SettingsManager().get_setting("plc_settings", {}).get("com_port", "")

        if project_name.startswith("--"):
            logger.warning("Start aborted: project not selected")
            QMessageBox.warning(self, "Error", "Select project")
            return

        if not com_port or com_port.startswith("--"):
            logger.warning("Start aborted: COM port not configured")
            QMessageBox.warning(self, "Error", "Configure PLC COM port in Settings first.")
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
            if not sn1: 
                fail_msgs.append("PCB 1 QR Scanner failed (No Response)")
            elif "NG" in sn1.upper():
                fail_msgs.append("QR scanning failed for PCB 1, check QR Code.")

            if not sn2: 
                fail_msgs.append("PCB 2 QR Scanner failed (No Response)")
            elif "NG" in sn2.upper():
                fail_msgs.append("QR scanning failed for PCB 2, check QR Code.")

            if fail_msgs:
                logger.warning("QR read failed or NG received")
                QMessageBox.warning(self, "QR Error", "\n".join(fail_msgs) + "\n\nTip: Check cables, verify the QR is readable, or try 'Reset Bus' if hardware is unresponsive.")
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
        # CLEANUP OLD RUNNER (PURE PYTHON NOW, NO DELETE LATER)
        # =====================================================
        if self.runner:
            if self.runner.isRunning():
                self.runner.stop()
            self.runner = None

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

        self.runner.signals.running_sn_signal.connect(self.highlight_running_row, Qt.QueuedConnection)
        self.runner.signals.result_signal.connect(self.update_ui_row, Qt.QueuedConnection)
        self.runner.signals.finished_signal.connect(self.on_tests_finished, Qt.QueuedConnection)
        self.runner.signals.error_signal.connect(self.on_test_error, Qt.QueuedConnection)
        self.runner.signals.safety_stop_signal.connect(self.show_safety_popup, Qt.QueuedConnection)

        self._set_running_state(True)

        self.runner.start()
        logger.info("TestRunner thread started")

    # -------------------------------------------------
    def run_selected_test(self, table):
        logger.info("Run selected test clicked")
        
        if getattr(self, '_is_starting', False):
            return

        if self.runner and self.runner.isRunning():
            logger.warning("Run Selected clicked while TestRunner already running")
            QMessageBox.warning(self, "Warning", "A test is already running. Please wait or stop it first.")
            return
            
        self._is_starting = True
        try:
            self._do_run_selected_test(table)
        finally:
            self._is_starting = False

    def _do_run_selected_test(self, table):
        project_name = self.cmb_projects.currentText()
        from src.ui.settings_manager import SettingsManager
        com_port = SettingsManager().get_setting("plc_settings", {}).get("com_port", "")

        if project_name.startswith("--"):
            QMessageBox.warning(self, "Error", "Select project")
            return

        if not com_port or com_port.startswith("--"):
            QMessageBox.warning(self, "Error", "Configure PLC COM port in Settings first.")
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
        
        fail_msgs = []
        if "NG" in sn1.upper():
            fail_msgs.append("QR scanning failed for PCB 1, check QR Code.")
        if "NG" in sn2.upper():
            fail_msgs.append("QR scanning failed for PCB 2, check QR Code.")
            
        if fail_msgs:
            QMessageBox.warning(self, "QR Error", "\n".join(fail_msgs) + "\n\nCannot run test with invalid QR code.")
            return

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

        # =====================================================
        # CLEANUP OLD RUNNER (CRITICAL TO PREVENT CRASHES)
        # =====================================================
        # CLEANUP OLD RUNNER (PURE PYTHON NOW, NO DELETE LATER)
        # =====================================================
        if self.runner:
            if self.runner.isRunning():
                self.runner.stop()
            self.runner = None

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

        self.runner.signals.running_sn_signal.connect(
            lambda sn: self.highlight_running_row(sn, table), Qt.QueuedConnection
        )
        self.runner.signals.result_signal.connect(self.update_ui_row, Qt.QueuedConnection)
        self.runner.signals.finished_signal.connect(self.on_tests_finished, Qt.QueuedConnection)
        self.runner.signals.error_signal.connect(self.on_test_error, Qt.QueuedConnection)
        self.runner.signals.safety_stop_signal.connect(self.show_safety_popup, Qt.QueuedConnection)

        self._set_running_state(True)
        self.runner.start()

    # -------------------------------------------------
    def _read_qr(self, device_key, default_com_port):
        try:
            from src.ui.settings_manager import SettingsManager
            settings = SettingsManager().get_setting("qr_scanners", {})
            com_port = settings.get("scanner_1_port" if device_key == "QR_SCANNER_1" else "scanner_2_port")
            
            if not com_port:
                raise Exception(f"No COM port configured for {device_key}")

            qr = SLAVE_DEVICES[device_key]
            print(f"[QR] Reading {qr['display_name']} on {com_port} → CMD {qr['read_cmd']}")

            from src.core.drivers.modbus_manager import ModbusManager
            scanner_baudrate = qr.get("baudrate", 115200)
            mb = ModbusManager.get_client(port=com_port, baudrate=scanner_baudrate)
            data = mb.send_raw_receive(qr["read_cmd"], delay=2.5, baudrate=scanner_baudrate)
            
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
            from src.ui.settings_manager import SettingsManager
            com_port = SettingsManager().get_setting("plc_settings", {}).get("com_port", "")
            if not com_port or com_port.startswith("--"):
                QMessageBox.warning(self, "Error", "Configure PLC COM port in Settings first to reset PLC")
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
    def update_ui_row(self, sn: int, pcb_index: int, rv: str, yv: str, bv: str, measured_v: float, measured_i: float, result: str):
        row = sn - 1

        if pcb_index == 1:
            table = self.table_results_1
        elif pcb_index == 2:
            table = self.table_results_2
        else:
            return

        if 0 <= row < table.rowCount():
            # Apply color mapping
            

            # --- Update Table Items ---
            rv_item = QTableWidgetItem(rv)
            yv_item = QTableWidgetItem(yv)
            bv_item = QTableWidgetItem(bv)
            
            table.setItem(row, 7, rv_item)
            table.setItem(row, 8, yv_item)
            table.setItem(row, 9, bv_item)
            
            meas_v_item = QTableWidgetItem(f"{measured_v:.3f}")
            meas_i_item = QTableWidgetItem(f"{measured_i:.3f}")

            meas_v_item.setTextAlignment(Qt.AlignCenter)
            meas_i_item.setTextAlignment(Qt.AlignCenter)

            table.setItem(row, 10, meas_v_item)
            table.setItem(row, 11, meas_i_item)

            res_item = QTableWidgetItem(result)
            res_item.setTextAlignment(Qt.AlignCenter)

            if result.startswith("Pass"):
                res_item.setForeground(Qt.darkGreen)
            elif result == "Fail":
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
                    if hasattr(self, 'completion_view') and self.completion_view is not None:
                        try:
                            self.completion_view.deleteLater()
                        except RuntimeError:
                            pass
                    self.completion_view = TestCompletionDialog(popup_results, self.ui)
                    self.completion_view.exec_()
                else:
                    msg = QMessageBox(self.ui)
                    msg.setIcon(QMessageBox.Information)
                    msg.setWindowTitle("Test Completed")
                    msg.setText("All tests have been completed successfully.\nReports generated.")
                    msg.exec_()
                    msg.deleteLater()

            self._start_polling()

        elif status == "error":
            print("[EXEC] on_tests_finished : error")
            logger.info("[EXEC] on_tests_finished : error")
            msg = QMessageBox(self.ui)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Test Failed")
            msg.setText("Error occurred during test execution.")
            msg.exec_()
            msg.deleteLater()
            self._start_polling()
        elif status == "stop_requested":
            print("[EXEC] on_tests_finished : stopped")
            logger.info("[EXEC] on_tests_finished : stopped")
            msg = QMessageBox(self.ui)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Test Completed")
            msg.setText("All tests have been stopped successfully.")
            msg.exec_()
            msg.deleteLater()
            self._start_polling()


    # -------------------------------------------------
    def on_test_error(self, msg):
        msg_box = QMessageBox(self.ui)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Error")
        msg_box.setText(msg)
        msg_box.exec_()
        msg_box.deleteLater()

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
        msg = QMessageBox(self.ui)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Safety Alert")
        msg.setText(f"Operation Stopped!\n\nReason: {reason}")
        msg.setStandardButtons(QMessageBox.Close)
        msg.exec_()
        msg.deleteLater()

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
        if not START_PUSH_BUTTON_POLLING_FEATURE:
            return
            
        # If STOP button is enabled, it means a test is running.
        if self.btn_stop.isEnabled(): 
            return
            
        # Try to find label if not linked
        if not self.lbl_waiting:
            self.lbl_waiting = self.window().findChild(QWidget, "label_waiting_status")
        
        from src.ui.settings_manager import SettingsManager
        com_port = SettingsManager().get_setting("plc_settings", {}).get("com_port", "")
        if not com_port or com_port.startswith("--"): 
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
            self.poller.signals.start_signal.connect(self._handle_start_from_coil, Qt.QueuedConnection)
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
            self.poller = None

    def _handle_start_from_coil(self):
        logger.info("--- PHYSICAL START DETECTED ---")
        
        # Capture current poller before clearing it
        current_poller = self.poller
        self._stop_polling()
        
        if current_poller and current_poller.isRunning():
            # Wait asynchronously for the poller thread to finish before proceeding
            current_poller.signals.finished.connect(self._on_poller_finished_for_start, Qt.QueuedConnection)
        else:
            self._on_poller_finished_for_start()
            
    def _on_poller_finished_for_start(self):
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

