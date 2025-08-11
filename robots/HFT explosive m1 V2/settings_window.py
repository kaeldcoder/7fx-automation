# D:\7FX Automation\robots\HFT explosive m1\settings_window.py

import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QTabWidget, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QDoubleSpinBox, 
                             QSpinBox, QMessageBox, QCompleter, QDialog)
from PyQt6.QtCore import Qt
import qtawesome as qta
import MetaTrader5 as mt5

# --- Widget Kustom untuk Pengaturan per Pair ---
class StrategyTab(QWidget):
    def __init__(self, available_symbols: list, initial_magic: int):
        super().__init__()
        layout = QGridLayout(self)
        layout.setColumnStretch(1, 2)
        
        self.widgets = {
            "symbol": (QLabel("Simbol:"), QComboBox()),
            "timeframe": (QLabel("Timeframe:"), QComboBox()),
            "ema_period": (QLabel("EMA Period:"), QSpinBox()),
            "risk_per_trade": (QLabel("Risk/Trade (%):"), QDoubleSpinBox()),
            "rr_ratio": (QLabel("Risk:Reward Ratio:"), QDoubleSpinBox()),
            "sl_lookback": (QLabel("SL Lookback Period:"), QSpinBox()),
            "spread_tolerance": (QLabel("Toleransi Spread (x Avg):"), QDoubleSpinBox()),
            "magic_number": (QLabel("Magic Number:"), QLineEdit(str(initial_magic)))
        }

        # Konfigurasi Detail Widget
        self.widgets["symbol"][1].setEditable(True); self.widgets["symbol"][1].addItems(available_symbols)
        completer = QCompleter(available_symbols); self.widgets["symbol"][1].setCompleter(completer)
        completer.setFilterMode(Qt.MatchFlag.MatchContains); completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        self.timeframe_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
        self.widgets["timeframe"][1].addItems(self.timeframe_map.keys()); self.widgets["timeframe"][1].setCurrentText("M1")

        self.widgets["ema_period"][1].setRange(10, 200); self.widgets["ema_period"][1].setValue(50)
        self.widgets["risk_per_trade"][1].setRange(0.1, 5.0); self.widgets["risk_per_trade"][1].setSingleStep(0.1); self.widgets["risk_per_trade"][1].setValue(1.0)
        self.widgets["rr_ratio"][1].setRange(0.5, 10.0); self.widgets["rr_ratio"][1].setSingleStep(0.1); self.widgets["rr_ratio"][1].setValue(1.5)
        self.widgets["sl_lookback"][1].setRange(1, 10); self.widgets["sl_lookback"][1].setValue(3)
        self.widgets["spread_tolerance"][1].setRange(1.0, 5.0); self.widgets["spread_tolerance"][1].setSingleStep(0.1); self.widgets["spread_tolerance"][1].setValue(1.5)
        self.widgets["spread_tolerance"][1].setToolTip("Bot akan trade jika spread saat ini < (Rata-rata spread x nilai ini).")

        for i, (label, widget) in enumerate(self.widgets.values()):
            layout.addWidget(label, i, 0); layout.addWidget(widget, i, 1)

    def get_config(self) -> dict:
        """[PERBAIKAN] Menyimpan data dengan format yang konsisten."""
        config_data = {}
        for key, (_, widget) in self.widgets.items():
            if isinstance(widget, QComboBox):
                config_data[key] = widget.currentText() # Simpan teksnya, misal "M1"
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                config_data[key] = widget.value()
            elif isinstance(widget, QLineEdit):
                config_data[key] = widget.text()

        # Tambahkan data integer MT5 secara terpisah untuk digunakan oleh worker
        config_data['timeframe_int'] = self.timeframe_map[config_data['timeframe']]
        try:
            config_data['magic_number'] = int(config_data['magic_number'])
        except (ValueError, TypeError):
            config_data['magic_number'] = 0
            
        return config_data

    def set_config(self, config: dict):
        """[PERBAIKAN] Memuat data dengan tipe yang benar untuk setiap widget."""
        self.widgets["symbol"][1].setCurrentText(config.get("symbol", ""))
        self.widgets["timeframe"][1].setCurrentText(config.get("timeframe", "M1"))
        self.widgets["ema_period"][1].setValue(config.get("ema_period", 50))
        self.widgets["risk_per_trade"][1].setValue(config.get("risk_per_trade", 1.0))
        self.widgets["rr_ratio"][1].setValue(config.get("rr_ratio", 1.5))
        self.widgets["sl_lookback"][1].setValue(config.get("sl_lookback", 3))
        self.widgets["spread_tolerance"][1].setValue(config.get("spread_tolerance", 1.5))
        self.widgets["magic_number"][1].setText(str(config.get("magic_number", "")))

# --- Jendela Utama Pengaturan Strategi ---
class SettingsWindow(QDialog):
    def __init__(self, available_symbols: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pengaturan Strategi Multi-Pair")
        self.setWindowIcon(qta.icon('fa5s.cogs', color='white'))
        self.setGeometry(250, 250, 450, 400)
        self.config_file_path = os.path.join(os.path.dirname(__file__), "strategy_settings.json")
        self.available_symbols = available_symbols
        self.base_magic_number = 12345

        layout = QVBoxLayout(self)
        self.strategy_tabs = QTabWidget()
        self.strategy_tabs.setTabsClosable(True)
        self.strategy_tabs.tabCloseRequested.connect(self.remove_strategy_tab)
        layout.addWidget(self.strategy_tabs)
        
        self.btn_add_pair = QPushButton(qta.icon('fa5s.plus'), " Add Pair")
        self.btn_add_pair.clicked.connect(self.add_strategy_tab)
        self.strategy_tabs.setCornerWidget(self.btn_add_pair, Qt.Corner.TopLeftCorner)
        
        if not self.available_symbols:
            self.btn_add_pair.setEnabled(False)
            info_label = QLabel("Harap hubungkan ke akun MT5 di jendela utama untuk memuat daftar simbol.")
            info_label.setWordWrap(True); info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(info_label)
        else:
            self.load_configs() # Muat konfigurasi terakhir

    def add_strategy_tab(self, config: dict = None):
        new_magic = self.base_magic_number + self.strategy_tabs.count()
        new_tab = StrategyTab(self.available_symbols, new_magic)
        if config:
            new_tab.set_config(config)
        index = self.strategy_tabs.addTab(new_tab, f"Pair {self.strategy_tabs.count() + 1}")
        self.strategy_tabs.setCurrentIndex(index)

    def remove_strategy_tab(self, index: int):
        if self.strategy_tabs.count() > 1:
            self.strategy_tabs.removeTab(index)
        else:
            QMessageBox.warning(self, "Aksi Ditolak", "Setidaknya harus ada satu tab strategi.")
            
    def get_all_configs(self) -> list:
        all_configs = []
        for i in range(self.strategy_tabs.count()):
            config = self.strategy_tabs.widget(i).get_config()
            if not config['symbol']:
                QMessageBox.warning(self, "Input Error", f"Harap pilih simbol di Tab Pair {i+1}."); return []
            all_configs.append(config)
        return all_configs
        
    def save_configs(self):
        configs = self.get_all_configs()
        if configs: # Hanya simpan jika valid
            with open(self.config_file_path, "w") as f:
                json.dump(configs, f, indent=4)

    def load_configs(self):
        if not os.path.exists(self.config_file_path):
            self.add_strategy_tab() # Tambahkan satu tab default jika tidak ada file
            return
        try:
            with open(self.config_file_path, "r") as f:
                configs = json.load(f)
                for config in configs:
                    self.add_strategy_tab(config=config)
        except (json.JSONDecodeError, FileNotFoundError):
            self.add_strategy_tab() # Tambahkan default jika file rusak

    def closeEvent(self, event):
        self.save_configs()
        super().closeEvent(event)