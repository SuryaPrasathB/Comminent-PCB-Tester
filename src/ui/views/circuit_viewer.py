import os
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QScrollArea, QSizePolicy
)
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QEvent
from PySide6.QtGui import QPainter, QPixmap, QCursor

from src.core.logger import logger

class CircuitFullScreenDialog(QDialog):
    def __init__(self, svg_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Circuit Diagram - Full Screen")
        self.setWindowState(Qt.WindowMaximized)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header with Close Button
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)
        layout.addLayout(header_layout)

        # SVG Display
        self.svg_widget = QSvgWidget()
        self.svg_widget.load(svg_data)

        # Add to layout
        layout.addWidget(self.svg_widget)

class ZoomOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(300, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1) # Thin border space

        self.label = QLabel()
        self.label.setScaledContents(True) # Ensure pixmap scales to label
        self.label.setStyleSheet("border: 2px solid #007ACC; background-color: white;")
        layout.addWidget(self.label)

    def update_content(self, pixmap):
        self.label.setPixmap(pixmap)

class CircuitPreviewWidget(QSvgWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.current_svg_data = None
        self.zoom_overlay = None
        self.high_res_pixmap = None
        self.setMouseTracking(True) # Essential for hover events without clicking

    def load(self, data):
        self.current_svg_data = data
        super().load(data)
        # Pre-render high res pixmap when new data is loaded
        self._generate_high_res_pixmap()

    def _generate_high_res_pixmap(self):
        if not self.current_svg_data:
            self.high_res_pixmap = None
            return

        renderer = QSvgRenderer(self.current_svg_data)
        if not renderer.isValid():
            return

        # Render at a large size (e.g. 1500px width)
        default_size = renderer.defaultSize()
        if default_size.isEmpty():
            default_size = QSize(800, 600)

        scale = 1500 / default_size.width()
        target_size = default_size * scale

        image = QPixmap(target_size.toSize())
        image.fill(Qt.transparent)

        painter = QPainter(image)
        renderer.render(painter)
        painter.end()

        self.high_res_pixmap = image

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.current_svg_data:
            dialog = CircuitFullScreenDialog(self.current_svg_data, self.window())
            dialog.exec()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self.zoom_overlay:
            self.zoom_overlay = ZoomOverlay(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.zoom_overlay:
            self.zoom_overlay.hide()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if not self.high_res_pixmap or not self.zoom_overlay:
            super().mouseMoveEvent(event)
            return

        # Show overlay if not visible
        if not self.zoom_overlay.isVisible():
            self.zoom_overlay.show()

        # Calculate position for overlay (to the right of cursor)
        global_pos = event.globalPos()
        overlay_pos = global_pos + QPoint(20, 20)

        self.zoom_overlay.move(overlay_pos)

        # Calculate crop from high_res_pixmap
        local_pos = event.pos()
        w = self.width()
        h = self.height()

        if w == 0 or h == 0: return

        nx = local_pos.x() / w
        ny = local_pos.y() / h

        # Map to high_res_pixmap coordinates
        pw = self.high_res_pixmap.width()
        ph = self.high_res_pixmap.height()

        center_x = int(nx * pw)
        center_y = int(ny * ph)

        crop_w = 300
        crop_h = 300

        x = center_x - crop_w // 2
        y = center_y - crop_h // 2

        # Clamp
        x = max(0, min(x, pw - crop_w))
        y = max(0, min(y, ph - crop_h))

        crop = self.high_res_pixmap.copy(x, y, crop_w, crop_h)
        self.zoom_overlay.update_content(crop)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.renderer().render(painter, self.rect().toRectF())
        painter.end()
