import os
import datetime
from PySide6.QtWidgets import QWidget, QRadioButton, QLineEdit, QPushButton, QFileDialog, QMessageBox, QDoubleSpinBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice
from PySide6.QtWidgets import QApplication

from src.ui.settings_manager import SettingsManager
from src.ui.theme import AppTheme
from src.core.logger import logger

class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.load_ui()
        self.bind_widgets()
        self.initialize_state()
        self.setup_connections()
        logger.info("SettingsView initialized")

    def load_ui(self):
        loader = QUiLoader()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(base_dir, "..", "forms", "settings.ui")

        ui_file = QFile(ui_path)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error(f"Cannot open settings.ui at {ui_path}")
            raise RuntimeError("Cannot open settings.ui")

        self.ui = loader.load(ui_file, self)
        ui_file.close()

        # Layout integration
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)
        self.setLayout(layout)

    def bind_widgets(self):
        # Appearance
        self.radio_light = self.findChild(QRadioButton, "radio_light")
        self.radio_dark = self.findChild(QRadioButton, "radio_dark")

        # Report Export
        self.txt_template = self.findChild(QLineEdit, "lineEdit_templatePath")
        self.txt_export = self.findChild(QLineEdit, "lineEdit_exportPath")
        self.btn_browse_template = self.findChild(QPushButton, "btn_browse_template")
        self.btn_browse_export = self.findChild(QPushButton, "btn_browse_export")

        # Single Mappings
        self.map_sn = self.findChild(QLineEdit, "lineEdit_map_sn")
        self.map_status = self.findChild(QLineEdit, "lineEdit_map_status")
        self.map_timestamp = self.findChild(QLineEdit, "lineEdit_map_timestamp")
        self.map_project = self.findChild(QLineEdit, "lineEdit_map_project")

        # Column Mappings
        self.map_sn_col = self.findChild(QLineEdit, "lineEdit_map_sn_col")
        self.map_desc = self.findChild(QLineEdit, "lineEdit_map_desc")
        self.map_r = self.findChild(QLineEdit, "lineEdit_map_r")
        self.map_y = self.findChild(QLineEdit, "lineEdit_map_y")
        self.map_b = self.findChild(QLineEdit, "lineEdit_map_b")
        self.map_n = self.findChild(QLineEdit, "lineEdit_map_n")
        self.map_expv = self.findChild(QLineEdit, "lineEdit_map_expv")
        self.map_expi = self.findChild(QLineEdit, "lineEdit_map_expi")
        self.map_measv = self.findChild(QLineEdit, "lineEdit_map_measv")
        self.map_measi = self.findChild(QLineEdit, "lineEdit_map_measi")
        self.map_result = self.findChild(QLineEdit, "lineEdit_map_result")

        self.btn_save_report = self.findChild(QPushButton, "btn_save_report")

        # Test Parameters
        self.spinBox_stab_time = self.findChild(QDoubleSpinBox, "spinBox_stab_time")
        self.spinBox_curr_tol = self.findChild(QDoubleSpinBox, "spinBox_curr_tol")
        self.spinBox_zero_curr = self.findChild(QDoubleSpinBox, "spinBox_zero_curr")

        self.spinBox_0_0_vu = self.findChild(QDoubleSpinBox, "spinBox_0_0_vu")
        self.spinBox_0_0_vl = self.findChild(QDoubleSpinBox, "spinBox_0_0_vl")
        self.spinBox_0_5_vu = self.findChild(QDoubleSpinBox, "spinBox_0_5_vu")
        self.spinBox_0_5_vl = self.findChild(QDoubleSpinBox, "spinBox_0_5_vl")
        self.spinBox_1_25_vu = self.findChild(QDoubleSpinBox, "spinBox_1_25_vu")
        self.spinBox_1_25_vl = self.findChild(QDoubleSpinBox, "spinBox_1_25_vl")
        self.spinBox_2_5_vu = self.findChild(QDoubleSpinBox, "spinBox_2_5_vu")
        self.spinBox_2_5_vl = self.findChild(QDoubleSpinBox, "spinBox_2_5_vl")

        self.btn_save_test_params = self.findChild(QPushButton, "btn_save_test_params")

    def initialize_state(self):
        # Theme
        current_theme = self.settings_manager.get_setting("theme", AppTheme.LIGHT)
        if current_theme == AppTheme.LIGHT:
            self.radio_light.setChecked(True)
        else:
            self.radio_dark.setChecked(True)

        # Report
        report = self.settings_manager.get_setting("report_export") or {}
        self.txt_template.setText(report.get("template_path", ""))
        self.txt_export.setText(report.get("export_path", ""))

        mappings = report.get("mappings", {})
        self.map_sn.setText(mappings.get("pcb_serial", ""))
        self.map_status.setText(mappings.get("overall_status", ""))
        self.map_timestamp.setText(mappings.get("timestamp", ""))
        self.map_project.setText(mappings.get("project_name", ""))

        self.map_sn_col.setText(mappings.get("sn", ""))
        self.map_desc.setText(mappings.get("description", ""))
        self.map_r.setText(mappings.get("r", ""))
        self.map_y.setText(mappings.get("y", ""))
        self.map_b.setText(mappings.get("b", ""))
        self.map_n.setText(mappings.get("n", ""))
        self.map_expv.setText(mappings.get("expected_v", ""))
        self.map_expi.setText(mappings.get("expected_i", ""))
        self.map_measv.setText(mappings.get("measured_v", ""))
        self.map_measi.setText(mappings.get("measured_i", ""))
        self.map_result.setText(mappings.get("result", ""))

        # Test Parameters
        test_params = self.settings_manager.get_setting("test_parameters") or {}
        self.spinBox_stab_time.setValue(test_params.get("stabilization_time", 2.0))
        self.spinBox_curr_tol.setValue(test_params.get("current_tolerance_percent", 20.0))
        self.spinBox_zero_curr.setValue(test_params.get("zero_current_limit", 0.2))

        limit_table = test_params.get("limit_table", {})

        if "0.0" in limit_table:
            self.spinBox_0_0_vu.setValue(limit_table["0.0"].get("v_upper", 5.75))
            self.spinBox_0_0_vl.setValue(limit_table["0.0"].get("v_lower", 5.40))
        if "0.5" in limit_table:
            self.spinBox_0_5_vu.setValue(limit_table["0.5"].get("v_upper", 5.75))
            self.spinBox_0_5_vl.setValue(limit_table["0.5"].get("v_lower", 5.40))
        if "1.25" in limit_table:
            self.spinBox_1_25_vu.setValue(limit_table["1.25"].get("v_upper", 5.75))
            self.spinBox_1_25_vl.setValue(limit_table["1.25"].get("v_lower", 5.30))
        if "2.5" in limit_table:
            self.spinBox_2_5_vu.setValue(limit_table["2.5"].get("v_upper", 5.75))
            self.spinBox_2_5_vl.setValue(limit_table["2.5"].get("v_lower", 5.10))


    def setup_connections(self):
        self.radio_light.toggled.connect(self.on_theme_changed)
        self.radio_dark.toggled.connect(self.on_theme_changed)

        self.btn_browse_template.clicked.connect(self.browse_template)
        self.btn_browse_export.clicked.connect(self.browse_export)
        self.btn_save_report.clicked.connect(self.save_report_config)
        self.btn_save_test_params.clicked.connect(self.save_test_params)

    def on_theme_changed(self):
        # Determine selected theme
        if self.radio_light.isChecked():
            new_theme = AppTheme.LIGHT
        else:
            new_theme = AppTheme.DARK

        # Only apply if changed
        current_theme = self.settings_manager.get_setting("theme", AppTheme.LIGHT)
        if new_theme != current_theme:
            logger.info(f"Theme changing to {new_theme}")
            self.settings_manager.save_setting("theme", new_theme)
            AppTheme.apply_theme(QApplication.instance(), new_theme)

    def browse_template(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Template", "", "Excel Files (*.xlsx *.xls)")
        if fname:
            self.txt_template.setText(fname)

    def browse_export(self):
        dname = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if dname:
            self.txt_export.setText(dname)

    def save_report_config(self):
        config = {
            "template_path": self.txt_template.text(),
            "export_path": self.txt_export.text(),
            "mappings": {
                "project_name": self.map_project.text(),
                "pcb_serial": self.map_sn.text(),
                "overall_status": self.map_status.text(),
                "timestamp": self.map_timestamp.text(),
                "sn": self.map_sn_col.text(),
                "description": self.map_desc.text(),
                "r": self.map_r.text(),
                "y": self.map_y.text(),
                "b": self.map_b.text(),
                "n": self.map_n.text(),
                "expected_v": self.map_expv.text(),
                "expected_i": self.map_expi.text(),
                "measured_v": self.map_measv.text(),
                "measured_i": self.map_measi.text(),
                "result": self.map_result.text()
            }
        }

        self.settings_manager.save_setting("report_export", config)
        QMessageBox.information(self, "Saved", "Report configuration saved successfully.")
        logger.info("Report configuration saved by user")

        try:
            from src.core.report_uploader import ReportUploader
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            folder = os.path.join(config["export_path"], date_str)
            ReportUploader().update_folder(folder)
        except Exception as e:
            logger.warning(f"Failed to update uploader immediately: {e}")

    def save_test_params(self):
        config = {
            "stabilization_time": self.spinBox_stab_time.value(),
            "current_tolerance_percent": self.spinBox_curr_tol.value(),
            "zero_current_limit": self.spinBox_zero_curr.value(),
            "limit_table": {
                "0.0": {"v_upper": self.spinBox_0_0_vu.value(), "v_lower": self.spinBox_0_0_vl.value()},
                "0.5": {"v_upper": self.spinBox_0_5_vu.value(), "v_lower": self.spinBox_0_5_vl.value()},
                "1.25": {"v_upper": self.spinBox_1_25_vu.value(), "v_lower": self.spinBox_1_25_vl.value()},
                "2.5": {"v_upper": self.spinBox_2_5_vu.value(), "v_lower": self.spinBox_2_5_vl.value()}
            }
        }
        self.settings_manager.save_setting("test_parameters", config)
        QMessageBox.information(self, "Saved", "Test parameters saved successfully.")
        logger.info("Test parameters saved by user")
