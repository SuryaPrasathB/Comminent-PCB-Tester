import os
import serial.tools.list_ports
from PySide6.QtWidgets import QWidget, QMessageBox, QComboBox, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent

from src.core.drivers.modbus_driver import ModbusRTU
from src.core.drivers.raw_serial_driver import RawSerial
from src.core.config import SLAVE_DEVICES, VOLTAGE_TAPPINGS, CURRENT_TAPPINGS, NEUTRAL_OPTIONS, VLL_TO_TAP
from src.core.logger import logger
from src.ui.icons import IconHelper


class DebugView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New DebugView")

        self.modbus = None
        self.current_com = None
        self.main_contactor_on = False
        self.imp_test_pcb1_on = False
        self.imp_test_pcb2_on = False
        self.pcb2_enabled = False

        self.imp_relays = {
            "IMP1_R": False,
            "IMP1_Y": False,
            "IMP1_B": False,
            "IMP1_N": False,
            "IMP2_R": False,
            "IMP2_Y": False,
            "IMP2_B": False,
            "IMP2_N": False,
        }

        self.load_ui()
        self.setup_icons()
        self.populate_com_ports()
        self.populate_tappings()
        self.connect_signals()

    # -------------------------------------------------
    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "..", "forms", "debug.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open debug.ui at {ui_path}")
            raise RuntimeError("Cannot open debug.ui")

        # Load UI WITHOUT parent (important for centering)
        self.ui = loader.load(ui_file)
        ui_file.close()

        # ---------------- SCROLL AREA ----------------
        from PySide6.QtWidgets import QScrollArea, QHBoxLayout, QFrame

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background-color: #f8f9fa;")

        # ---------------- CENTERING CONTAINER ----------------
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #f8f9fa;")

        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(20, 20, 20, 20)

        container_layout.addStretch(1)
        container_layout.addWidget(self.ui)
        container_layout.addStretch(1)

        # Reasonable content width (same idea as old version)
        self.ui.setMinimumWidth(800)
        self.ui.setMaximumWidth(1100)

        self.scroll.setWidget(self.container)

        # ---------------- MAIN LAYOUT ----------------
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        self.setLayout(layout)

        # ================= Widget Bindings =================

        self.cmb_com = self.findChild(QComboBox, "comboBox_comPorts")

        self.cmb_r = self.findChild(QComboBox, "combo_r_voltage")
        self.cmb_y = self.findChild(QComboBox, "combo_y_voltage")
        self.cmb_b = self.findChild(QComboBox, "combo_b_voltage")
        self.cmb_n = self.findChild(QComboBox, "combo_neutral")

        # Two current taps
        self.cmb_i1 = self.findChild(QComboBox, "combo_current_1")
        self.cmb_i2 = self.findChild(QComboBox, "combo_current_2")

        self.btn_main = self.findChild(QWidget, "btn_main_contactor")
        self.btn_imp_test_pcb1 = self.findChild(QWidget, "btn_imp_test_pcb1")
        self.btn_imp_test_pcb2 = self.findChild(QWidget, "btn_imp_test_pcb2")
        self.btn_pcb2_enable = self.findChild(QWidget, "btn_pcb2_enable")

        self.btn_apply = self.findChild(QWidget, "btn_apply_taps")
        self.btn_reset = self.findChild(QWidget, "btn_reset_taps")

        # QR scanners
        self.btn_qr_1 = self.findChild(QWidget, "btn_read_qr_1")
        self.txt_qr_1 = self.findChild(QWidget, "txt_qr_1")
        self.btn_qr_2 = self.findChild(QWidget, "btn_read_qr_2")
        self.txt_qr_2 = self.findChild(QWidget, "txt_qr_2")

        # AC meters
        self.btn_read_r_v = self.findChild(QWidget, "btn_read_r_v")
        self.txt_r_v = self.findChild(QWidget, "txt_r_v")
        self.btn_read_y_v = self.findChild(QWidget, "btn_read_y_v")
        self.txt_y_v = self.findChild(QWidget, "txt_y_v")
        self.btn_read_b_v = self.findChild(QWidget, "btn_read_b_v")
        self.txt_b_v = self.findChild(QWidget, "txt_b_v")

        self.btn_read_vry = self.findChild(QWidget, "btn_read_vry")
        self.txt_vry = self.findChild(QWidget, "txt_vry")
        self.btn_read_vyb = self.findChild(QWidget, "btn_read_vyb")
        self.txt_vyb = self.findChild(QWidget, "txt_vyb")
        self.btn_read_vbr = self.findChild(QWidget, "btn_read_vbr")
        self.txt_vbr = self.findChild(QWidget, "txt_vbr")

        # Impedance meters (2x)
        self.btn_read_rn_r_1 = self.findChild(QWidget, "btn_read_rn_r_1")
        self.txt_rn_r_1 = self.findChild(QWidget, "txt_rn_r_1")
        self.btn_read_rn_r_2 = self.findChild(QWidget, "btn_read_rn_r_2")
        self.txt_rn_r_2 = self.findChild(QWidget, "txt_rn_r_2")

        self.btn_read_yn_r_1 = self.findChild(QWidget, "btn_read_yn_r_1")
        self.txt_yn_r_1 = self.findChild(QWidget, "txt_yn_r_1")
        self.btn_read_yn_r_2 = self.findChild(QWidget, "btn_read_yn_r_2")
        self.txt_yn_r_2 = self.findChild(QWidget, "txt_yn_r_2")

        self.btn_read_bn_r_1 = self.findChild(QWidget, "btn_read_bn_r_1")
        self.txt_bn_r_1 = self.findChild(QWidget, "txt_bn_r_1")
        self.btn_read_bn_r_2 = self.findChild(QWidget, "btn_read_bn_r_2")
        self.txt_bn_r_2 = self.findChild(QWidget, "txt_bn_r_2")

        # DC meters (2x)
        self.btn_read_dc_v_1 = self.findChild(QWidget, "btn_read_dc_v_1")
        self.txt_dc_v_1 = self.findChild(QWidget, "txt_dc_v_1")
        self.btn_read_dc_v_2 = self.findChild(QWidget, "btn_read_dc_v_2")
        self.txt_dc_v_2 = self.findChild(QWidget, "txt_dc_v_2")

        self.btn_read_dc_i_1 = self.findChild(QWidget, "btn_read_dc_i_1")
        self.txt_dc_i_1 = self.findChild(QWidget, "txt_dc_i_1")
        self.btn_read_dc_i_2 = self.findChild(QWidget, "btn_read_dc_i_2")
        self.txt_dc_i_2 = self.findChild(QWidget, "txt_dc_i_2")

        # PCB1 Impedance Relays
        self.btn_imp1_r = self.findChild(QWidget, "btn_imp1_r")
        self.btn_imp1_y = self.findChild(QWidget, "btn_imp1_y")
        self.btn_imp1_b = self.findChild(QWidget, "btn_imp1_b")
        self.btn_imp1_n = self.findChild(QWidget, "btn_imp1_n")

        # PCB2 Impedance Relays
        self.btn_imp2_r = self.findChild(QWidget, "btn_imp2_r")
        self.btn_imp2_y = self.findChild(QWidget, "btn_imp2_y")
        self.btn_imp2_b = self.findChild(QWidget, "btn_imp2_b")
        self.btn_imp2_n = self.findChild(QWidget, "btn_imp2_n")

        # Rescan COM on click
        self.cmb_com.installEventFilter(self)

    # -------------------------------------------------
    def setup_icons(self):
        IconHelper.apply_icon(self.btn_apply, "check", "white")
        IconHelper.apply_icon(self.btn_reset, "times", "black")

    # -------------------------------------------------
    def eventFilter(self, obj, event):
        if obj == self.cmb_com and event.type() == QEvent.MouseButtonPress:
            self.populate_com_ports()
        return super().eventFilter(obj, event)

    # -------------------------------------------------
    def populate_com_ports(self):
        self.cmb_com.blockSignals(True)
        self.cmb_com.clear()
        self.cmb_com.addItem("-- Select COM --")
        for p in serial.tools.list_ports.comports():
            self.cmb_com.addItem(p.device)
        self.cmb_com.blockSignals(False)

    # -------------------------------------------------
    def populate_tappings(self):
        self.cmb_r.addItems(VOLTAGE_TAPPINGS)
        self.cmb_y.addItems(VOLTAGE_TAPPINGS)
        self.cmb_b.addItems(VOLTAGE_TAPPINGS)
        self.cmb_n.addItems(NEUTRAL_OPTIONS)

        # 🔹 CHANGED: two current taps
        self.cmb_i1.addItems(CURRENT_TAPPINGS)
        self.cmb_i2.addItems(CURRENT_TAPPINGS)

    # -------------------------------------------------
    def connect_signals(self):

        # ================== APPLY / RESET ==================
        self.btn_apply.clicked.connect(self.apply_all_taps)
        self.btn_reset.clicked.connect(self.reset_all_relays)
        self.btn_main.clicked.connect(self.toggle_main_contactor)
        self.btn_imp_test_pcb1.clicked.connect(self.toggle_impedance_pcb1)
        self.btn_imp_test_pcb2.clicked.connect(self.toggle_impedance_pcb2)
        self.btn_pcb2_enable.clicked.connect(self.toggle_pcb2_enable)

        # ================== QR SCANNERS (2) ==================
        self.btn_qr_1.clicked.connect(lambda: self.read_qr_code("QR_SCANNER_1", self.txt_qr_1))
        self.btn_qr_2.clicked.connect(lambda: self.read_qr_code("QR_SCANNER_2", self.txt_qr_2))

        # ================== AC VOLTAGE (SINGLE METER) ==================
        self.btn_read_r_v.clicked.connect(lambda: self.read_modbus("r_n_v", self.txt_r_v))
        self.btn_read_y_v.clicked.connect(lambda: self.read_modbus("y_n_v", self.txt_y_v))
        self.btn_read_b_v.clicked.connect(lambda: self.read_modbus("b_n_v", self.txt_b_v))
        self.btn_read_vry.clicked.connect(lambda: self.read_modbus("r_y_v", self.txt_vry))
        self.btn_read_vyb.clicked.connect(lambda: self.read_modbus("y_b_v", self.txt_vyb))
        self.btn_read_vbr.clicked.connect(lambda: self.read_modbus("b_r_v", self.txt_vbr))

        # ================== IMPEDANCE METERS (2) ==================
        self.btn_read_rn_r_1.clicked.connect(lambda: self.read_modbus("imp_rn_1", self.txt_rn_r_1))
        self.btn_read_rn_r_2.clicked.connect(lambda: self.read_modbus("imp_rn_2", self.txt_rn_r_2))

        self.btn_read_yn_r_1.clicked.connect(lambda: self.read_modbus("imp_yn_1", self.txt_yn_r_1))
        self.btn_read_yn_r_2.clicked.connect(lambda: self.read_modbus("imp_yn_2", self.txt_yn_r_2))

        self.btn_read_bn_r_1.clicked.connect(lambda: self.read_modbus("imp_bn_1", self.txt_bn_r_1))
        self.btn_read_bn_r_2.clicked.connect(lambda: self.read_modbus("imp_bn_2", self.txt_bn_r_2))

        # ================== DC VOLTAGE METERS (2) ==================
        self.btn_read_dc_v_1.clicked.connect(lambda: self.read_modbus("dc_v_1", self.txt_dc_v_1))
        self.btn_read_dc_v_2.clicked.connect(lambda: self.read_modbus("dc_v_2", self.txt_dc_v_2))

        # ================== DC CURRENT METERS (2) ==================
        self.btn_read_dc_i_1.clicked.connect(lambda: self.read_modbus("dc_i_1", self.txt_dc_i_1))
        self.btn_read_dc_i_2.clicked.connect(lambda: self.read_modbus("dc_i_2", self.txt_dc_i_2))

        # PCB1 Impedance relays
        self.btn_imp1_r.clicked.connect(lambda: self.toggle_imp_relay("IMP1_R", self.btn_imp1_r))
        self.btn_imp1_y.clicked.connect(lambda: self.toggle_imp_relay("IMP1_Y", self.btn_imp1_y))
        self.btn_imp1_b.clicked.connect(lambda: self.toggle_imp_relay("IMP1_B", self.btn_imp1_b))
        self.btn_imp1_n.clicked.connect(lambda: self.toggle_imp_relay("IMP1_N", self.btn_imp1_n))

        # PCB2 relays
        self.btn_imp2_r.clicked.connect(lambda: self.toggle_imp_relay("IMP2_R", self.btn_imp2_r))
        self.btn_imp2_y.clicked.connect(lambda: self.toggle_imp_relay("IMP2_Y", self.btn_imp2_y))
        self.btn_imp2_b.clicked.connect(lambda: self.toggle_imp_relay("IMP2_B", self.btn_imp2_b))
        self.btn_imp2_n.clicked.connect(lambda: self.toggle_imp_relay("IMP2_N", self.btn_imp2_n))

    # =========================================================================

    def _get_modbus(self):
        com = self.cmb_com.currentText()
        if com.startswith("--"):
            raise RuntimeError("COM not selected")
        if self.modbus and self.current_com == com:
            return self.modbus
        if self.modbus:
            self.modbus.close()
        self.modbus = ModbusRTU(port=com)
        self.current_com = com
        return self.modbus

    # -------------------------------------------------
    def apply_all_taps(self):
        try:
            print("=== apply_all_taps(): START ===")

            mb = self._get_modbus()
            print("Modbus connection obtained")

            plc = SLAVE_DEVICES["PLC"]
            c = plc["coils"]
            s = plc["slave_id"]

            print(f"Using slave_id: {s}")

            # Helper to write
            def write(coil, state):
                print(f"  → Writing coil {coil} = {state}")
                mb.write_coil(s, coil, state)

            # -------------------------------------------------
            # Neutral
            neutral_state = self.cmb_n.currentText() == "C"
            print(f"Neutral selection: {self.cmb_n.currentText()} -> {neutral_state}")
            write(c["NEUTRAL"], neutral_state)

            # -------------------------------------------------
            # Voltage selections (COMMON transformer tap)
            rv = self.cmb_r.currentText()
            yv = self.cmb_y.currentText()
            bv = self.cmb_b.currentText()

            print(f"Voltage selections: R={rv}, Y={yv}, B={bv}")

            # -------------------------------------------------
            # Phase enable control
            write(c["R_EN"], rv != "NC")
            write(c["Y_EN"], yv != "NC")
            write(c["B_EN"], bv != "NC")

            print(
                f"Phase enables → "
                f"R_EN={rv != 'NC'}, "
                f"Y_EN={yv != 'NC'}, "
                f"B_EN={bv != 'NC'}"
            )

            # -------------------------------------------------
            print("Resetting ALL transformer voltage taps")

            for name, addr in c.items():
                if name.startswith("T_"):
                    write(addr, False)

            # -------------------------------------------------
            # Decide which voltage tap to apply
            # Priority: R → Y → B (first non-NC)

            selected_voltage = None

            for v in (rv, yv, bv):
                if v != "NC":
                    selected_voltage = v
                    break

            if selected_voltage:
                if selected_voltage == "240V":
                    if neutral_state:
                        tap_key = "240"
                    else:
                        tap_key = "138"
                else:
                    tap_key = VLL_TO_TAP.get(
                        selected_voltage,
                        selected_voltage.replace("V", "")
                    )

                print(f"Applying COMMON voltage tap: {selected_voltage} → T_{tap_key}")
                write(c[f"T_{tap_key}"], True)

            else:
                print("No voltage tap selected (all phases NC)")

            # -------------------------------------------------
            # 🔹 Current 1 & 2 (UNCHANGED)
            print("Resetting all current taps (CUR1 & CUR2)")
            for i in CURRENT_TAPPINGS:
                if i != "0A":
                    cur_key = i.replace("A", "").replace(".", "_")
                    write(c[f"CUR1_{cur_key}"], False)
                    write(c[f"CUR2_{cur_key}"], False)

            i1 = self.cmb_i1.currentText()
            i2 = self.cmb_i2.currentText()

            print(f"Current selections: I1={i1}, I2={i2}")

            if i1 != "0A":
                cur_key = i1.replace("A", "").replace(".", "_")
                print(f"Setting CUR1 tap: {i1}")
                write(c[f"CUR1_{cur_key}"], True)

            if i2 != "0A":
                cur_key = i2.replace("A", "").replace(".", "_")
                print(f"Setting CUR2 tap: {i2}")
                write(c[f"CUR2_{cur_key}"], True)

            print("=== apply_all_taps(): SUCCESS ===")
            logger.info("Taps applied")

        except Exception as e:
            print(f"❌ apply_all_taps(): ERROR -> {e}")
            logger.error(f"Apply failed: {e}")
            QMessageBox.warning(self, "Error", str(e))

        finally:
            print("Closing Modbus connection")
            self._close_modbus()
            print("=== apply_all_taps(): END ===")

    # -------------------------------------------------

    def reset_all_relays(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]
            for _, addr in plc["coils"].items():
                mb.write_coil(plc["slave_id"], addr, False)
            QMessageBox.information(self, "Done", "Relays reset")
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    # -------------------------------------------------
    def toggle_main_contactor(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]

            coil_addr = plc["coils"]["MAIN_CONTACTOR"]
            slave_id = plc["slave_id"]

            # Toggle state
            self.main_contactor_on = not self.main_contactor_on

            # Write to PLC
            mb.write_coil(slave_id, coil_addr, self.main_contactor_on)

            # Update UI
            if self.main_contactor_on:
                self.btn_main.setText("MAIN : OFF")
                self.btn_main.setStyleSheet(
                    "background-color: #dc3545; color: white; font-weight: bold; font-size: 14pt;"
                )
                logger.info("MAIN_CONTACTOR turned ON")
            else:
                self.btn_main.setText("MAIN : ON")
                self.btn_main.setStyleSheet(
                    "background-color: #28a745; color: white; font-weight: bold; font-size: 14pt;"
                )
                logger.info("MAIN_CONTACTOR turned OFF")

        except Exception as e:
            logger.error(f"Main Contactor toggle failed: {e}")
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    def toggle_impedance_pcb1(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]

            self.imp_test_pcb1_on = not self.imp_test_pcb1_on
            mb.write_coil(plc["slave_id"], plc["coils"]["IMP1_TEST_EN"], self.imp_test_pcb1_on)

            if self.imp_test_pcb1_on:
                self.btn_imp_test_pcb1.setText("IMPEDANCE TEST PCB 1 : OFF")
                self.btn_imp_test_pcb1.setStyleSheet("background-color:#dc3545;color:white;font-weight:bold;")
            else:
                self.btn_imp_test_pcb1.setText("IMPEDANCE TEST PCB 1 : ON")
                self.btn_imp_test_pcb1.setStyleSheet("background-color:#28a745;color:white;font-weight:bold;")

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    def toggle_impedance_pcb2(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]

            self.imp_test_pcb2_on = not self.imp_test_pcb2_on
            mb.write_coil(plc["slave_id"], plc["coils"]["IMP2_TEST_EN"], self.imp_test_pcb2_on)

            if self.imp_test_pcb2_on:
                self.btn_imp_test_pcb2.setText("IMPEDANCE TEST PCB 2 : OFF")
                self.btn_imp_test_pcb2.setStyleSheet("background-color:#dc3545;color:white;font-weight:bold;")
            else:
                self.btn_imp_test_pcb2.setText("IMPEDANCE TEST PCB 2 : ON")
                self.btn_imp_test_pcb2.setStyleSheet("background-color:#28a745;color:white;font-weight:bold;")

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    def toggle_pcb2_enable(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]

            self.pcb2_enabled = not self.pcb2_enabled
            mb.write_coil(plc["slave_id"], plc["coils"]["PCB_2_EN"], self.pcb2_enabled)

            if self.pcb2_enabled:
                self.btn_pcb2_enable.setText("PCB 2 ENABLE : OFF")
                self.btn_pcb2_enable.setStyleSheet("background-color:#dc3545;color:white;font-weight:bold;")
            else:
                self.btn_pcb2_enable.setText("PCB 2 ENABLE : ON")
                self.btn_pcb2_enable.setStyleSheet("background-color:#28a745;color:white;font-weight:bold;")

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    def toggle_imp_relay(self, relay_name, button):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]

            # Toggle state
            self.imp_relays[relay_name] = not self.imp_relays[relay_name]

            # Write coil
            mb.write_coil(plc["slave_id"], plc["coils"][relay_name], self.imp_relays[relay_name])

            # Update UI
            if self.imp_relays[relay_name]:
                button.setText(f"{relay_name} : OFF")
                button.setStyleSheet("background-color:#dc3545;color:white;font-weight:bold;")
            else:
                button.setText(f"{relay_name} : ON")
                button.setStyleSheet("background-color:#28a745;color:white;font-weight:bold;")

        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

    # -------------------------------------------------
    def read_qr_code(self, scanner_name, field):
        try:
            com = self.cmb_com.currentText()
            if com.startswith("--"): return
            qr = SLAVE_DEVICES[scanner_name]
            raw = RawSerial(port=com)
            rx = raw.write_read(qr["read_cmd"])
            raw.close()
            field.setText(rx.decode(errors="ignore").strip())
        except Exception as e:
            logger.error(f"QR Error ({scanner_name}): {e}")

    # -------------------------------------------------
    def read_modbus(self, key, field):
        try:
            mb = self._get_modbus()
            for _, dev in SLAVE_DEVICES.items():
                if "reads" in dev and key in dev["reads"]:
                    reg = dev["registers"][dev["reads"][key]]
                    val = mb.read_float(
                        dev["slave_id"],
                        reg,
                        endian=dev.get("endian","ABCD")
                    )
                    field.setText(f"{val:.3f}")
                    return
        except Exception as e:
            logger.error(f"Read Error ({key}): {e}")
        finally:
            self._close_modbus()

    # -------------------------------------------------
    def _close_modbus(self):
        if self.modbus:
            try:
                self.modbus.close()
            except Exception:
                pass
            self.modbus = None
            self.current_com = None
