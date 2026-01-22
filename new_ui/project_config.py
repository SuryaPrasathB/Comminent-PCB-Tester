import os
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QCheckBox, QComboBox, QMessageBox,
    QVBoxLayout, QHeaderView, QAbstractItemView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt
from PySide6.QtGui import QPixmap

from config import default_test_cases, VOLTAGE_TAPPINGS, NEUTRAL_OPTIONS
from db_utils import save_project, load_projects, load_project_rows, delete_project
from circuit_diagram import generate_three_phase_diagram
from logs import logger
from new_ui.icons import IconHelper

# Helper for non-scrolling combo
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class ProjectConfigView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New ProjectConfigView")
        self.load_ui()
        self.setup_icons()
        self.connect_signals()

        # Initial Population
        self.refresh_projects()
        self.populate_test_table(default_test_cases)

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "project_config.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open project_config.ui at {ui_path}")
            raise RuntimeError("Cannot open project_config.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Widget Binding
        self.table = self.findChild(QWidget, "tableWidget_testCases")
        self.txt_project = self.findChild(QWidget, "lineEdit_projectName")
        self.cmb_projects = self.findChild(QWidget, "comboBox_projects")
        self.lbl_circuit = self.findChild(QWidget, "label_circuitDiagram")

        self.btn_save = self.findChild(QWidget, "pushButton_save")
        self.btn_delete = self.findChild(QWidget, "pushButton_delete")
        self.btn_up = self.findChild(QWidget, "pushButton_moveUp")
        self.btn_down = self.findChild(QWidget, "pushButton_moveDown")

        # Table Config
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)

    def setup_icons(self):
        IconHelper.apply_icon(self.btn_save, "save", "white")
        IconHelper.apply_icon(self.btn_delete, "delete", "white")
        IconHelper.apply_icon(self.btn_up, "arrow_up")
        IconHelper.apply_icon(self.btn_down, "arrow_down")

    def connect_signals(self):
        self.btn_up.clicked.connect(self.move_up)
        self.btn_down.clicked.connect(self.move_down)
        self.btn_save.clicked.connect(self.save_current_project)
        self.btn_delete.clicked.connect(self.delete_current_project)
        self.cmb_projects.currentIndexChanged.connect(self.load_selected_project)
        self.table.itemSelectionChanged.connect(self.on_row_selected)

    # =========================================================================
    # LOGIC (Ported)
    # =========================================================================

    def refresh_projects(self):
        logger.info("Refreshing project list")
        self.cmb_projects.blockSignals(True)
        self.cmb_projects.clear()
        self.cmb_projects.addItem("-- Select from Saved Projects --")
        for p in load_projects():
            self.cmb_projects.addItem(p)
        self.cmb_projects.blockSignals(False)

    def populate_test_table(self, test_cases):
        logger.info(f"Populating test table: {len(test_cases)} items")
        self.table.setRowCount(0)

        for row, tc in enumerate(test_cases):
            self.table.insertRow(row)

            # SN
            sn = QTableWidgetItem(str(row + 1))
            sn.setFlags(sn.flags() & ~Qt.ItemIsEditable)
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, sn)

            # Enable Checkbox
            chk = QCheckBox()
            chk.setChecked(tc.get("enabled", True))
            self.table.setCellWidget(row, 1, chk)

            # Desc
            self.table.setItem(row, 2, QTableWidgetItem(tc.get("desc", "")))

            # Combos
            self._set_combo(row, 3, VOLTAGE_TAPPINGS, tc.get("r", "NC"))
            self._set_combo(row, 4, VOLTAGE_TAPPINGS, tc.get("y", "NC"))
            self._set_combo(row, 5, VOLTAGE_TAPPINGS, tc.get("b", "NC"))
            self._set_combo(row, 6, NEUTRAL_OPTIONS, tc.get("n", "NC"))

            # Expected
            self.table.setItem(row, 7, QTableWidgetItem(tc.get("v", "")))
            self.table.setItem(row, 8, QTableWidgetItem(tc.get("i", "")))

            self.table.setRowHeight(row, 32)

        self._renumber_serials()

    def _set_combo(self, row, col, values, current):
        combo = NoWheelComboBox()
        combo.addItems(values)
        combo.setCurrentText(current)
        combo.currentTextChanged.connect(self.on_combo_changed)
        self.table.setCellWidget(row, col, combo)

    def on_combo_changed(self, _=None):
        if self.table.currentRow() >= 0:
            self.on_row_selected()

    def _renumber_serials(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item: item.setText(str(row + 1))

    def move_up(self):
        r = self.table.currentRow()
        if r > 0:
            self._swap_rows(r, r - 1)
            self.table.setCurrentCell(r - 1, 0)

    def move_down(self):
        r = self.table.currentRow()
        if 0 <= r < self.table.rowCount() - 1:
            self._swap_rows(r, r + 1)
            self.table.setCurrentCell(r + 1, 0)

    def _swap_rows(self, r1, r2):
        def read_row(row):
            return {
                "enabled": self.table.cellWidget(row, 1).isChecked(),
                "desc": self.table.item(row, 2).text(),
                "r": self.table.cellWidget(row, 3).currentText(),
                "y": self.table.cellWidget(row, 4).currentText(),
                "b": self.table.cellWidget(row, 5).currentText(),
                "n": self.table.cellWidget(row, 6).currentText(),
                "v": self.table.item(row, 7).text(),
                "i": self.table.item(row, 8).text(),
            }
        def write_row(row, data):
            self.table.cellWidget(row, 1).setChecked(data["enabled"])
            self.table.item(row, 2).setText(data["desc"])
            self.table.cellWidget(row, 3).setCurrentText(data["r"])
            self.table.cellWidget(row, 4).setCurrentText(data["y"])
            self.table.cellWidget(row, 5).setCurrentText(data["b"])
            self.table.cellWidget(row, 6).setCurrentText(data["n"])
            self.table.item(row, 7).setText(data["v"])
            self.table.item(row, 8).setText(data["i"])

        d1 = read_row(r1)
        d2 = read_row(r2)
        write_row(r1, d2)
        write_row(r2, d1)
        self._renumber_serials()

    def load_selected_project(self):
        project_name = self.cmb_projects.currentText()
        if project_name.startswith("--"): return

        self.txt_project.setText(project_name)
        saved_rows = load_project_rows(project_name)

        # Merge logic (simplified port)
        def _norm(val): return val.strip() if isinstance(val, str) else val
        saved_map = {}
        for row in saved_rows:
            key = (_norm(row["desc"]), _norm(row["r"]), _norm(row["y"]), _norm(row["b"]), _norm(row["n"]), _norm(row["v"]), _norm(row["i"]))
            saved_map[key] = row

        merged = []
        for tc in default_test_cases:
            key = (_norm(tc["desc"]), _norm(tc["r"]), _norm(tc["y"]), _norm(tc["b"]), _norm(tc["n"]), _norm(tc["v"]), _norm(tc["i"]))
            if key in saved_map:
                row = saved_map[key]
                merged.append({**tc, "enabled": row["enabled"]})
            else:
                merged.append({**tc, "enabled": False})

        self.populate_test_table(merged)

    def save_current_project(self):
        name = self.txt_project.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Project name required")
            return

        data = []
        for row in range(self.table.rowCount()):
            if not self.table.cellWidget(row, 1).isChecked(): continue
            data.append({
                "sn": row + 1,
                "desc": self.table.item(row, 2).text(),
                "r": self.table.cellWidget(row, 3).currentText(),
                "y": self.table.cellWidget(row, 4).currentText(),
                "b": self.table.cellWidget(row, 5).currentText(),
                "n": self.table.cellWidget(row, 6).currentText(),
                "v": self.table.item(row, 7).text(),
                "i": self.table.item(row, 8).text(),
                "enabled": True
            })

        save_project(name, data)
        self.refresh_projects()
        QMessageBox.information(self, "Saved", "Project saved")

    def delete_current_project(self):
        name = self.cmb_projects.currentText()
        if name.startswith("--"): return
        if QMessageBox.question(self, "Confirm", f"Delete '{name}'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            delete_project(name)
            self.refresh_projects()
            self.txt_project.clear()
            self.populate_test_table(default_test_cases)

    def on_row_selected(self):
        row = self.table.currentRow()
        if row < 0: return

        try:
            r = self.parse_ac(self.table.cellWidget(row, 3).currentText())
            y = self.parse_ac(self.table.cellWidget(row, 4).currentText())
            b = self.parse_ac(self.table.cellWidget(row, 5).currentText())
            n = self.parse_ac(self.table.cellWidget(row, 6).currentText())

            vdc = self.table.item(row, 7).text().replace("V","").strip()
            dc_v = float(vdc) if vdc else 0.0

            idc = self.table.item(row, 8).text().replace("A","").strip()
            dc_i = float(idc) if idc else 0.0

            png = generate_three_phase_diagram(r, y, b, n, dc_v, dc_i)
            if png:
                pix = QPixmap()
                pix.loadFromData(png)
                self.lbl_circuit.setPixmap(pix.scaled(self.lbl_circuit.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            logger.error(f"Diagram error: {e}")

    def parse_ac(self, val):
        if val in ["NC", "C"]: return val
        return float(val.replace("V","").strip())
