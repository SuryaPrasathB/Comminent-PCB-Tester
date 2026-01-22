import os
import mysql.connector
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QTableWidgetItem, QFileDialog, QAbstractItemView, QHeaderView
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, QDateTime, QTime, QDate

from config import DB_CONFIG
from logs import logger
from new_ui.icons import IconHelper
import openpyxl

class ResultsView(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing New ResultsView")
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
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Description column
        header.setSectionResizeMode(12, QHeaderView.Stretch) # Result column
        header.setMinimumSectionSize(50)

        # Row Height / Word Wrap
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

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
            SELECT project_name, pcb_serial, sn, description,
                   r, y, b, n,
                   expected_v, expected_i,
                   measured_v, measured_i,
                   result, tested_at
            FROM test_results
            WHERE pcb_serial = %s
            ORDER BY tested_at DESC
        """
        self._run_query(query, (serial,))

    def fetch_by_date(self):
        from_dt = self.dt_from.dateTime().toPython()
        to_dt   = self.dt_to.dateTime().toPython()

        query = """
            SELECT project_name, pcb_serial, sn, description,
                   r, y, b, n,
                   expected_v, expected_i,
                   measured_v, measured_i,
                   result, tested_at
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
        self.table.setRowCount(0)
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))

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
