import os
import serial.tools.list_ports
from PySide6.QtWidgets import QWidget, QMessageBox, QComboBox, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QEvent

from modbus_driver import ModbusRTU
from raw_serial_driver import RawSerial
from config import SLAVE_DEVICES, VOLTAGE_TAPPINGS, CURRENT_TAPPINGS, NEUTRAL_OPTIONS
from logs import logger
from new_ui.icons import IconHelper

class DebugView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New DebugView")
        self.modbus = None
        self.current_com = None

        self.load_ui()
        self.setup_icons()
        self.populate_com_ports()
        self.populate_tappings()
        self.connect_signals()

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "debug.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open debug.ui at {ui_path}")
            raise RuntimeError("Cannot open debug.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Widget Binding
        self.cmb_com = self.findChild(QComboBox, "comboBox_comPorts")
        self.cmb_r = self.findChild(QComboBox, "combo_r_voltage")
        self.cmb_y = self.findChild(QComboBox, "combo_y_voltage")
        self.cmb_b = self.findChild(QComboBox, "combo_b_voltage")
        self.cmb_n = self.findChild(QComboBox, "combo_neutral")
        self.cmb_i = self.findChild(QComboBox, "combo_current")

        self.btn_apply = self.findChild(QWidget, "btn_apply_taps")
        self.btn_reset = self.findChild(QWidget, "btn_reset_taps")
        self.btn_qr = self.findChild(QWidget, "btn_read_qr")
        self.txt_qr = self.findChild(QWidget, "txt_qr")

        # Dynamic read buttons for DC
        self.btn_read_v = self.findChild(QWidget, "btn_read_dc_voltage")
        self.txt_read_v = self.findChild(QWidget, "txt_dc_voltage")
        self.btn_read_i = self.findChild(QWidget, "btn_read_dc_current")
        self.txt_read_i = self.findChild(QWidget, "txt_dc_current")

        self.cmb_com.installEventFilter(self)

    def setup_icons(self):
        IconHelper.apply_icon(self.btn_apply, "check", "white")
        IconHelper.apply_icon(self.btn_reset, "times", "white")
        IconHelper.apply_icon(self.btn_qr, "search")

    def eventFilter(self, obj, event):
        if obj == self.cmb_com and event.type() == QEvent.MouseButtonPress:
            self.populate_com_ports()
        return super().eventFilter(obj, event)

    def populate_com_ports(self):
        self.cmb_com.blockSignals(True)
        self.cmb_com.clear()
        self.cmb_com.addItem("-- Select COM --")
        for p in serial.tools.list_ports.comports():
            self.cmb_com.addItem(p.device)
        self.cmb_com.blockSignals(False)

    def populate_tappings(self):
        self.cmb_r.addItems(VOLTAGE_TAPPINGS)
        self.cmb_y.addItems(VOLTAGE_TAPPINGS)
        self.cmb_b.addItems(VOLTAGE_TAPPINGS)
        self.cmb_n.addItems(NEUTRAL_OPTIONS)
        self.cmb_i.addItems(CURRENT_TAPPINGS)

    def connect_signals(self):
        self.btn_apply.clicked.connect(self.apply_all_taps)
        self.btn_reset.clicked.connect(self.reset_all_relays)
        self.btn_qr.clicked.connect(lambda: self.read_qr_code(self.txt_qr))

        if self.btn_read_v:
            self.btn_read_v.clicked.connect(lambda: self.read_modbus("dc_voltage", self.txt_read_v))
        if self.btn_read_i:
            self.btn_read_i.clicked.connect(lambda: self.read_modbus("dc_current", self.txt_read_i))

    # =========================================================================
    # LOGIC (Ported)
    # =========================================================================

    def _get_modbus(self):
        com = self.cmb_com.currentText()
        if com.startswith("--"):
            raise RuntimeError("COM not selected")
        if self.modbus and self.current_com == com:
            return self.modbus
        if self.modbus: self.modbus.close()
        self.modbus = ModbusRTU(port=com)
        self.current_com = com
        return self.modbus

    def apply_all_taps(self):
        try:
            mb = self._get_modbus()
            plc = SLAVE_DEVICES["PLC"]
            c = plc["coils"]
            s = plc["slave_id"]

            # Helper to write
            def w(coil, state): mb.write_coil(s, coil, state)

            # Neutral
            w(c["NEUTRAL"], self.cmb_n.currentText() == "C")

            # Voltage
            rv, yv, bv = self.cmb_r.currentText(), self.cmb_y.currentText(), self.cmb_b.currentText()

            for t in VOLTAGE_TAPPINGS:
                if t != "NC": w(c[f"R_{t.replace('V','')}"], False)
            if rv != "NC": w(c[f"R_{rv.replace('V','')}"], True)

            for t in VOLTAGE_TAPPINGS:
                if t != "NC": w(c[f"Y_{t.replace('V','')}"], False)
            if yv != "NC": w(c[f"Y_{yv.replace('V','')}"], True)

            for t in VOLTAGE_TAPPINGS:
                if t != "NC": w(c[f"B_{t.replace('V','')}"], False)
            if bv != "NC": w(c[f"B_{bv.replace('V','')}"], True)

            # Current
            cur = self.cmb_i.currentText()
            for i in CURRENT_TAPPINGS:
                if i != "0": w(c[f"CUR_{i.replace('.','_')}"], False)
            if cur != "0": w(c[f"CUR_{cur.replace('.','_')}"], True)

            logger.info("Taps applied")

        except Exception as e:
            logger.error(f"Apply failed: {e}")
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._close_modbus()

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

    def read_qr_code(self, field):
        try:
            com = self.cmb_com.currentText()
            if com.startswith("--"): return
            qr = SLAVE_DEVICES["QR_SCANNER"]
            raw = RawSerial(port=com)
            rx = raw.write_read(qr["read_cmd"])
            raw.close()
            field.setText(rx.decode(errors="ignore").strip())
        except Exception as e:
            logger.error(f"QR Error: {e}")

    def read_modbus(self, key, field):
        try:
            mb = self._get_modbus()
            for _, dev in SLAVE_DEVICES.items():
                if "reads" in dev and key in dev["reads"]:
                    reg = dev["registers"][dev["reads"][key]]
                    val = mb.read_float(dev["slave_id"], reg, endian=dev.get("endian","ABCD"))
                    field.setText(f"{val:.3f}")
                    return
        except Exception as e:
            logger.error(f"Read Error: {e}")
        finally:
            self._close_modbus()

    def _close_modbus(self):
        if self.modbus:
            try: self.modbus.close()
            except: pass
            self.modbus = None
            self.current_com = None
