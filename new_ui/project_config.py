import os
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QCheckBox, QComboBox, QMessageBox,
    QVBoxLayout, QHeaderView, QAbstractItemView, QHBoxLayout, QSizePolicy
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtCore import QFile, QIODevice, Qt, QEvent
from PySide6.QtGui import QPixmap, QPainter

from config import default_test_cases, VOLTAGE_TAPPINGS, NEUTRAL_OPTIONS
from db_utils import save_project, load_projects, load_project_rows, delete_project
from circuit_diagram import generate_three_phase_diagram
from logs import logger
from new_ui.icons import IconHelper

# Helper for non-scrolling combo
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class AntialiasedSvgWidget(QSvgWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.renderer().render(painter)
        painter.end()

class ProjectConfigView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New ProjectConfigView")
        self.load_ui()
        self.setup_icons()
        self.connect_signals()
        
        # State for resizing
        self.current_diagram_svg = None

        # Initial Population
        self.refresh_projects()
        self.populate_test_table(default_test_cases)
        
        # Table Header Config
        self.configure_table_headers()

    def update_diagram(self):
        if not self.current_diagram_svg: return
        try:
            self.svg_circuit.load(self.current_diagram_svg)
        except Exception as e:
            logger.error(f"Error loading SVG diagram: {e}")

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
        
        # Replace QLabel with QSvgWidget
        self.lbl_circuit = self.findChild(QWidget, "label_circuitDiagram")
        if self.lbl_circuit:
            parent = self.lbl_circuit.parentWidget()
            layout = parent.layout()
            if layout:
                # Create a container to center the diagram
                self.circuit_container = QWidget()
                container_layout = QVBoxLayout(self.circuit_container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                # Removed AlignCenter to allow the widget to expand horizontally;
                # SVG's preserveAspectRatio="xMidYMid meet" handles the actual centering/aspect ratio.

                self.svg_circuit = AntialiasedSvgWidget()
                # Use Preferred size policy so it respects SVG size hint but can shrink/grow slightly if needed
                # However, with AlignCenter in layout, it should stick to its size hint or available space.
                self.svg_circuit.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

                container_layout.addWidget(self.svg_circuit)

                # Replace the widget in-place to preserve layout order
                layout.replaceWidget(self.lbl_circuit, self.circuit_container)
                self.lbl_circuit.deleteLater()
            else:
                logger.error("Could not find layout for circuit label")
        else:
            logger.error("Could not find label_circuitDiagram")

        self.btn_save = self.findChild(QWidget, "pushButton_save")
        self.btn_delete = self.findChild(QWidget, "pushButton_delete")
        self.btn_up = self.findChild(QWidget, "pushButton_moveUp")
        self.btn_down = self.findChild(QWidget, "pushButton_moveDown")

        # Table Config
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        
        # Row highlighting style
        self.table.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #0078d7;
                color: white;
                font-weight: bold;
            }
        """)
        
    def configure_table_headers(self):
        header = self.table.horizontalHeader()
        
        # "R Tap", "Y Tap", "B Tap", "Neutral", "Exp V", "Exp I" (indices 3,4,5,6,7,8)
        fixed_width = 80
        for i in [3, 4, 5, 6, 7, 8]:
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, fixed_width)
            
        # Description (index 2) - stretch
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        # S.No (0) and Enable (1) - ResizeToContents
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

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

            # Enable Checkbox (Centered)
            chk = QCheckBox()
            chk.setChecked(tc.get("enabled", True))
            
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0,0,0,0)
            self.table.setCellWidget(row, 1, chk_widget)

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
        
        # Apply stylesheet to hide arrow when not active/hovered, but make it accessible
        # User request: "dont display the combo box arrows, when that particular cell is clean, open combo box."
        combo.setStyleSheet("""
            QComboBox {
                border: none;
                padding-left: 2px;
            }
            QComboBox::drop-down {
                border: none;
                width: 0px; 
            }
        """)
        
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
        # Helper to get checkbox state from widget container
        def get_checked(row):
            widget = self.table.cellWidget(row, 1) # QWidget container
            if widget:
                # Find QCheckBox child
                cb = widget.findChild(QCheckBox)
                return cb.isChecked() if cb else False
            return False
            
        def set_checked(row, state):
            widget = self.table.cellWidget(row, 1)
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb: cb.setChecked(state)

        def read_row(row):
            return {
                "enabled": get_checked(row),
                "desc": self.table.item(row, 2).text(),
                "r": self.table.cellWidget(row, 3).currentText(),
                "y": self.table.cellWidget(row, 4).currentText(),
                "b": self.table.cellWidget(row, 5).currentText(),
                "n": self.table.cellWidget(row, 6).currentText(),
                "v": self.table.item(row, 7).text(),
                "i": self.table.item(row, 8).text(),
            }
        def write_row(row, data):
            set_checked(row, data["enabled"])
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

        def get_checked(row):
            widget = self.table.cellWidget(row, 1)
            if widget:
                cb = widget.findChild(QCheckBox)
                return cb.isChecked() if cb else False
            return False

        data = []
        for row in range(self.table.rowCount()):
            if not get_checked(row): continue
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

            svg_data = generate_three_phase_diagram(r, y, b, n, dc_v, dc_i)
            if svg_data:
                self.current_diagram_svg = svg_data
                self.update_diagram()

        except Exception as e:
            logger.error(f"Diagram error: {e}")

    def parse_ac(self, val):
        if val in ["NC", "C"]: return val
        return float(val.replace("V","").strip())
