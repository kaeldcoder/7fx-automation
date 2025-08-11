# D:\7FX Automation\robots\HFT explosive m1\monitoring_window.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QTabWidget, QLabel, 
                             QTextEdit, QSplitter, QDialog, QGroupBox, QHBoxLayout)
from PyQt6.QtCore import Qt
import time

# --- [BARU] Widget Kustom untuk Menampilkan Status & Log per Pair ---
class PairMonitorTab(QWidget):
    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        status_panel = QGroupBox("Live Status")
        # [DIUBAH] Layout utama status sekarang horizontal untuk 2 kolom
        self.status_layout = QHBoxLayout(status_panel)
        splitter.addWidget(status_panel)
        
        # Buat kolom kiri dan kanan
        self.entry_group = QGroupBox("Info Strategi Entri")
        self.exit_group = QGroupBox("Info Strategi Exit")
        self.entry_layout = QGridLayout(self.entry_group)
        self.exit_layout = QGridLayout(self.exit_group)
        self.entry_layout.setColumnStretch(1, 1)
        self.exit_layout.setColumnStretch(1, 1)

        self.status_layout.addWidget(self.entry_group)
        self.status_layout.addWidget(self.exit_group)
        
        # Dictionary untuk menyimpan label dinamis
        self.status_labels = {}
        log_panel = QGroupBox("Log")
        log_layout = QVBoxLayout(log_panel)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        splitter.addWidget(log_panel)
        
        splitter.setSizes([220, 380])

    def update_status(self, status_data: dict):
        """[VERSI BARU] Membangun atau memperbarui UI status secara dinamis."""
        all_labels_def = {
            'price': "Harga Terkini:",
            'spread_info': "Spread Saat Ini:"
        }
        all_labels_def.update(status_data.get('entry_labels', {}))
        all_labels_def.update(status_data.get('exit_labels', {}))

        if set(all_labels_def.keys()) != set(self.status_labels.keys()):
            self._rebuild_status_ui(status_data)

        for key, value_label in self.status_labels.items():
            value = status_data.get(key, "-")
            
            # [PERBAIKAN] Pemformatan dan pewarnaan tidak berubah
            if key == 'price' and isinstance(value, (float, int)):
                value_label.setText(f"<b>{value:.5f}</b>")
            else:
                value_label.setText(str(value))
            
            # Pewarnaan khusus untuk kondisi pasar
            if key == 'condition':
                text_lower = str(value).lower()
                if "bullish" in text_lower: value_label.setStyleSheet("color: #2ECC71; font-weight: bold;")
                elif "bearish" in text_lower: value_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
                elif "spread" in text_lower: value_label.setStyleSheet("color: #F39C12;")
                else: value_label.setStyleSheet("")

    def _rebuild_status_ui(self, status_data: dict):
        for layout in [self.entry_layout, self.exit_layout]:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self.status_labels.clear()
        
        entry_name = status_data.get('entry_strategy_name', '-')
        self.entry_group.setTitle(f"Info Strategi Entri: {entry_name}")

        exit_name = status_data.get('exit_strategy_name')
        if exit_name:
            self.exit_group.setTitle(f"Info Strategi Exit: {exit_name}")
            self.exit_group.setVisible(True)
        else:
            self.exit_group.setVisible(False)

        # --- Atur Kolom Kiri (Entri) ---
        entry_labels_def = status_data.get('entry_labels', {})
        entry_labels_def['price'] = "Harga Terkini:"
        entry_labels_def['spread_info'] = "Spread Saat Ini:"
        
        for row, (key, display_text) in enumerate(entry_labels_def.items()):
            label = QLabel(display_text)
            value_label = QLabel("-")
            self.entry_layout.addWidget(label, row, 0)
            self.entry_layout.addWidget(value_label, row, 1)
            self.status_labels[key] = value_label # [PERBAIKAN] Simpan value_label saja
            
        # --- Atur Kolom Kanan (Exit) ---
        exit_labels_def = status_data.get('exit_labels', {})
        if exit_labels_def:
            self.exit_group.setVisible(True)
            for row, (key, display_text) in enumerate(exit_labels_def.items()):
                label = QLabel(display_text)
                value_label = QLabel("-")
                self.exit_layout.addWidget(label, row, 0)
                self.exit_layout.addWidget(value_label, row, 1)
                self.status_labels[key] = value_label # [PERBAIKAN] Simpan value_label saja
        else:
            self.exit_group.setVisible(False)

    def add_log(self, message: str, level: str):
        """Menambahkan pesan ke area log dengan format berwarna."""
        timestamp = f"[{time.strftime('%H:%M:%S')}]"
        
        if level == "SUCCESS": color = "#2ECC71" # Hijau
        elif level == "ERROR": color = "#E74C3C" # Merah
        elif level == "WARNING": color = "#F39C12" # Oranye
        else: color = "#FFFFFF" # INFO / Default (Putih)

        formatted_message = f'<p style="color:{color}; margin: 0;">{timestamp} {message}</p>'
        
        self.log_area.append(formatted_message)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

# --- Jendela Utama Monitor ---
class MonitoringWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Monitoring & Logs")
        self.setGeometry(900, 200, 700, 600)
        
        self.pair_tabs = {}
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

    def add_log(self, symbol: str, message: str, level: str):
        """Meneruskan pesan log beserta levelnya ke tab yang benar."""
        if symbol in self.pair_tabs:
            # Panggil add_log di PairMonitorTab dengan semua argumen
            self.pair_tabs[symbol].add_log(message, level)

    def clear_all(self):
        """Mereset seluruh tab dan data."""
        self.main_tabs.clear()
        self.pair_tabs.clear()
        
    def closeEvent(self, event):
        """Sembunyikan jendela, jangan ditutup, agar bisa dibuka lagi."""
        self.hide()
        event.ignore()