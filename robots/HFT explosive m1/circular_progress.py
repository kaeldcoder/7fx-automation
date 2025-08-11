# circular_progress.py

from PyQt6.QtCore import Qt, QPropertyAnimation, pyqtProperty, QEasingCurve
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

class CircularProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.progress_width = 10
        self.progress_color = QColor("#01c38e")
        self.max_value = 100
        self.font_family = "Oswald"
        self.font_size = 32
        self.suffix = "%"

        self.animation = QPropertyAnimation(self, b"value", self)
        self.animation.setDuration(1500) # Durasi animasi 1.5 detik
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_value(self, value):
        self.animation.stop()
        self.animation.setStartValue(self.value)
        self.animation.setEndValue(value)
        self.animation.start()

    def paintEvent(self, event):
        width = self.width() - self.progress_width
        height = self.height() - self.progress_width
        margin = self.progress_width / 2
        side = min(width, height)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Latar belakang lingkaran
        pen = QPen(QColor("#1A1E29"), self.progress_width) # Warna biru gelap
        painter.setPen(pen)
        painter.drawArc(int(margin), int(margin), int(side), int(side), 0, 360 * 16)

        # Progress bar
        pen.setColor(self.progress_color)
        painter.setPen(pen)
        span_angle = (self._value / self.max_value) * 360
        painter.drawArc(int(margin), int(margin), int(side), int(side), 90 * 16, int(-span_angle * 16))

        # Teks di tengah
        font = QFont(self.font_family, self.font_size)
        painter.setFont(font)
        pen.setColor(QColor("#FFFFFF"))
        painter.setPen(pen)
        text = f"{self._value}{self.suffix}"
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

    @pyqtProperty(int)
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val
        self.update()