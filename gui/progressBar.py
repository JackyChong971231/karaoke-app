from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QPainter, QColor

class ProgressBar(QWidget):
    clicked = Signal(float)  # emits fraction 0.0-1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0  # 0.0 - 1.0
        self.setMinimumHeight(10)

    def set_progress(self, fraction):
        self.progress = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Background
        painter.setBrush(QColor(80, 80, 80))
        painter.drawRect(self.rect())
        # Red progress
        width = int(self.progress * self.width())
        painter.setBrush(QColor(255, 0, 0))
        painter.drawRect(0, 0, width, self.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            fraction = event.position().x() / self.width()
            self.clicked.emit(fraction)
