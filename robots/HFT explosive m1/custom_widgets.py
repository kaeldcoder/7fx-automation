from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPalette

class AnimatedButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.animation = QPropertyAnimation(self, b"color")
        self.animation.setDuration(200) # Durasi animasi 200ms
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)

    def enterEvent(self, event):
        # Animasi ke warna hover
        self.animation.setEndValue(QColor("#132d46")) # Warna hover
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Animasi kembali ke warna transparan
        self.animation.setEndValue(QColor("transparent"))
        self.animation.start()
        super().leaveEvent(event)

    @pyqtProperty(QColor)
    def color(self):
        return self.palette().color(QPalette.ColorRole.Button)

    @color.setter
    def color(self, color):
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Button, color)
        self.setPalette(palette)
