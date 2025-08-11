# D:\7FX Automation\robots\HFT explosive m1\monitoring_window.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QTabWidget, QLabel, 
                             QTextEdit, QSplitter, QDialog, QGroupBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import time

# --- [BARU] Widget Kustom untuk Menampilkan Status & Log per Pair ---
class PairMonitorTab(QWidget):
    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        status_panel = QGroupBox("Live Status")
        status_layout = QGridLayout(status_panel)
        
        # [UPGRADE] Tambahkan baris untuk Spread
        self.labels = {
            "price": (QLabel("Harga Terkini:"), QLabel("-")),
            "spread": (QLabel("Spread Saat Ini:"), QLabel("-")), # <-- BARIS BARU
            "condition": (QLabel("Kondisi Pasar:"), QLabel("-")),
            "trend": (QLabel("Info Tren:"), QLabel("-")),
            "volume": (QLabel("Info Volume:"), QLabel("-"))
        }
        
        for i, (label, value_label) in enumerate(self.labels.values()):
            status_layout.addWidget(label, i, 0)
            status_layout.addWidget(value_label, i, 1)
            status_layout.setColumnStretch(1, 2)
            
        splitter.addWidget(status_panel)

        log_panel = QGroupBox("Log")
        log_layout = QVBoxLayout(log_panel)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        splitter.addWidget(log_panel)
        
        splitter.setSizes([180, 220]) # Sesuaikan ukuran

    def update_status(self, status_data: dict):
        """Memperbarui semua label di panel status."""
        self.labels["price"][1].setText(f"{status_data.get('price', 0):.5f}")
        self.labels["spread"][1].setText(status_data.get('spread_info', '-')) # <-- BARU
        
        condition_label = self.labels["condition"][1]
        condition_text = status_data.get('condition', '-')
        condition_label.setText(condition_text)
        
        if "bullish" in condition_text.lower(): condition_label.setStyleSheet("color: #2ecc71;")
        elif "bearish" in condition_text.lower(): condition_label.setStyleSheet("color: #e74c3c;")
        elif "spread" in condition_text.lower(): condition_label.setStyleSheet("color: orange;")
        else: condition_label.setStyleSheet("")

        self.labels["trend"][1].setText(status_data.get('trend_info', '-'))
        self.labels["volume"][1].setText(status_data.get('volume_info', '-'))

    def add_log(self, message: str):
        """Menambahkan pesan ke area log."""
        timestamp = time.strftime('%H:%M:%S')
        self.log_area.append(f"[{timestamp}] {message}")
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

# --- Jendela Utama Monitor ---
class MonitoringWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Monitoring & Logs")
        self.setGeometry(900, 200, 700, 600)
        
        self.pair_tabs = {} # Mapping: symbol -> PairMonitorTab

        layout = QVBoxLayout(self)
        self.main_tabs = QTabWidget()
        layout.addWidget(self.main_tabs)

    def update_pair_data(self, status_data: dict):
        """Menerima data status, membuat tab jika perlu, dan update isinya."""
        symbol = status_data.get('symbol')
        if not symbol: return

        if symbol not in self.pair_tabs:
            new_tab = PairMonitorTab()
            self.pair_tabs[symbol] = new_tab
            self.main_tabs.addTab(new_tab, symbol)
        
        self.pair_tabs[symbol].update_status(status_data)

    def add_log(self, symbol: str, message: str):
        """Meneruskan pesan log ke tab yang benar."""
        if symbol in self.pair_tabs:
            self.pair_tabs[symbol].add_log(message)

    def clear_all(self):
        """Mereset seluruh tab dan data."""
        self.main_tabs.clear()
        self.pair_tabs.clear()
        
    def closeEvent(self, event):
        """Sembunyikan jendela, jangan ditutup, agar bisa dibuka lagi."""
        self.hide()
        event.ignore()