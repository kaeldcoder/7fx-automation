import sys
import os
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QMessageBox, QGridLayout,
                             QSpacerItem, QSizePolicy, QFrame)
from PyQt6.QtCore import pyqtSignal, Qt, QPoint, QTimer, QPropertyAnimation, pyqtProperty
from PyQt6.QtWidgets import QDialog, QProgressBar, QStackedLayout
from PyQt6.QtGui import QFont, QIcon, QColor, QPixmap
import qtawesome as qta

class LoginWindow(QWidget):
    # Sinyal yang akan dikirim saat login berhasil
    login_successful = pyqtSignal()
    window_is_ready = pyqtSignal()

    def __init__(self):
        super().__init__()
        
        self.setWindowTitle(self.tr("7FX Automation - Login"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 450)
        self.setObjectName("LoginWindow")

        self.dragPos = QPoint()

        # WIDGET DASAR untuk menampung semua elemen & styling sudut tumpul
        self.main_widget = QWidget()
        self.main_widget.setObjectName("MainWidget")
        outer_layout = QVBoxLayout(self.main_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 1. Header Kustom untuk drag dan tombol kontrol
        header_container = self.create_header()
        outer_layout.addWidget(header_container)

        # 2. Layout Konten Utama (Ikon, Input, Tombol)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(40, 20, 40, 30)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Ikon Robot
        icon_path = os.path.join('assets', '7fx_logo.png') # <-- GANTI NAMA FILE JIKA PERLU
        icon_label = QLabel()

        if os.path.exists(icon_path):
            # Jika gambar kustom ditemukan, gunakan gambar tersebut
            brand_pixmap = QPixmap(icon_path)
            icon_label.setPixmap(brand_pixmap.scaled(
                120, 120, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            # Jika tidak ditemukan, gunakan ikon qtawesome sebagai fallback
            icon_label.setPixmap(qta.icon('fa5s.robot', color='#01c38e').pixmap(80, 80))

        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addSpacing(10)

        # Garis Aksen
        accent_line = QFrame()
        accent_line.setObjectName("AccentFrame")
        accent_line.setFixedHeight(2)
        content_layout.addWidget(accent_line)
        content_layout.addSpacing(30)

        # Input field dengan ikon
        self.user_input = QLineEdit(placeholderText=self.tr("Username"))
        self.password_input = QLineEdit(placeholderText=self.tr("Master Password"), echoMode=QLineEdit.EchoMode.Password)
        content_layout.addWidget(self.create_icon_input_field(
            qta.icon('fa5s.user', color='#6a6e79'), self.user_input
        ))
        content_layout.addSpacing(15)
        content_layout.addWidget(self.create_icon_input_field(
            qta.icon('fa5s.lock', color='#6a6e79'), self.password_input
        ))
        content_layout.addSpacing(30)

        # Tombol Login
        self.login_button = QPushButton(self.tr("LOGIN"))
        self.login_button.setObjectName("LoginButton")
        self.login_button.setMinimumHeight(45)
        content_layout.addWidget(self.login_button)
        
        outer_layout.addLayout(content_layout)
        outer_layout.addStretch()

        # 3. Footer
        footer_container = self.create_footer()
        outer_layout.addWidget(footer_container)

        # Atur layout utama dari QWidget
        final_layout = QVBoxLayout(self)
        final_layout.setContentsMargins(0,0,0,0)
        final_layout.addWidget(self.main_widget)
        
        # Hubungkan sinyal
        self.login_button.clicked.connect(self.check_login)
        self.password_input.returnPressed.connect(self.check_login)

        self.apply_stylesheet()

    def create_header(self):
        """Helper untuk membuat widget header."""
        header_container = QWidget()
        header_container.setObjectName("HeaderContainer")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 0, 5, 0)
        
        btn_minimize = QPushButton(qta.icon('fa5s.minus', color='#6a6e79'), "")
        btn_close = QPushButton(qta.icon('fa5s.times', color='#6a6e79'), "")
        
        for btn in [btn_minimize, btn_close]:
            btn.setObjectName("ControlButton")
            btn.setFixedSize(30, 30)
        
        btn_minimize.clicked.connect(self.showMinimized)
        btn_close.clicked.connect(self.close)

        header_layout.addStretch()
        header_layout.addWidget(btn_minimize)
        header_layout.addWidget(btn_close)
        return header_container

    def create_icon_input_field(self, icon, line_edit):
        """Helper untuk membuat widget input dengan ikon di sebelah kiri."""
        container = QFrame()
        container.setObjectName("InputFieldContainer")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(10)
        
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(16, 16))
        
        layout.addWidget(icon_label)
        layout.addWidget(line_edit)
        return container

    def create_footer(self):
        """Helper untuk membuat widget footer."""
        footer_container = QWidget()
        footer_layout = QHBoxLayout(footer_container)
        footer_layout.setContentsMargins(40, 10, 40, 10)
        
        btn_help = QPushButton(self.tr("Need Help?"))
        btn_forgot_pass = QPushButton(self.tr("Forgot Password?"))
        
        for btn in [btn_help, btn_forgot_pass]:
            btn.setObjectName("FooterButton")
        
        footer_layout.addWidget(btn_help, alignment=Qt.AlignmentFlag.AlignLeft)
        footer_layout.addStretch()
        footer_layout.addWidget(btn_forgot_pass, alignment=Qt.AlignmentFlag.AlignRight)
        return footer_container
    
    def showEvent(self, event):
        """Override event yang dipanggil saat jendela akan ditampilkan."""
        # Panggil implementasi asli dari parent class terlebih dahulu
        super().showEvent(event)
        # Kirim sinyal bahwa UI sudah siap. Hanya akan berjalan sekali.
        self.window_is_ready.emit()

    def check_login(self):
        username = self.user_input.text()
        password = self.password_input.text()
        if username == "admin" and password == "220713":
            self.login_successful.emit()
        else:
            QMessageBox.warning(self, self.tr("Login Failed"), self.tr("Incorrect username or password."))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPos)
            event.accept()

    def apply_stylesheet(self):
        qss = """
            #MainWidget {
                background-color: #1a1e29;
                font-family: Segoe UI, Arial, sans-serif;
                border-radius: 10px;
            }
            #HeaderContainer { background-color: transparent; }
            #ControlButton {
                background-color: transparent; border: none; border-radius: 5px;
            }
            #ControlButton:hover { background-color: #6a6e79; }
            QPushButton#ControlButton[objectName*="btn_close"]:hover {
                 background-color: #e81123;
            }
            #AccentFrame { background-color: #01c38e; }

            /* Kontainer untuk Input Field */
            #InputFieldContainer {
                background-color: #132d46;
                border: 1px solid #6a6e79;
                border-radius: 5px;
            }
            #InputFieldContainer:focus-within {
                border: 1px solid #01c38e;
            }
            
            /* QLineEdit di dalam kontainer */
            QLineEdit {
                background-color: transparent;
                border: none;
                color: #ffffff;
                padding: 12px 0px;
                font-size: 15px;
            }
            QLineEdit::placeholder { color: #6a6e79; }

            /* Tombol Login Utama */
            #LoginButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 #01c38e, stop:1 #01a87a);
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            #LoginButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 #01e0a4, stop:1 #01c38e);
            }
            #LoginButton:pressed {
                background-color: #01a87a;
            }
            
            /* Tombol Teks di Footer */
            #FooterButton {
                color: #6a6e79;
                background-color: transparent;
                border: none;
                font-size: 12px;
            }
            #FooterButton:hover {
                color: #01c38e;
                text-decoration: underline;
            }
        """
        self.setStyleSheet(qss)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    sys.exit(app.exec())
