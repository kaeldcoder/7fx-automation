# custom_dialogs.py

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QDialogButtonBox, QProgressBar
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QProgressDialog
import qtawesome as qta

class StyledDialog(QDialog):
    """Template dasar untuk semua dialog kustom yang frameless dan bisa di-drag."""
    def __init__(self, title="Dialog", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("StyledDialog")

        self.dragPos = QPoint()
        self._is_dragging = False

        # --- Widget Utama & Layout ---
        self.main_widget = QFrame()
        self.main_widget.setObjectName("DialogMainWidget")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(self.main_widget)

        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Header ---
        self.header = QFrame()
        self.header.setObjectName("DialogHeader")
        self.header.setFixedHeight(40)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(25, 0, 5, 0)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("DialogHeaderTitle")

        btn_close = QPushButton(qta.icon('fa5s.times', color='#6a6e79'), "")
        btn_close.setObjectName("DialogControlButton")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(self.close)

        header_layout.addStretch()
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(btn_close) # Tambahkan tombol ke layout

        main_layout.addWidget(self.header)

        # --- Area Konten (untuk diisi oleh subclass) ---
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(15, 10, 15, 15)
        main_layout.addLayout(self.content_layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.header.underMouse():
            # Cek jika klik di atas tombol close, jangan di-drag
            widget_under_cursor = self.childAt(event.pos())
            if widget_under_cursor and widget_under_cursor.objectName() == "DialogControlButton":
                return

            self._is_dragging = True
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False

class ConfirmationDialog(StyledDialog):
    """Dialog konfirmasi kustom yang menggantikan QMessageBox."""
    def __init__(self, title, message, parent=None):
        super().__init__(title, parent)
        self.setMinimumWidth(300)
        self.setMinimumHeight(200)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.content_layout.addWidget(self.message_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Beri gaya pada tombol Yes/No
        btn_yes = button_box.button(QDialogButtonBox.StandardButton.Yes)
        btn_yes.setObjectName("DialogButton")
        btn_yes.setProperty("class", "affirmative")
        btn_no = button_box.button(QDialogButtonBox.StandardButton.No)
        btn_no.setObjectName("DialogButton")

        self.content_layout.addWidget(button_box)

class InfoDialog(StyledDialog):
    """Dialog informasi kustom yang menggantikan QMessageBox.information."""
    def __init__(self, title, message, parent=None):
        super().__init__(title, parent)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.message_label)

        self.content_layout.addSpacing(15)

        # Hanya tombol OK
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)

        btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setObjectName("DialogButton")
        btn_ok.setProperty("class", "affirmative") # Beri gaya tombol utama
        btn_ok.setMinimumWidth(120)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        button_layout.addStretch()
        self.content_layout.addLayout(button_layout)

class CustomProgressDialog(StyledDialog):
    """Dialog progres kustom yang menggantikan QProgressDialog."""
    def __init__(self, title, cancel_text, parent=None):
        super().__init__(title, parent)
        self.setMinimumWidth(450)

        # --- [PERBAIKAN] Atur jarak antar elemen ---
        self.content_layout.setSpacing(15)

        self.lbl_status = QLabel("Initializing...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True) # Agar teks panjang tidak terpotong

        self.progress_bar = QProgressBar()
        # --- [PERBAIKAN] Aktifkan animasi "busy" ---
        self.progress_bar.setRange(0, 0)

        self.btn_cancel = QPushButton(cancel_text)
        self.btn_cancel.setObjectName("DialogButton")

        # Tambahkan widget ke layout konten
        self.content_layout.addWidget(self.lbl_status)
        self.content_layout.addWidget(self.progress_bar)

        # Layout terpisah untuk menempatkan tombol di kanan
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        self.content_layout.addLayout(button_layout)

    def setLabelText(self, text):
        self.lbl_status.setText(text)

    def closeEvent(self, event):
        # Pastikan tombol cancel ditekan jika jendela ditutup paksa
        self.btn_cancel.click()
        super().closeEvent(event)

class MessageDialog(StyledDialog):
    """Dialog pesan kustom untuk menggantikan QMessageBox.information/critical."""
    def __init__(self, title, message, parent=None):
        super().__init__(title, parent)
        self.setMinimumWidth(350)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.message_label)
        self.content_layout.addSpacing(15)

        # Hanya tombol OK
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)

        btn_ok = button_box.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setObjectName("DialogButton")
        btn_ok.setProperty("class", "affirmative")

        # Layout untuk menengahkan tombol
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        button_layout.addStretch()
        self.content_layout.addLayout(button_layout)

class RetryConnectionDialog(StyledDialog):
    """Dialog untuk menampilkan error koneksi dan opsi retry/cancel."""
    def __init__(self, title, message, parent=None):
        super().__init__(title, parent)
        self.setMinimumWidth(400)
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.message_label)
        self.content_layout.addSpacing(15)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        btn_retry = button_box.button(QDialogButtonBox.StandardButton.Yes)
        btn_retry.setText("Retry")
        btn_retry.setObjectName("DialogButton")
        btn_retry.setProperty("class", "affirmative")
        btn_cancel = button_box.button(QDialogButtonBox.StandardButton.No)
        btn_cancel.setText("Cancel")
        btn_cancel.setObjectName("DialogButton")
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        button_layout.addStretch()
        self.content_layout.addLayout(button_layout)