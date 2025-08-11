# D:\7FX Automation\robots\HFT explosive m1\monitoring_window.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QTabWidget, QLabel, 
                             QTextEdit, QSplitter, QDialog, QGroupBox, QHBoxLayout, QFrame)
from PyQt6.QtCore import Qt
import time

from custom_dialogs import StyledDialog

# --- [BARU] Widget Kustom untuk Menampilkan Status & Log per Pair ---
class PairMonitorTab(QWidget):
    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        splitter = QSplitter(Qt.Orientation.Vertical)

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0,0,0,0)

        strategy_layout = QHBoxLayout()
        strategy_layout.setSpacing(0) # Hapus spasi agar garis pemisah menempel

        # --- Kotak Entry Strategy ---
        entry_frame = QFrame()
        entry_frame.setObjectName("StrategyContainer")
        self.entry_layout = QVBoxLayout(entry_frame) # [DIUBAH] Gunakan QVBoxLayout
        self.entry_group = QGroupBox(self.tr("Entry Strategy Info"))
        self.entry_group.setStyleSheet("border: none; margin-top: 0px; padding-top: 0px;")
        self.entry_layout.addWidget(self.entry_group)
        
        # [DIUBAH] Konten strategi akan dibuat secara dinamis
        self.entry_content_layout = QVBoxLayout()
        self.entry_layout.addLayout(self.entry_content_layout)
        self.entry_layout.addStretch() # Tambah stretch agar konten merapat ke atas

        # [BARU] Garis Pemisah Vertikal
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setObjectName("VSeparator")

        # --- Kotak Exit Strategy ---
        exit_frame = QFrame()
        exit_frame.setObjectName("StrategyContainer")
        self.exit_layout = QVBoxLayout(exit_frame) # [DIUBAH] Gunakan QVBoxLayout
        self.exit_group = QGroupBox(self.tr("Exit Strategy Info"))
        self.exit_group.setStyleSheet("border: none; margin-top: 0px; padding-top: 0px;")
        self.exit_layout.addWidget(self.exit_group)
        
        # [DIUBAH] Konten strategi akan dibuat secara dinamis
        self.exit_content_layout = QVBoxLayout()
        self.exit_layout.addLayout(self.exit_content_layout)
        self.exit_layout.addStretch()

        # Masukkan semua ke layout
        strategy_layout.addWidget(entry_frame)
        strategy_layout.addWidget(separator) # Tambahkan garis pemisah
        strategy_layout.addWidget(exit_frame)

        self.status_labels = {}
        top_layout.addLayout(strategy_layout)
        
        log_panel = QGroupBox(self.tr("Log"))
        log_panel.setObjectName("LogGroup")
        log_layout = QVBoxLayout(log_panel)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        
        splitter.addWidget(top_container)
        splitter.addWidget(log_panel)
        splitter.setSizes([220, 380])
        main_layout.addWidget(splitter)

    def update_status(self, status_data: dict):
        all_labels_def = {
            'price': self.tr("Current Price:"),
            'spread_info': self.tr("Current Spread:")
        }
        all_labels_def.update(status_data.get('entry_labels', {}))
        all_labels_def.update(status_data.get('exit_labels', {}))

        if set(all_labels_def.keys()) != set(self.status_labels.keys()):
            self._rebuild_status_ui(status_data)

        for key, value_label in self.status_labels.items():
            value = status_data.get(key, "-")
            
            if key == 'price' and isinstance(value, (float, int)):
                value_label.setText(f"<b>{value:.5f}</b>")
            else:
                value_label.setText(str(value))
            
            if key == 'condition':
                text_lower = str(value).lower()
                if "bullish" in text_lower or "buy" in text_lower: value_label.setStyleSheet("color: #2ECC71; font-weight: bold;")
                elif "bearish" in text_lower or "sell" in text_lower: value_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
                elif "spread" in text_lower or "ranging" in text_lower: value_label.setStyleSheet("color: #F39C12;")
                else: value_label.setStyleSheet("")

    def _rebuild_status_ui(self, status_data: dict):
        for layout in [self.entry_content_layout, self.exit_content_layout]:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None: widget.deleteLater()
        self.status_labels.clear()
        
        # Atur Judul
        entry_name = status_data.get('entry_strategy_name', '-')
        self.entry_group.setTitle(self.tr("Entry: {0}").format(entry_name))
        exit_name = status_data.get('exit_strategy_name')
        if exit_name:
            self.exit_group.setTitle(self.tr("Exit: {0}").format(exit_name))
            self.exit_group.setVisible(True)
        else: self.exit_group.setVisible(False)

        # Isi konten Entry
        entry_labels_def = status_data.get('entry_labels', {})
        entry_labels_def['price'] = self.tr("Current Price:")
        entry_labels_def['spread_info'] = self.tr("Current Spread:")
        for key, display_text in entry_labels_def.items():
            value_label = QLabel("-")
            # [BARU] Buat layout horizontal untuk setiap baris (Label: Value)
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(display_text))
            row_layout.addStretch()
            row_layout.addWidget(value_label)
            self.entry_content_layout.addLayout(row_layout)
            self.status_labels[key] = value_label
            
        # Isi konten Exit
        exit_labels_def = status_data.get('exit_labels', {})
        if exit_labels_def:
            self.exit_group.setVisible(True)
            for key, display_text in exit_labels_def.items():
                value_label = QLabel("-")
                row_layout = QHBoxLayout()
                row_layout.addWidget(QLabel(display_text))
                row_layout.addStretch()
                row_layout.addWidget(value_label)
                self.exit_content_layout.addLayout(row_layout)
                self.status_labels[key] = value_label
        else: self.exit_group.setVisible(False)

    def add_log(self, message: str, level: str):
        timestamp = f"[{time.strftime('%H:%M:%S')}]"
        if level == "SUCCESS": color = "#2ECC71"
        elif level == "ERROR": color = "#E74C3C"
        elif level == "WARNING": color = "#F39C12"
        else: color = "#FFFFFF"
        formatted_message = f'<p style="color:{color}; margin: 0;">{timestamp} {message}</p>'
        self.log_area.append(formatted_message)
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

# --- Jendela Utama Monitor ---
class MonitoringWindow(StyledDialog):
    def __init__(self, parent=None):
        super().__init__(title="Live Monitoring & Logs", parent=parent)
        self.setMinimumSize(700, 600)
        
        self.pair_tabs = {}

        self.main_tabs = QTabWidget()
        self.content_layout.addWidget(self.main_tabs)
        self.content_layout.setContentsMargins(5, 5, 5, 5)

    def update_pair_data(self, status_data: dict):
        symbol = status_data.get('symbol')
        if not symbol: return

        if symbol not in self.pair_tabs:
            new_tab = PairMonitorTab()
            self.pair_tabs[symbol] = new_tab
            self.main_tabs.addTab(new_tab, symbol)
        
        self.pair_tabs[symbol].update_status(status_data)

    def add_log(self, symbol: str, message: str, level: str):
        if symbol in self.pair_tabs:
            self.pair_tabs[symbol].add_log(message, level)

    def clear_all(self):
        self.main_tabs.clear()
        self.pair_tabs.clear()
        
    def closeEvent(self, event):
        """Sembunyikan jendela, jangan ditutup, agar bisa dibuka lagi."""
        self.hide()
        event.ignore()