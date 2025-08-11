# ui/login_window.py

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox
from PyQt6.QtCore import pyqtSignal

class LoginWindow(QDialog):
    # Sinyal ini tidak lagi digunakan secara langsung, tapi bisa dipertahankan
    login_successful = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setFixedSize(300, 150)

        layout = QVBoxLayout(self)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.login_button = QPushButton("Login")

        layout.addWidget(QLabel("Silakan login untuk melanjutkan:"))
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)

        self.login_button.clicked.connect(self.handle_login_attempt)
        # Hubungkan enter di field password ke tombol login
        self.password_input.returnPressed.connect(self.login_button.click)

    def handle_login_attempt(self):
        # Untuk sekarang, kita buat login sederhana
        # TODO: Ganti dengan logika verifikasi user Anda yang sebenarnya
        if self.username_input.text() == "admin" and self.password_input.text() == "220713":
            self.handle_login_success()
        else:
            QMessageBox.warning(self, "Login Gagal", "Username atau password salah.")

    def handle_login_success(self):
        """
        [PERUBAHAN] Jika login berhasil, kita tidak lagi membuka jendela baru.
        Kita cukup menerima (accept) dialog ini, yang akan memberi tahu 'main.py'
        bahwa login berhasil.
        """
        print("Verifikasi login berhasil.")
        self.accept() # Menutup dialog dan mengembalikan status 'Accepted'