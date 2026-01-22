# project_config.py
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QCheckBox, QComboBox,
    QMessageBox, QHeaderView, QVBoxLayout, QSizePolicy
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Qt, QFile, QIODevice, QSize

from config import default_test_cases, VOLTAGE_TAPPINGS, NEUTRAL_OPTIONS
from db_utils import (
    save_project,
    load_projects,
    load_project_rows,
    delete_project
)
from circuit_diagram import generate_three_phase_diagram

from logs import logger

# =====================================================
# ComboBox that ignores mouse wheel
# =====================================================
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


# =====================================================
# Project Configuration Controller
# =====================================================
class ProjectConfigController:
    def __init__(self, parent_tab: QWidget):
        self.parent_tab = parent_tab
        print("[PROJECT CONFIG] Initializing ProjectConfigController")
        logger.info("ProjectConfigController initialized")
        self.load_ui()
        self.connect_signals()
        self.refresh_projects()
        self.populate_test_table(default_test_cases)

    # -------------------------------------------------
    # Load UI
    # -------------------------------------------------
    def load_ui(self):
        import os

        print("[PROJECT CONFIG] load_ui() called")
        logger.info("load_ui called")

        loader = QUiLoader()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "project_config.ui")

        print(f"[PROJECT CONFIG] Loading UI from: {ui_path}")
        logger.info(f"Loading UI from {ui_path}")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            print("[PROJECT CONFIG] ERROR: Failed to open project_config.ui")
            logger.error("Failed to open project_config.ui")
            raise RuntimeError(f"Cannot open project_config.ui at {ui_path}")

        self.ui = loader.load(ui_file, self.parent_tab)
        ui_file.close()

        if not self.ui:
            print("[PROJECT CONFIG] ERROR: project_config.ui loaded as NULL")
            logger.error("project_config.ui loaded as NULL")
            raise RuntimeError("Failed to load project_config.ui")

        old_layout = self.parent_tab.layout()
        if old_layout:
            old_layout.deleteLater()

        layout = QVBoxLayout()
        layout.addWidget(self.ui)
        self.parent_tab.setLayout(layout)

        self.table = self.ui.tableWidget_testCases
        self.txt_project = self.ui.lineEdit_projectName
        self.cmb_projects = self.ui.comboBox_projects
        self.lbl_circuit = self.ui.label_circuitDiagram

        print("[PROJECT CONFIG] UI widgets bound successfully")
        logger.info("UI widgets bound successfully")
        # -------------------------------------------------
        # Row highlight
        # -------------------------------------------------
        from PySide6.QtWidgets import QAbstractItemView

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.table.setStyleSheet(
            "QTableWidget::item:selected { background-color: #cce6ff; }"
        )

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)

        print("[PROJECT CONFIG] UI loaded successfully")
        logger.info("UI loaded successfully")
    # -------------------------------------------------
    # Signals
    # -------------------------------------------------
    def connect_signals(self):
        print("[PROJECT CONFIG] Connecting UI signals")
        logger.info("Connecting UI signals")
        self.ui.pushButton_moveUp.clicked.connect(self.move_up)
        self.ui.pushButton_moveDown.clicked.connect(self.move_down)
        self.ui.pushButton_save.clicked.connect(self.save_current_project)
        if hasattr(self.ui, "pushButton_delete"):
            self.ui.pushButton_delete.clicked.connect(self.delete_current_project)
        self.cmb_projects.currentIndexChanged.connect(self.load_selected_project)
        self.table.itemSelectionChanged.connect(self.on_row_selected)

    # -------------------------------------------------
    # Populate table
    # -------------------------------------------------
    def populate_test_table(self, test_cases):
        print(f"[PROJECT CONFIG] Populating test table with {len(test_cases)} cases")
        logger.info(f"Populating test table with {len(test_cases)} cases")
        self.table.setRowCount(0)

        for row, tc in enumerate(test_cases):
            self.table.insertRow(row)

            # ---- S. No. (STABLE, NOT MOVED) ----
            sn = QTableWidgetItem(str(row + 1))
            sn.setFlags(sn.flags() & ~Qt.ItemIsEditable)
            sn.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, sn)

            # ---- Enable ----
            chk = QCheckBox()
            chk.setChecked(tc.get("enabled", True))
            self.table.setCellWidget(row, 1, chk)

            # ---- Description ----
            self.table.setItem(row, 2, QTableWidgetItem(tc.get("desc", "")))

            self._set_combo(row, 3, VOLTAGE_TAPPINGS, tc.get("r", "NC"))
            self._set_combo(row, 4, VOLTAGE_TAPPINGS, tc.get("y", "NC"))
            self._set_combo(row, 5, VOLTAGE_TAPPINGS, tc.get("b", "NC"))
            self._set_combo(row, 6, NEUTRAL_OPTIONS, tc.get("n", "NC"))

            self.table.setItem(row, 7, QTableWidgetItem(tc.get("v", "")))
            self.table.setItem(row, 8, QTableWidgetItem(tc.get("i", "")))

            self.table.setRowHeight(row, 28)

        print("[PROJECT CONFIG] Test table population complete")
        logger.info(f"Test table population complete")
        self._renumber_serials()

    def _renumber_serials(self):
        print("[PROJECT CONFIG] Renumbering serial numbers")
        logger.info("Renumbering serial numbers")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setText(str(row + 1))

    def _set_combo(self, row, col, values, current):
        combo = NoWheelComboBox()
        combo.addItems(values)
        combo.setCurrentText(current)

        combo.currentTextChanged.connect(self.on_combo_changed)

        self.table.setCellWidget(row, col, combo)

    def on_combo_changed(self, _=None):
        if self.table.currentRow() < 0:
            return

        print("[UI] Combo changed → updating diagram")
        logger.info("Combo changed")
        self.on_row_selected()

    # -------------------------------------------------
    # Move rows (SAFE + DEBUG)
    # -------------------------------------------------
    def move_up(self):
        r = self.table.currentRow()
        print(f"[MOVE UP] currentRow = {r}")
        logger.info(f"Move up requested at row {r}")

        if r <= 0:
            print("[MOVE UP] At top or no selection, abort")
            logger.warning("Move up aborted")
            return

        self._swap_rows(r, r - 1)
        self.table.setCurrentCell(r - 1, 0)
        print(f"[MOVE UP] Moved row {r} -> {r - 1}")

    def move_down(self):
        r = self.table.currentRow()
        print(f"[MOVE DOWN] currentRow = {r}")
        logger.info(f"Move down requested at row {r}")

        if r < 0:
            print("[MOVE DOWN] No row selected, abort")
            logger.warning("Move down aborted")
            return

        if r >= self.table.rowCount() - 1:
            print("[MOVE DOWN] At bottom, abort")
            logger.warning("Move down aborted")
            return

        self._swap_rows(r, r + 1)
        self.table.setCurrentCell(r + 1, 0)
        print(f"[MOVE DOWN] Moved row {r} -> {r + 1}")

    def _swap_rows(self, r1, r2):
        print(f"[SWAP] SAFE swap rows {r1} <-> {r2} (excluding S.No.)")
        logger.info(f"Swapping rows {r1} and {r2}")

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

        row1 = read_row(r1)
        row2 = read_row(r2)

        write_row(r1, row2)
        write_row(r2, row1)

        self._renumber_serials()

        print("[SWAP] SAFE swap complete")
        logger.info("Row swap complete")

    # -------------------------------------------------
    # Save
    # -------------------------------------------------
    def save_current_project(self):
        name = self.txt_project.text().strip()
        logger.info(f"Save project requested: {name}")

        if not name:
            QMessageBox.warning(self.ui, "Error", "Project name required")
            logger.warning("Project name empty")
            return

        data = []
        for row in range(self.table.rowCount()):
            if not self.table.cellWidget(row, 1).isChecked():
                continue

            data.append({
                "sn": row + 1,  # 👈 SERIAL NUMBER (FINAL ORDER)
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
        logger.info(f"Project saved: {name}")
        self.refresh_projects()
        QMessageBox.information(self.ui, "Saved", "Project saved")

    # -------------------------------------------------
    # Delete
    # -------------------------------------------------
    def delete_current_project(self):
        name = self.cmb_projects.currentText()
        logger.info(f"Delete project requested: {name}")

        if name.startswith("--"):
            return

        if QMessageBox.question(
            self.ui, "Confirm",
            f"Delete project '{name}'?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            delete_project(name)
            logger.warning(f"Project deleted: {name}")
            self.refresh_projects()
            self.txt_project.clear()
            self.populate_test_table(default_test_cases)

    # -------------------------------------------------
    # Projects
    # -------------------------------------------------

    def refresh_projects(self):
        logger.info("Refreshing project list")
        self.cmb_projects.clear()
        self.cmb_projects.addItem("-- Select from Saved Projects --")
        for p in load_projects():
            self.cmb_projects.addItem(p)

    def load_selected_project(self):
        logger.info("loading selected project")
        print("[PROJECT CONFIG] loading selected project")
        logger.info("[PROJECT CONFIG] loading selected project")

        # Clear circuit diagram
        self.lbl_circuit.clear()
        self.lbl_circuit.setText("")

        project_name = self.cmb_projects.currentText()
        print(f"[PROJECT CONFIG] Selected project: {project_name}")
        logger.info(f"[PROJECT CONFIG] Selected project: {project_name}")

        # -------------------------------------------------
        # Placeholder selected → reset to defaults
        # -------------------------------------------------
        if project_name.startswith("--"):
            print("[PROJECT CONFIG] Placeholder selected → resetting to defaults")
            logger.info("[PROJECT CONFIG] Placeholder selected → resetting to defaults")
            self.txt_project.clear()
            self.populate_test_table(default_test_cases)
            return

        # -------------------------------------------------
        # Load project from DB
        # -------------------------------------------------
        self.txt_project.setText(project_name)

        saved_rows = load_project_rows(project_name)
        print(f"[PROJECT CONFIG] Loaded {len(saved_rows)} rows from DB")
        logger.info(f"Loaded {len(saved_rows)} rows from DB")

        # -------------------------------------------------
        # Helper for safe comparison
        # -------------------------------------------------
        def _norm(val):
            return val.strip() if isinstance(val, str) else val

        # -------------------------------------------------
        # Build composite-key map from DB rows
        # -------------------------------------------------
        saved_map = {}

        for row in saved_rows:
            key = (
                _norm(row["desc"]),
                _norm(row["r"]),
                _norm(row["y"]),
                _norm(row["b"]),
                _norm(row["n"]),
                _norm(row["v"]),
                _norm(row["i"]),
            )
            saved_map[key] = row

        print("[PROJECT CONFIG] Saved map keys (COMPOSITE):")
        logger.info(f"[PROJECT CONFIG] Saved map keys (COMPOSITE):")
        for k in saved_map:
            print("   ", k)

        # -------------------------------------------------
        # Merge with default test cases (ORDER PRESERVED)
        # -------------------------------------------------
        merged = []

        for tc in default_test_cases:
            key = (
                _norm(tc["desc"]),
                _norm(tc["r"]),
                _norm(tc["y"]),
                _norm(tc["b"]),
                _norm(tc["n"]),
                _norm(tc["v"]),
                _norm(tc["i"]),
            )

            if key in saved_map:
                row = saved_map[key]
                merged.append({
                    "desc": tc["desc"],
                    "r": tc["r"],
                    "y": tc["y"],
                    "b": tc["b"],
                    "n": tc["n"],
                    "v": tc["v"],
                    "i": tc["i"],
                    "enabled": row["enabled"],
                })
                #print(f"[PROJECT CONFIG] MATCH → ENABLED: {tc['desc']} {tc['i']}")
            else:
                merged.append({
                    "desc": tc["desc"],
                    "r": tc["r"],
                    "y": tc["y"],
                    "b": tc["b"],
                    "n": tc["n"],
                    "v": tc["v"],
                    "i": tc["i"],
                    "enabled": False,
                })
                #print(f"[PROJECT CONFIG] NO MATCH → DISABLED: {tc['desc']} {tc['i']}")

        print("[PROJECT CONFIG] Merged test cases prepared")
        logger.info(f"[PROJECT CONFIG] Merged test cases prepared")
        self.populate_test_table(merged)

    def on_row_selected(self):
        print("[UI] on_row_selected() triggered")
        logger.info("Row selected")

        row = self.table.currentRow()
        print(f"[UI] Current row: {row}")

        if row < 0:
            return

        # ---------------- AC INPUTS ----------------
        r_text = self.table.cellWidget(row, 3).currentText().strip()
        y_text = self.table.cellWidget(row, 4).currentText().strip()
        b_text = self.table.cellWidget(row, 5).currentText().strip()
        n_text = self.table.cellWidget(row, 6).currentText().strip()

        # ---------------- DC OUTPUTS ----------------
        v_item = self.table.item(row, 7)  # Expected V
        i_item = self.table.item(row, 8)  # Expected I

        vdc_text = v_item.text().strip() if v_item else "0"
        idc_text = i_item.text().strip() if i_item else "0"

        print(f"r_text = '{r_text}'")
        print(f"y_text = '{y_text}'")
        print(f"b_text = '{b_text}'")
        print(f"n_text = '{n_text}'")
        print(f"v_item = '{v_item}'")
        print(f"i_item = '{i_item}'")

        print(f"[UI] Raw DC values: V='{vdc_text}', I='{idc_text}'")

        # ---------------- PARSE AC (NC SAFE) ----------------

        try:
            r = self.parse_ac(r_text)
            y = self.parse_ac(y_text)
            b = self.parse_ac(b_text)
            n = self.parse_ac(n_text)

            dc_v = float(vdc_text.replace("V", "").strip()) if vdc_text else 0.0
            dc_i = float(idc_text.replace("A", "").strip()) if idc_text else 0.0

        except ValueError as e:
            print("[UI] Parse error:", e)
            logger.error(f"Parse error: {e}")
            return

        print(f"[UI] AC: R={r}, Y={y}, B={b}")
        logger.info(f"[UI] AC: R={r}, {y}, {b}")
        print(f"[UI] DC: V={dc_v}, I={dc_i}")
        logger.info(f"[UI] DC: V={dc_v}, {dc_i}")

        # ---------------- GENERATE DIAGRAM ----------------
        png_bytes = generate_three_phase_diagram(
            r_voltage=r,
            y_voltage=y,
            b_voltage=b,
            neutral_state=n,
            dc_voltage=dc_v,
            dc_current=dc_i
        )

        if not png_bytes:
            print("[UI] Diagram generation failed")
            logger.error("Diagram generation failed")
            return

        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)

        # 🔴 REQUIRED FOR QLabel IMAGE UPDATE
        self.lbl_circuit.clear()
        self.lbl_circuit.setText("")

        self.lbl_circuit.setPixmap(
            pixmap.scaled(
                self.lbl_circuit.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

        self.lbl_circuit.repaint()

        print("[UI] Circuit diagram updated")
        logger.info("Circuit diagram updated")

    def parse_ac(self, val):
        if val.upper() == "NC":
            return "NC"
        if val.upper() == "C":
            return "C"
        return float(val.replace("V", "").strip())
