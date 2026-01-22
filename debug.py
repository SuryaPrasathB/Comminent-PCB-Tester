# debug.py
import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent
import serial.tools.list_ports

from modbus_driver import ModbusRTU
from raw_serial_driver import RawSerial
from config import (
    SLAVE_DEVICES,
    VOLTAGE_TAPPINGS,
    CURRENT_TAPPINGS,
    NEUTRAL_OPTIONS,
)

from logs import logger


class DebugController(QWidget):
    def __init__(self, parent_tab: QWidget):
        super().__init__(parent_tab)

        print("[DEBUG] DebugController __init__")
        logger.info("DebugController initialized")

        self.parent_tab = parent_tab
        self.modbus = None
        self.current_com = None

        self.load_ui()
        self.populate_com_ports()
        self.populate_tappings()
        self.connect_signals()

    # -------------------------------------------------
    def showEvent(self, event):
        print("[DEBUG] Debug tab activated (showEvent)")
        logger.info("Debug tab activated")
        super().showEvent(event)

    # -------------------------------------------------
    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "debug.ui")

        print("[DEBUG] Loading debug UI from:", ui_path)
        logger.info(f"Loading debug UI from {ui_path}")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Unable to open debug.ui: {ui_path}")
            raise RuntimeError(f"Unable to open debug.ui: {ui_path}")

        self.ui = loader.load(ui_file, self.parent_tab)  # ← Parent is the tab page
        ui_file.close()

        # IMPORTANT: Do NOT create a new layout or call setLayout!
        layout = self.parent_tab.layout()
        if layout is None:
            layout = QVBoxLayout(self.parent_tab)
            self.parent_tab.setLayout(layout)
            logger.warning("Debug tab layout was missing, fallback layout created")

        layout.addWidget(self.ui)

        # ---------- Widget bindings ----------
        self.cmb_com = self.ui.comboBox_comPorts
        self.cmb_neutral = self.ui.combo_neutral
        self.cmb_r_v     = self.ui.combo_r_voltage
        self.cmb_y_v     = self.ui.combo_y_voltage
        self.cmb_b_v     = self.ui.combo_b_voltage
        self.cmb_current = self.ui.combo_current
        self.btn_apply   = self.ui.btn_apply_taps
        self.btn_reset   = self.ui.btn_reset_taps

        # Rescan COM on click
        self.cmb_com.installEventFilter(self)

        print("[DEBUG] Debug UI loaded successfully")
        logger.info("Debug UI loaded successfully")

    # -------------------------------------------------
    def eventFilter(self, obj, event):
        if obj == self.cmb_com and event.type() == QEvent.MouseButtonPress:
            print("[DEBUG] COM dropdown clicked → rescanning")
            logger.info("COM dropdown clicked → rescanning ports")
            self.populate_com_ports()
        return super().eventFilter(obj, event)

    # -------------------------------------------------
    def populate_com_ports(self):
        logger.info("Scanning available COM ports")

        self.cmb_com.blockSignals(True)
        self.cmb_com.clear()
        self.cmb_com.addItem("-- Select COM --")

        for p in serial.tools.list_ports.comports():
            print(f"[DEBUG] Found COM: {p.device}")
            logger.info(f"Found COM port: {p.device}")
            self.cmb_com.addItem(p.device)

        self.cmb_com.blockSignals(False)

    # -------------------------------------------------
    def populate_tappings(self):
        logger.info("Populating voltage/current/neutral tappings")

        self.cmb_neutral.clear()
        self.cmb_r_v.clear()
        self.cmb_y_v.clear()
        self.cmb_b_v.clear()
        self.cmb_current.clear()

        self.cmb_neutral.addItems(NEUTRAL_OPTIONS)
        self.cmb_r_v.addItems(VOLTAGE_TAPPINGS)
        self.cmb_y_v.addItems(VOLTAGE_TAPPINGS)
        self.cmb_b_v.addItems(VOLTAGE_TAPPINGS)
        self.cmb_current.addItems(CURRENT_TAPPINGS)

    # -------------------------------------------------
    def connect_signals(self):
        logger.info("Connecting Debug tab signals")

        self.cmb_com.currentTextChanged.connect(self.on_com_selected)
        self.btn_apply.clicked.connect(self.apply_all_taps)
        self.btn_reset.clicked.connect(self.reset_all_relays)

        self.ui.btn_read_qr.clicked.connect(
            lambda: self.read_qr_code(self.ui.txt_qr)
        )

        # Connect read buttons dynamically
        for dev in SLAVE_DEVICES.values():
            if "reads" not in dev:
                continue

            for key in dev["reads"]:
                btn = getattr(self.ui, f"btn_read_{key}", None)
                txt = getattr(self.ui, f"txt_{key}", None)

                if btn and txt:
                    btn.clicked.connect(
                        lambda _, k=key, f=txt:
                        self.read_modbus(k, f)
                    )

    # -------------------------------------------------
    def on_com_selected(self, com):
        if not com.startswith("--"):
            print(f"[DEBUG] COM selected: {com}")
            logger.info(f"COM selected: {com}")

    # -------------------------------------------------
    def _get_modbus(self):
        com = self.cmb_com.currentText()
        if com.startswith("--"):
            logger.error("Modbus request failed: COM not selected")
            raise RuntimeError("COM not selected")

        if self.modbus and self.current_com == com:
            return self.modbus

        if self.modbus:
            self.modbus.close()

        logger.info(f"Opening Modbus RTU on {com}")
        self.modbus = ModbusRTU(port=com)
        self.current_com = com
        return self.modbus

    # -------------------------------------------------
    def apply_all_taps(self):
        logger.info("Apply taps requested")

        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]
            c = plc["coils"]
            s = plc["slave_id"]

            n = self.cmb_neutral.currentText()
            rv = self.cmb_r_v.currentText()
            yv = self.cmb_y_v.currentText()
            bv = self.cmb_b_v.currentText()
            cur = self.cmb_current.currentText()

            print("[DEBUG] Applying taps:")
            print(f"  Neutral = {n}")
            print(f"  R Volt  = {rv}")
            print(f"  Y Volt  = {yv}")
            print(f"  B Volt  = {bv}")
            print(f"  Current = {cur}")

            logger.info(f"Applying taps | N={n}, R={rv}, Y={yv}, B={bv}, I={cur}")

            # ---- Neutral (NC = OFF, C = ON) ----
            print(f" Neutral Coil Adrs  = {c["NEUTRAL"]}")
            mb.write_coil(s, c["NEUTRAL"], n == "C")

            # =================================================
            # VOLTAGE TAPS
            # =================================================

            # R phase
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and mb.write_coil(s, c[f"R_{tap.replace('V', '')}"], False)
            rv != "NC" and mb.write_coil(s, c[f"R_{rv.replace('V', '')}"], True)

            # Y phase
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and mb.write_coil(s, c[f"Y_{tap.replace('V', '')}"], False)
            yv != "NC" and mb.write_coil(s, c[f"Y_{yv.replace('V', '')}"], True)

            # B phase
            for tap in VOLTAGE_TAPPINGS:
                tap != "NC" and mb.write_coil(s, c[f"B_{tap.replace('V', '')}"], False)
            bv != "NC" and mb.write_coil(s, c[f"B_{bv.replace('V', '')}"], True)

            # =================================================
            # CURRENT TAPS
            # =================================================

            # OFF all current relays
            for i in CURRENT_TAPPINGS:
                i != "0" and mb.write_coil(s, c[f"CUR_{i.replace('.', '_')}"], False)

            # ON selected current relay
            cur != "0" and mb.write_coil(s, c[f"CUR_{cur.replace('.', '_')}"], True)

            print("[DEBUG] ✅ Taps applied successfully")
            logger.info("Taps applied successfully")

        except Exception as e:
            print("[DEBUG][ERROR] Apply taps failed:", e)
            logger.error(f"Apply taps failed: {e}")
            QMessageBox.warning(self.ui, "Apply Failed", str(e))

        finally:
            self._close_modbus()
            logger.info("Closing COM Port")

    # -------------------------------------------------
    def reset_all_relays(self):
        logger.info("Reset all relays requested")

        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]
            coils = plc["coils"]
            slave = plc["slave_id"]

            print("[DEBUG] Resetting ALL PLC relays")

            for name, addr in coils.items():
                print(f"  → OFF {name} (coil {addr})")
                mb.write_coil(slave, addr, False)

            QMessageBox.information(
                self.ui,
                "Reset Done",
                "All PLC relays have been reset (OFF)."
            )

            logger.info("All PLC relays reset successfully")

        except Exception as e:
            print("[DEBUG][ERROR] Reset failed:", e)
            logger.error(f"Reset all relays failed: {e}")
            QMessageBox.warning(self.ui, "Reset Failed", str(e))

        finally:
            self._close_modbus()

    # -------------------------------------------------
    def read_qr_code(self, field):
        logger.info("QR code read requested")

        try:
            com = self.cmb_com.currentText()
            if com.startswith("--"):
                logger.error("QR read failed: COM not selected")
                raise RuntimeError("COM not selected")

            qr = SLAVE_DEVICES["QR_SCANNER"]
            print(f"[DEBUG] Command : {qr["read_cmd"]}")
            cmd_str = qr["read_cmd"]  # "015404"
            #cmd_bytes = bytes.fromhex(cmd_str)

            raw = RawSerial(port=com)
            rx = raw.write_read(cmd_str) #raw.write_read(cmd_bytes, rx_len=256)
            print(f"[DEBUG] rx : {rx}")
            logger.info(f"[INFO] rx : {rx}")

            raw.close()
            field.setText(rx.decode(errors="ignore").strip())

            logger.info("QR code read successfully")

        except Exception as e:
            print("[DEBUG][ERROR] QR read failed:", e)
            logger.error(f"QR read failed: {e}")

    # -------------------------------------------------
    def read_modbus(self, key, field):
        logger.info(f"Modbus read requested | key={key}")

        try:
            mb = self._get_modbus()

            for name, dev in SLAVE_DEVICES.items():
                if "reads" in dev and key in dev["reads"]:
                    reg = dev["registers"][dev["reads"][key]]
                    endian = dev.get("endian", "ABCD")

                    value = mb.read_float(
                        dev["slave_id"], reg, endian=endian
                    )

                    print(f"[DEBUG] {name}.{key} = {value:.3f}")
                    field.setText(f"{value:.3f}")

                    logger.info(
                        f"Modbus read success | {name}.{key}={value:.3f}"
                    )
                    return

            raise RuntimeError("Unknown read key")

        except Exception as e:
            print(f"[DEBUG][ERROR] Read failed ({key}):", e)
            logger.error(f"Modbus read failed | key={key} | error={e}")

        finally:
            self._close_modbus()

    # -------------------------------------------------
    def _close_modbus(self):
        if self.modbus:
            try:
                print("[DEBUG] Closing Modbus connection")
                logger.info("Closing Modbus connection")
                self.modbus.close()
            except Exception:
                logger.warning("Exception while closing Modbus connection")
                pass
            finally:
                self.modbus = None
                self.current_com = None
