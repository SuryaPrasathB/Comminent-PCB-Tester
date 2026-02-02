import os
import mysql.connector
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QTableWidgetItem, QFileDialog, QAbstractItemView, QHeaderView,
    QMenu, QInputDialog
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QDateTime, QTime, QDate, Qt

from config import DB_CONFIG
from logs import logger
from new_ui.icons import IconHelper
import openpyxl

class ResultsView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New ResultsView")
        self.active_filters = {}
        self.load_ui()
        self.setup_icons()
        self.connect_signals()

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "forms", "results.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open results.ui at {ui_path}")
            raise RuntimeError("Cannot open results.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

        # Widget Binding
        self.table = self.findChild(QWidget, "tableWidget_results")
        self.txt_serial = self.findChild(QWidget, "lineEdit_serial")
        self.dt_from = self.findChild(QWidget, "dateTimeEdit_from")
        self.dt_to = self.findChild(QWidget, "dateTimeEdit_to")
        self.chk_pdf = self.findChild(QWidget, "checkBox_pdf")
        self.chk_excel = self.findChild(QWidget, "checkBox_excel")

        self.btn_fetch_serial = self.findChild(QWidget, "pushButton_fetchSerial")
        self.btn_fetch_date = self.findChild(QWidget, "pushButton_fetchDate")
        self.btn_export = self.findChild(QWidget, "pushButton_export")

        # Config
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setRowCount(0)

        # Header Configuration
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Description column (index 4)
        header.setSectionResizeMode(13, QHeaderView.Stretch) # Result column (index 13)
        header.setMinimumSectionSize(50)

        # Row Height / Word Wrap
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSortingEnabled(True)

        # Row highlighting style and cell padding
        self.table.setStyleSheet("""
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

        # Default Dates
        today = QDate.currentDate()
        self.dt_from.setDateTime(QDateTime(today, QTime(0, 0)))
        self.dt_to.setDateTime(QDateTime(today, QTime(23, 59)))

    def setup_icons(self):
        IconHelper.apply_icon(self.btn_fetch_serial, "search")
        IconHelper.apply_icon(self.btn_fetch_date, "search")
        IconHelper.apply_icon(self.btn_export, "save")

    def connect_signals(self):
        self.btn_fetch_serial.clicked.connect(self.fetch_by_serial)
        self.btn_fetch_date.clicked.connect(self.fetch_by_date)
        self.btn_export.clicked.connect(self.export_results)

        # Header Context Menu
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.show_header_menu)

        # Checkbox Interlock
        self.chk_pdf.clicked.connect(self.on_pdf_clicked)
        self.chk_excel.clicked.connect(self.on_excel_clicked)

    def on_pdf_clicked(self):
        if self.chk_pdf.isChecked():
            self.chk_excel.setChecked(False)

    def on_excel_clicked(self):
        if self.chk_excel.isChecked():
            self.chk_pdf.setChecked(False)

    def show_header_menu(self, pos):
        header = self.table.horizontalHeader()
        logical_index = header.logicalIndexAt(pos)

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { color: white; }")

        col_name = header.model().headerData(logical_index, Qt.Horizontal)
        filter_action = menu.addAction(f"Filter by '{col_name}'")
        clear_action = menu.addAction("Clear All Filters")

        action = menu.exec(header.mapToGlobal(pos))

        if action == filter_action:
            self.filter_column(logical_index)
        elif action == clear_action:
            self.clear_filters()

    def filter_column(self, col_index):
        header_text = self.table.model().headerData(col_index, Qt.Horizontal)
        text, ok = QInputDialog.getText(self, "Filter", f"Show rows where {header_text} contains:")
        if ok:
            if text:
                self.active_filters[col_index] = text.lower()
            else:
                if col_index in self.active_filters:
                    del self.active_filters[col_index]
            self.apply_filters()

    def clear_filters(self):
        self.active_filters.clear()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)

    def apply_filters(self):
        for row in range(self.table.rowCount()):
            should_show = True
            for col, text in self.active_filters.items():
                item = self.table.item(row, col)
                if not item or text not in item.text().lower():
                    should_show = False
                    break
            self.table.setRowHidden(row, not should_show)

    # =========================================================================
    # LOGIC (Ported)
    # =========================================================================

    def _db_connect(self):
        return mysql.connector.connect(**DB_CONFIG)

    def fetch_by_serial(self):
        serial = self.txt_serial.text().strip()
        if not serial:
            QMessageBox.warning(self, "Input", "Enter PCB Serial Number")
            return

        query = """
            SELECT sn, tested_at, project_name, pcb_serial, description,
                   r, y, b, n,
                   expected_v, expected_i,
                   measured_v, measured_i,
                   result
            FROM test_results
            WHERE pcb_serial = %s
            ORDER BY tested_at DESC
        """
        self._run_query(query, (serial,))

    def fetch_by_date(self):
        from_dt = self.dt_from.dateTime().toPython()
        to_dt   = self.dt_to.dateTime().toPython()

        query = """
            SELECT sn, tested_at, project_name, pcb_serial, description,
                   r, y, b, n,
                   expected_v, expected_i,
                   measured_v, measured_i,
                   result
            FROM test_results
            WHERE tested_at BETWEEN %s AND %s
            ORDER BY tested_at DESC
        """
        self._run_query(query, (from_dt, to_dt))

    def _run_query(self, query, params):
        try:
            conn = self._db_connect()
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                QMessageBox.information(self, "Results", "No results found")
                self.table.setRowCount(0)
                return

            self.populate_table(rows)

        except Exception as e:
            logger.error(f"DB Error: {e}")
            QMessageBox.critical(self, "Database Error", str(e))

    def populate_table(self, rows):
        self.active_filters.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, value in enumerate(row):
                item = QTableWidgetItem()

                # Check for numeric types for sorting
                if isinstance(value, (int, float)):
                    item.setData(Qt.EditRole, value)
                    item.setText(str(value))
                elif hasattr(value, 'timestamp'): # Handle datetime objects
                    item.setData(Qt.EditRole, value.timestamp())
                    item.setText(str(value))
                else:
                    item.setText(str(value))

                # Alignment
                if c == 4: # Description
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                elif c == 13: # Result
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)

                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)

    def export_results(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "No data to export")
            return

        pdf = self.chk_pdf.isChecked()
        excel = self.chk_excel.isChecked()

        if not pdf and not excel:
            QMessageBox.warning(self, "Export", "Select PDF or Excel")
            return

        if excel: self.export_excel()
        if pdf: self.export_pdf()

    def export_excel(self):
        from datetime import datetime
        import pandas as pd

        path, _ = QFileDialog.getSaveFileName(self, "Save Excel", "", "Excel Files (*.xlsx)")
        if not path: return

        try:
            # Gather Data
            all_headers = [self.table.horizontalHeaderItem(i).text().strip() for i in range(self.table.columnCount())]
            data = []
            for r in range(self.table.rowCount()):
                row_data = []
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    row_data.append(item.text() if item else "")
                data.append(row_data)

            df = pd.DataFrame(data, columns=all_headers)

            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, startrow=4, sheet_name="Test Results")
                ws = writer.sheets["Test Results"]
                ws.cell(row=1, column=1).value = "PCB TEST REPORT"
                ws.cell(row=3, column=1).value = f"Generated: {datetime.now()}"

            QMessageBox.information(self, "Export", "Excel exported successfully")

        except Exception as e:
            logger.error(f"Excel Export Error: {e}")
            QMessageBox.critical(self, "Export Failed", str(e))

    def export_pdf(self):
        # Using simplified port for brevity, assuming reportlab exists as per original code
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
        from datetime import datetime

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "", "PDF Files (*.pdf)")
        if not path: return

        try:
            c = canvas.Canvas(path, pagesize=landscape(A4))
            width, height = landscape(A4)

            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(width/2, height-40, "PCB TEST REPORT")
            c.setFont("Helvetica", 10)
            c.drawString(40, height-70, f"Generated: {datetime.now()}")

            # Simple Table Dump
            y = height - 120
            row_h = 20
            x_start = 30

            # Draw Headers
            c.setFont("Helvetica-Bold", 8)
            x = x_start
            for i in range(self.table.columnCount()):
                h = self.table.horizontalHeaderItem(i).text()
                if h.lower() in ["r","y","b","n"]: continue # Skip small cols to save space?
                c.drawString(x, y, h)
                x += 70 # Fixed width for simplicity in this port

            y -= row_h
            c.setFont("Helvetica", 8)

            for r in range(self.table.rowCount()):
                x = x_start
                for i in range(self.table.columnCount()):
                    if self.table.horizontalHeaderItem(i).text().lower() in ["r","y","b","n"]: continue
                    item = self.table.item(r, i)
                    val = item.text() if item else ""
                    c.drawString(x, y, val[:15])
                    x += 70
                y -= row_h
                if y < 50:
                    c.showPage()
                    y = height - 50

            c.save()
            QMessageBox.information(self, "Export", "PDF exported successfully")

        except Exception as e:
            logger.error(f"PDF Export Error: {e}")
            QMessageBox.critical(self, "Export Failed", str(e))
