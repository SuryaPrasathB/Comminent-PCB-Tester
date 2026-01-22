from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

class AppTheme:
    LIGHT = "Light"
    DARK = "Dark"

    # Brand Colors
    PRIMARY_COLOR = "#007ACC"
    ACCENT_COLOR = "#0098FF"

    # Dark Palette
    DARK_BG = "#1E1E1E"
    DARK_SURFACE = "#252526"
    DARK_TEXT = "#CCCCCC"
    DARK_BORDER = "#3E3E42"

    # Light Palette
    LIGHT_BG = "#F3F3F3"
    LIGHT_SURFACE = "#FFFFFF"
    LIGHT_TEXT = "#333333"
    LIGHT_BORDER = "#D0D0D0"

    @staticmethod
    def apply_theme(app, theme_name):
        if theme_name == AppTheme.DARK:
            AppTheme._apply_dark_palette(app)
            AppTheme._apply_stylesheet(app, is_dark=True)
        else:
            AppTheme._apply_light_palette(app)
            AppTheme._apply_stylesheet(app, is_dark=False)

    @staticmethod
    def _apply_dark_palette(app):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(AppTheme.DARK_BG))
        palette.setColor(QPalette.WindowText, QColor(AppTheme.DARK_TEXT))
        palette.setColor(QPalette.Base, QColor(AppTheme.DARK_SURFACE))
        palette.setColor(QPalette.AlternateBase, QColor(AppTheme.DARK_BG))
        palette.setColor(QPalette.ToolTipBase, QColor(AppTheme.DARK_TEXT))
        palette.setColor(QPalette.ToolTipText, QColor(AppTheme.DARK_BG))
        palette.setColor(QPalette.Text, QColor(AppTheme.DARK_TEXT))
        palette.setColor(QPalette.Button, QColor(AppTheme.DARK_SURFACE))
        palette.setColor(QPalette.ButtonText, QColor(AppTheme.DARK_TEXT))
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(AppTheme.ACCENT_COLOR))
        palette.setColor(QPalette.Highlight, QColor(AppTheme.PRIMARY_COLOR))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)

    @staticmethod
    def _apply_light_palette(app):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(AppTheme.LIGHT_BG))
        palette.setColor(QPalette.WindowText, QColor(AppTheme.LIGHT_TEXT))
        palette.setColor(QPalette.Base, QColor(AppTheme.LIGHT_SURFACE))
        palette.setColor(QPalette.AlternateBase, QColor("#EAEAEA"))
        palette.setColor(QPalette.ToolTipBase, Qt.white)
        palette.setColor(QPalette.ToolTipText, Qt.black)
        palette.setColor(QPalette.Text, QColor(AppTheme.LIGHT_TEXT))
        palette.setColor(QPalette.Button, QColor(AppTheme.LIGHT_SURFACE))
        palette.setColor(QPalette.ButtonText, QColor(AppTheme.LIGHT_TEXT))
        palette.setColor(QPalette.Link, QColor(AppTheme.PRIMARY_COLOR))
        palette.setColor(QPalette.Highlight, QColor(AppTheme.PRIMARY_COLOR))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)

    @staticmethod
    def _apply_stylesheet(app, is_dark):
        # Common styles
        base_css = """
            QMainWindow { background: %BG%; }
            QWidget { font-family: "Segoe UI", "Roboto", sans-serif; font-size: 10pt; }

            /* Inputs */
            QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit {
                background-color: %SURFACE%;
                color: %TEXT%;
                border: 1px solid %BORDER%;
                border-radius: 4px;
                padding: 4px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid %PRIMARY%;
            }

            /* Buttons */
            QPushButton {
                background-color: %SURFACE%;
                border: 1px solid %BORDER%;
                border-radius: 4px;
                padding: 6px 12px;
                color: %TEXT%;
            }
            QPushButton:hover {
                background-color: %Highlight%; /* slightly lighter/darker */
                border: 1px solid %PRIMARY%;
            }
            QPushButton:pressed {
                background-color: %PRIMARY%;
                color: white;
            }
            QPushButton#btn_primary {
                background-color: %PRIMARY%;
                color: white;
                border: none;
                font-weight: bold;
            }
            QPushButton#btn_primary:hover {
                background-color: %ACCENT%;
            }

            /* Tables */
            QTableWidget {
                background-color: %SURFACE%;
                alternate-background-color: %ALT_BG%;
                gridline-color: %BORDER%;
                color: %TEXT%;
                selection-background-color: %PRIMARY%;
                selection-color: white;
                border: 1px solid %BORDER%;
            }
            QHeaderView::section {
                background-color: %BG%;
                color: %TEXT%;
                padding: 4px;
                border: 1px solid %BORDER%;
            }

            /* Scrollbars */
            QScrollBar:vertical {
                border: none;
                background: %BG%;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: %BORDER%;
                min-height: 20px;
                border-radius: 5px;
            }

            /* Tabs */
            QTabWidget::pane { border: 1px solid %BORDER%; }
            QTabBar::tab {
                background: %BG%;
                color: %TEXT%;
                padding: 8px 16px;
                border: 1px solid %BORDER%;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: %SURFACE%;
                border-bottom: 2px solid %PRIMARY%;
            }
        """

        # Replace placeholders
        if is_dark:
            replacements = {
                "%BG%": AppTheme.DARK_BG,
                "%SURFACE%": AppTheme.DARK_SURFACE,
                "%TEXT%": AppTheme.DARK_TEXT,
                "%BORDER%": AppTheme.DARK_BORDER,
                "%PRIMARY%": AppTheme.PRIMARY_COLOR,
                "%ACCENT%": AppTheme.ACCENT_COLOR,
                "%ALT_BG%": AppTheme.DARK_BG,
                "%Highlight%": "#333333"
            }
        else:
            replacements = {
                "%BG%": AppTheme.LIGHT_BG,
                "%SURFACE%": AppTheme.LIGHT_SURFACE,
                "%TEXT%": AppTheme.LIGHT_TEXT,
                "%BORDER%": AppTheme.LIGHT_BORDER,
                "%PRIMARY%": AppTheme.PRIMARY_COLOR,
                "%ACCENT%": AppTheme.ACCENT_COLOR,
                "%ALT_BG%": "#F9F9F9",
                "%Highlight%": "#E5F1FB"
            }

        css = base_css
        for key, val in replacements.items():
            css = css.replace(key, val)

        app.setStyleSheet(css)
