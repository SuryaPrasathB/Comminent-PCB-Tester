import os
from PySide6.QtWidgets import (
    QWidget, QTableWidgetItem, QCheckBox, QComboBox, QMessageBox,
    QVBoxLayout, QHeaderView, QAbstractItemView, QHBoxLayout, QSizePolicy
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtCore import QFile, QIODevice, Qt, QEvent, QPoint, QItemSelectionModel, QItemSelection
from PySide6.QtGui import QPixmap, QPainter, QMouseEvent

from config import default_test_cases, VOLTAGE_TAPPINGS, NEUTRAL_OPTIONS
from db_utils import save_project, load_projects, load_project_rows, delete_project
from circuit_diagram import generate_three_phase_diagram
from logs import logger
from new_ui.icons import IconHelper

# Helper for non-scrolling combo
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class DraggableComboBox(NoWheelComboBox):
    def __init__(self, table):
        super().__init__()
        self.table = table
        self.start_pos = None
        self.drag_active = False
        self.pending_bulk = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.start_row = self._get_row()

            current_row = self.start_row
            if current_row >= 0:
                self.table.setCurrentCell(current_row, self._get_col())

            modifiers = event.modifiers()

            if modifiers & Qt.ControlModifier:
                if current_row >= 0:
                    model = self.table.selectionModel()
                    idx = self.table.model().index(current_row, 0)
                    model.select(idx, QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
            elif modifiers & Qt.ShiftModifier:
                # Range selection from anchor
                anchor = self.table.currentRow() # This is the anchor usually
                if anchor == -1: anchor = current_row

                self._select_range(anchor, current_row)
            else:
                # Normal click: Clear and select, BUT if we are starting a drag,
                # we might want to keep selection if already selected?
                # "Click behavior"
                item = self.table.item(current_row, 0)
                if item and not item.isSelected():
                    self.table.clearSelection()
                    self.table.selectRow(current_row)

            # If we just click, we want the popup. But we wait for release to confirm it's not a drag.
            # We accept the event so parent doesn't handle it yet.
            event.accept()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            if (event.pos() - self.start_pos).manhattanLength() > 5:
                if not self.drag_active:
                    self.drag_active = True
                    self.grabMouse()
                    # Initialize drag selection range
                    if self.start_row >= 0:
                        self.table.clearSelection()
                        self.table.selectRow(self.start_row)

        if self.drag_active:
            # Range Select from start_row to current_row
            pos = self.table.viewport().mapFromGlobal(event.globalPos())
            idx = self.table.indexAt(pos)
            if idx.isValid():
                current_row = idx.row()
                if self.start_row >= 0:
                    self._select_range(self.start_row, current_row)

    def _select_range(self, start, end):
        r_min, r_max = min(start, end), max(start, end)
        selection = QItemSelection(
            self.table.model().index(r_min, 0),
            self.table.model().index(r_max, self.table.columnCount()-1)
        )
        self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def mouseReleaseEvent(self, event):
        if self.drag_active:
            self.drag_active = False
            self.releaseMouse()
            self.start_pos = None

            # Find target widget under mouse
            pos = self.table.viewport().mapFromGlobal(event.globalPos())
            idx = self.table.indexAt(pos)

            target_widget = self
            if idx.isValid():
                w = self.table.cellWidget(idx.row(), idx.column())
                if isinstance(w, DraggableComboBox):
                    target_widget = w

            # Prepare for bulk update
            target_widget.pending_bulk = True

            # Safely connect signal (disconnect old if exists to avoid dupes)
            try:
                target_widget.activated.disconnect(target_widget._on_bulk_activated)
            except: pass
            target_widget.activated.connect(target_widget._on_bulk_activated)

            target_widget.showPopup()

        else:
            # Normal click
            self.start_pos = None
            self.showPopup()

    def _on_bulk_activated(self, index):
        if self.pending_bulk:
            val = self.currentText()
            col = self._get_col()
            # Apply to all selected rows
            selected_rows = set()
            for item in self.table.selectedItems():
                selected_rows.add(item.row())

            current_row = self.table.currentRow()

            for r in selected_rows:
                w = self.table.cellWidget(r, col)
                if isinstance(w, QComboBox):
                    if r == current_row:
                        # Allow signal to fire for the current row so the diagram updates once
                        w.setCurrentText(val)
                    else:
                        # Block signals for others to prevent redundant updates
                        w.blockSignals(True)
                        w.setCurrentText(val)
                        w.blockSignals(False)

            self.pending_bulk = False

    def hidePopup(self):
        super().hidePopup()
        self.pending_bulk = False

    def _get_row(self):
        pos = self.table.viewport().mapFromGlobal(self.mapToGlobal(QPoint(0,0)))
        idx = self.table.indexAt(pos)
        return idx.row() if idx.isValid() else -1

    def _get_col(self):
        pos = self.table.viewport().mapFromGlobal(self.mapToGlobal(QPoint(0,0)))
        idx = self.table.indexAt(pos)
        return idx.column() if idx.isValid() else -1

class DraggableCheckboxContainer(QWidget):
    def __init__(self, table):
        super().__init__()
        self.table = table
        self.setObjectName("checkbox_container")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.checkbox = QCheckBox()
        self.checkbox.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.checkbox.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.checkbox)

        self.drag_active = False
        self.target_state = False
        self.last_drag_row = -1

    def isChecked(self):
        return self.checkbox.isChecked()

    def setChecked(self, state):
        self.checkbox.setChecked(state)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.target_state = not self.checkbox.isChecked()
            self.checkbox.setChecked(self.target_state)

            current_row = self._get_row()
            if current_row >= 0:
                self.table.setCurrentCell(current_row, 1)
                self.last_drag_row = current_row

            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                if current_row >= 0:
                    model = self.table.selectionModel()
                    idx = self.table.model().index(current_row, 0)
                    model.select(idx, QItemSelectionModel.Toggle | QItemSelectionModel.Rows)
            elif modifiers & Qt.ShiftModifier:
                anchor = self.table.currentRow()
                if anchor == -1: anchor = current_row
                self._select_range(anchor, current_row)
            else:
                # Exclusive selection unless already selected
                item = self.table.item(current_row, 0)
                if item and not item.isSelected():
                    self.table.clearSelection()
                    self.table.selectRow(current_row)

            # Always apply to current (and selection if any)
            # Standard: if simple click, we toggled current.
            # If multiple selected, we toggle all?
            # "Apply the same checked/unchecked state to all selected rows"

            # Force selection of current if it wasn't
            if not self.table.item(current_row, 0).isSelected():
                self.table.selectRow(current_row)

            # Bulk apply
            selected_rows = set(i.row() for i in self.table.selectedItems())
            for r in selected_rows:
                self._update_row_checkbox(r, self.target_state)

            self.drag_active = True
            self.grabMouse()

    def mouseMoveEvent(self, event):
        if self.drag_active:
            pos = self.table.viewport().mapFromGlobal(event.globalPos())
            idx = self.table.indexAt(pos)
            if idx.isValid():
                current_row = idx.row()

                # Interpolate if we moved too fast
                if self.last_drag_row != -1:
                    step = 1 if current_row > self.last_drag_row else -1
                    # Range from last_drag_row (exclusive) to current (inclusive)
                    # Actually, we want to cover the path.

                    r_start = self.last_drag_row
                    r_end = current_row

                    # We already handled last_drag_row. So start from next.
                    # Wait, if we moved up/down, we want to toggle everything in between.

                    rows_to_process = []
                    if r_start == r_end:
                        rows_to_process = [r_start] # Already processed?
                    else:
                        for r in range(r_start, r_end + step, step):
                            rows_to_process.append(r)

                    for r in rows_to_process:
                        if not self.table.item(r, 0).isSelected():
                            self.table.selectRow(r)
                        self._update_row_checkbox(r, self.target_state)

                self.last_drag_row = current_row

    def _select_range(self, start, end):
        r_min, r_max = min(start, end), max(start, end)
        selection = QItemSelection(
            self.table.model().index(r_min, 0),
            self.table.model().index(r_max, self.table.columnCount()-1)
        )
        self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def mouseReleaseEvent(self, event):
        if self.drag_active:
            self.drag_active = False
            self.releaseMouse()
            pass

    def _get_row(self):
        pos = self.table.viewport().mapFromGlobal(self.mapToGlobal(QPoint(0,0)))
        idx = self.table.indexAt(pos)
        return idx.row() if idx.isValid() else -1

    def _update_row_checkbox(self, row, state):
        widget = self.table.cellWidget(row, 1)
        if isinstance(widget, DraggableCheckboxContainer):
            widget.setChecked(state)

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

                self.svg_circuit = AntialiasedSvgWidget()
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
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        
        # =========================================================================
        # STYLE FIX: Row Highlighting & Native Checkbox
        # =========================================================================
        self.table.setStyleSheet("""
            /* Row Selection: Soft Blue-Grey to contrast with Checkboxes */
            QTableWidget::item:selected {
                background-color: #E6F0FF;
                color: #1a1a1a;
                font-weight: bold;
            }
            QTableWidget::item:selected:!active {
                background-color: #E6F0FF;
                color: #1a1a1a;
            }

            /* NATIVE CHECKBOX STYLING 
               Reverted to native look by removing 'indicator' styling.
               Forced 'color: black' to ensure visibility in light mode.
            */
            QCheckBox {
                spacing: 0px;
                background: transparent;
                color: black;
            }
            QCheckBox::indicator {
                border: 1px solid black;
                width: 12px;
                height: 12px;
                background: white;
            }
            QCheckBox::indicator:checked {
                background-color: black;
                border: 1px solid black;
                image: none;
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
        self.table.itemSelectionChanged.connect(self.update_widget_highlights)

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
            chk_widget = DraggableCheckboxContainer(self.table)
            chk_widget.setChecked(tc.get("enabled", True))
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
        combo = DraggableComboBox(self.table)
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

    def update_widget_highlights(self):
        """Updates the background/text color of cell widgets based on row selection."""
        rows = self.table.rowCount()
        
        # Row selection color (Soft Blue-Grey)
        SELECTION_BG = "#E6F0FF" 
        SELECTION_TXT = "#1a1a1a"
        
        for r in range(rows):
            # Check if row is selected by checking the first item
            item = self.table.item(r, 0)
            is_sel = item.isSelected() if item else False

            bg = SELECTION_BG if is_sel else "transparent"
            color = SELECTION_TXT if is_sel else "black"
            font_weight = "bold" if is_sel else "normal"

            # Helper to style widgets
            def apply_style(widget, is_combo=False):
                if not widget: return
                if is_combo:
                    # Preserve specific styling for combos (hide arrow, etc)
                    widget.setStyleSheet(f"""
                        QComboBox {{
                            border: none;
                            padding-left: 2px;
                            background-color: {bg};
                            color: {color};
                            font-weight: {font_weight};
                        }}
                        QComboBox::drop-down {{
                            border: none;
                            width: 0px;
                        }}
                        QComboBox QAbstractItemView {{
                            color: black;
                            background-color: white;
                            selection-background-color: {SELECTION_BG};
                            selection-color: {SELECTION_TXT};
                        }}
                    """)
                # NOTE: We DO NOT style the checkbox here anymore. 
                # It is handled globally by self.table.setStyleSheet() in load_ui()

            apply_style(self.table.cellWidget(r, 3), is_combo=True)
            apply_style(self.table.cellWidget(r, 4), is_combo=True)
            apply_style(self.table.cellWidget(r, 5), is_combo=True)
            apply_style(self.table.cellWidget(r, 6), is_combo=True)

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