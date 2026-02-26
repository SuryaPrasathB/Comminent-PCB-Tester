import os
import re
import openpyxl
from datetime import datetime
from src.core.db_utils import get_test_results
from src.ui.settings_manager import SettingsManager
from src.core.logger import logger

class ReportGenerator:
    @staticmethod
    def generate_report(project_name, pcb_serial, overall_status):
        """
        Generates an Excel report for the given PCB test run.
        Returns the directory where the report was saved, or None on failure.
        """
        logger.info(f"Generating report for {project_name} - {pcb_serial} ({overall_status})")

        settings_mgr = SettingsManager()
        settings = settings_mgr.get_setting("report_export")

        if not settings:
            logger.error("Report export settings not found")
            return None

        template_path = settings.get("template_path", "")
        export_path = settings.get("export_path", "Report Export")
        mappings = settings.get("mappings", {})

        if not os.path.exists(template_path):
            logger.error(f"Template not found at {template_path}")
            return None

        # Fetch results
        results = get_test_results(project_name, pcb_serial)
        if not results:
            logger.warning(f"No test results found for {project_name} - {pcb_serial}")
            # We proceed to generate an empty report template if needed,
            # but usually empty results mean no test ran.
            # We'll continue to at least fill the header info.

        try:
            wb = openpyxl.load_workbook(template_path)
            ws = wb.active # Assume first sheet

            # Helper to set cell value safely
            def set_cell(cell_ref, value):
                if cell_ref:
                    try:
                        ws[cell_ref] = value
                    except Exception as e:
                        logger.error(f"Error setting cell {cell_ref}: {e}")

            # Fill Single Values
            set_cell(mappings.get("pcb_serial"), pcb_serial)
            set_cell(mappings.get("overall_status"), overall_status)

            now = datetime.now()
            set_cell(mappings.get("date"), now.strftime("%Y-%m-%d"))
            set_cell(mappings.get("time"), now.strftime("%H:%M:%S"))

            # Helper to parse "A6" -> ("A", 6)
            def parse_cell(cell_ref):
                if not cell_ref: return None, None
                match = re.match(r"([A-Z]+)(\d+)", str(cell_ref).strip())
                if match:
                    return match.group(1), int(match.group(2))
                return None, None

            # Map result keys (from DB) to mapping keys (from settings)
            col_map = {
                "description": mappings.get("description"),
                "r": mappings.get("r"),
                "y": mappings.get("y"),
                "b": mappings.get("b"),
                "n": mappings.get("n"),
                "expected_v": mappings.get("expected_v"),
                "expected_i": mappings.get("expected_i"),
                "measured_v": mappings.get("measured_v"),
                "measured_i": mappings.get("measured_i"),
                "result": mappings.get("result")
            }

            for i, row_data in enumerate(results):
                # Row index offset
                for field, start_cell in col_map.items():
                    col_letter, start_row = parse_cell(start_cell)
                    if col_letter and start_row:
                        target_cell = f"{col_letter}{start_row + i}"
                        val = row_data.get(field, "")
                        set_cell(target_cell, val)

            # Create Export Directory
            date_str = now.strftime("%Y-%m-%d")
            output_dir = os.path.join(export_path, date_str)
            os.makedirs(output_dir, exist_ok=True)

            # Filename: CPL-PSU-<PCB_Serial>_<Status>.xlsx
            # Sanitize PCB Serial for filename
            safe_serial = "".join([c for c in pcb_serial if c.isalnum() or c in ('-', '_')])
            filename = f"CPL-PSU-{safe_serial}_{overall_status}.xlsx"

            full_path = os.path.join(output_dir, filename)

            wb.save(full_path)
            logger.info(f"Report saved to {full_path}")

            return output_dir

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return None
