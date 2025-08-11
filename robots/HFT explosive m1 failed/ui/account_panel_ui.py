import sys
import os
import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, 
                             QLabel, QPushButton, QTextEdit, QMessageBox, QGroupBox)
from PyQt6.QtCore import pyqtSignal

# Import qtawesome jika tersedia, jika tidak, abaikan
try:
    import qtawesome as qta
except ImportError:
    qta = None

class AccountPanelUI(QWidget):
    """Kelas murni untuk UI Panel Kontrol. Tidak ada logika backend."""
    # Sinyal yang dipancarkan saat tombol ditekan
    start_engine_requested = pyqtSignal()
    stop_engine_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, account_info: dict, parent=None):
        super().__init__(parent)
        self.account_info = account_info
        self.account_number = account_info.get('number')

        self.init_ui()

    def init_ui(self):
        """Membangun semua elemen visual jendela."""
        main_layout = QVBoxLayout(self)
        info_group = QGroupBox(f"Akun: {self.account_number}")
        info_layout = QGridLayout(info_group)
        info_layout.addWidget(QLabel("Server:"), 0, 0)
        info_layout.addWidget(QLabel(f"<b>{self.account_info.get('server')}</b>"), 0, 1)
        
        self.connection_status_label = QLabel("<b style='color:orange;'>Menghubungkan...</b>")
        info_layout.addWidget(QLabel("Status Koneksi:"), 1, 0)
        info_layout.addWidget(self.connection_status_label, 1, 1)
        main_layout.addWidget(info_group)
        
        control_group = QGroupBox("Kontrol Engine")
        control_layout = QGridLayout(control_group)
        
        icon_play = qta.icon('fa5s.play') if qta else None
        self.btn_toggle_engine = QPushButton(icon_play, " Start Engine")
        self.btn_toggle_engine.clicked.connect(self.on_toggle_engine_clicked)
        self.btn_toggle_engine.setEnabled(False)

        icon_cogs = qta.icon('fa5s.cogs') if qta else None
        self.btn_open_settings = QPushButton(icon_cogs, " Pengaturan Strategi")
        self.btn_open_settings.clicked.connect(self.settings_requested.emit)
        self.btn_open_settings.setEnabled(False)

        control_layout.addWidget(self.btn_toggle_engine, 0, 0)
        control_layout.addWidget(self.btn_open_settings, 0, 1)
        main_layout.addWidget(control_group)
        
        log_group = QGroupBox("Log Aktivitas")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        main_layout.addWidget(log_group)

    def on_toggle_engine_clicked(self):
        """Memancarkan sinyal yang sesuai berdasarkan status engine saat ini."""
        if "Stop" in self.btn_toggle_engine.text():
            self.stop_engine_requested.emit()
        else:
            self.start_engine_requested.emit()

    def set_connection_status(self, status: str, color: str):
        """Slot untuk mengubah label status koneksi."""
        self.connection_status_label.setText(f"<b style='color:{color};'>{status}</b>")

    def set_controls_enabled(self, is_enabled: bool):
        """Slot untuk mengaktifkan/menonaktifkan tombol kontrol."""
        self.btn_toggle_engine.setEnabled(is_enabled)
        self.btn_open_settings.setEnabled(is_enabled)

    def set_engine_running(self, is_running: bool):
        """Slot untuk mengubah tampilan tombol Start/Stop."""
        if is_running:
            icon = qta.icon('fa5s.stop') if qta else None
            self.btn_toggle_engine.setText(" Stop Engine")
            self.btn_toggle_engine.setIcon(icon)
        else:
            icon = qta.icon('fa5s.play') if qta else None
            self.btn_toggle_engine.setText(" Start Engine")
            self.btn_toggle_engine.setIcon(icon)

    def add_log(self, source: str, message: str):
        """Slot untuk menambahkan pesan ke area log."""
        timestamp = time.strftime('%H:%M:%S')
        self.log_area.append(f"[{timestamp}] [{source}] {message}")