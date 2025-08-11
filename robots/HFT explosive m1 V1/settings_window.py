import json
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QGroupBox, QTabWidget
)
from PyQt6.QtCore import Qt
import qtawesome as qta

class SymbolSettingsForm(QWidget):
    """Widget terpisah untuk form pengaturan per simbol."""
    def __init__(self, symbol, config, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.create_widgets()
        self.set_config(config)

    def create_widgets(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Grup Parameter Risiko & Umum ---
        risk_group = QGroupBox("Pengaturan Umum & Risiko")
        risk_layout = QGridLayout(risk_group)
        self.input_magic = QLineEdit()
        self.input_risk = QLineEdit()
        self.input_rrr = QLineEdit()
        risk_layout.addWidget(QLabel("Magic Number:"), 0, 0); risk_layout.addWidget(self.input_magic, 0, 1)
        risk_layout.addWidget(QLabel("Risk per Trade (%):"), 1, 0); risk_layout.addWidget(self.input_risk, 1, 1)
        risk_layout.addWidget(QLabel("Risk/Reward Ratio:"), 2, 0); risk_layout.addWidget(self.input_rrr, 2, 1)
        layout.addWidget(risk_group)

        # --- Grup Parameter EMA ---
        ema_group = QGroupBox("Parameter EMA (Multi-Timeframe)")
        ema_layout = QGridLayout(ema_group)
        self.input_ema_macro = QLineEdit()
        self.input_ema_fast = QLineEdit()
        self.input_ema_slow = QLineEdit()
        ema_layout.addWidget(QLabel("Periode EMA Makro (M15):"), 0, 0); ema_layout.addWidget(self.input_ema_macro, 0, 1)
        ema_layout.addWidget(QLabel("Periode EMA Cepat (M5):"), 1, 0); ema_layout.addWidget(self.input_ema_fast, 1, 1)
        ema_layout.addWidget(QLabel("Periode EMA Lambat (M5):"), 2, 0); ema_layout.addWidget(self.input_ema_slow, 2, 1)
        layout.addWidget(ema_group)

        # --- Grup Parameter RSI ---
        rsi_group = QGroupBox("Parameter RSI (Filter Momentum M5)")
        rsi_layout = QGridLayout(rsi_group)
        self.input_rsi_period = QLineEdit()
        self.input_rsi_mid = QLineEdit()
        rsi_layout.addWidget(QLabel("Periode RSI:"), 0, 0); rsi_layout.addWidget(self.input_rsi_period, 0, 1)
        rsi_layout.addWidget(QLabel("Level Tengah RSI:"), 1, 0); rsi_layout.addWidget(self.input_rsi_mid, 1, 1)
        layout.addWidget(rsi_group)

        # --- Grup Parameter ATR ---
        atr_group = QGroupBox("Parameter ATR (Volatilitas M5 & Stop Loss)")
        atr_layout = QGridLayout(atr_group)
        self.input_atr_period = QLineEdit()
        self.input_atr_sma_period = QLineEdit()
        self.input_sl_multiplier = QLineEdit()
        atr_layout.addWidget(QLabel("Periode ATR:"), 0, 0); atr_layout.addWidget(self.input_atr_period, 0, 1)
        atr_layout.addWidget(QLabel("Periode SMA dari ATR:"), 1, 0); atr_layout.addWidget(self.input_atr_sma_period, 1, 1)
        atr_layout.addWidget(QLabel("Kelipatan ATR untuk SL:"), 2, 0); atr_layout.addWidget(self.input_sl_multiplier, 2, 1)
        layout.addWidget(atr_group)

        layout.addStretch() # Mendorong semua grup ke atas

    def set_config(self, config):
        """Mengisi form dengan data dari dictionary config."""
        self.input_magic.setText(str(config.get("magic_number", "")))
        self.input_risk.setText(str(config.get("risk_per_trade", "1.0")))
        self.input_rrr.setText(str(config.get("risk_reward_ratio", "2.0")))
        self.input_ema_macro.setText(str(config.get("ema_macro_period", "50")))
        self.input_ema_fast.setText(str(config.get("ema_fast_period", "9")))
        self.input_ema_slow.setText(str(config.get("ema_slow_period", "21")))
        self.input_rsi_period.setText(str(config.get("rsi_period", "14")))
        self.input_rsi_mid.setText(str(config.get("rsi_mid_level", "50")))
        self.input_atr_period.setText(str(config.get("atr_period", "14")))
        self.input_atr_sma_period.setText(str(config.get("atr_sma_period", "20")))
        self.input_sl_multiplier.setText(str(config.get("sl_atr_multiplier", "1.5")))

    def get_config(self):
        """Mengambil data dari form dan mengembalikannya sebagai dictionary."""
        try:
            return {
                "symbol": self.symbol,
                "magic_number": int(self.input_magic.text()),
                "risk_per_trade": float(self.input_risk.text()),
                "risk_reward_ratio": float(self.input_rrr.text()),
                "ema_macro_period": int(self.input_ema_macro.text()),
                "ema_fast_period": int(self.input_ema_fast.text()),
                "ema_slow_period": int(self.input_ema_slow.text()),
                "rsi_period": int(self.input_rsi_period.text()),
                "rsi_mid_level": int(self.input_rsi_mid.text()),
                "atr_period": int(self.input_atr_period.text()),
                "atr_sma_period": int(self.input_atr_sma_period.text()),
                "sl_atr_multiplier": float(self.input_sl_multiplier.text())
            }
        except ValueError as e:
            QMessageBox.critical(self, "Input Error", f"Pastikan semua input adalah angka yang valid untuk simbol {self.symbol}.\nError: {e}")
            return None

class SettingsWindow(QMainWindow):
    def __init__(self, available_symbols, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pengaturan Strategi V3 - Multi Symbol Editor")
        self.setWindowIcon(qta.icon('fa5s.cogs', color='white'))
        self.setGeometry(300, 300, 850, 600)

        self.available_symbols = available_symbols
        self.config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'Config', 'strategy_configs_v2.json')
        self.configs = self.load_configs()

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        
        main_layout = QHBoxLayout(self.main_widget)

        # --- Panel Kiri (Daftar Simbol & Search) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(220)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Cari simbol...")
        self.search_bar.textChanged.connect(self.filter_symbol_list)
        
        self.pair_list_widget = QListWidget()
        self.pair_list_widget.itemDoubleClicked.connect(self.add_symbol_to_tabs)
        
        left_layout.addWidget(QLabel("Daftar Simbol (Double Click)"))
        left_layout.addWidget(self.search_bar)
        left_layout.addWidget(self.pair_list_widget)
        main_layout.addWidget(left_panel)

        # --- Panel Kanan (Tabbed View) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        # Tombol untuk menyimpan semua konfigurasi dari tab yang aktif
        self.btn_save_all = QPushButton(qta.icon('fa5s.save', color='blue'), " Simpan Semua Pengaturan")
        self.btn_save_all.clicked.connect(self.save_all_configs)
        
        right_layout.addWidget(self.tab_widget)
        right_layout.addWidget(self.btn_save_all)
        main_layout.addWidget(right_panel, stretch=1)

        self.populate_pair_list()
        self.load_initial_tabs()

    def filter_symbol_list(self, text):
        """Menyaring daftar simbol berdasarkan input di search bar."""
        for i in range(self.pair_list_widget.count()):
            item = self.pair_list_widget.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def populate_pair_list(self):
        """Mengisi daftar simbol di panel kiri."""
        self.pair_list_widget.clear()
        for symbol in sorted(self.available_symbols):
            self.pair_list_widget.addItem(QListWidgetItem(symbol))

    def load_initial_tabs(self):
        """Memuat tab untuk simbol yang sudah ada di file konfigurasi."""
        for symbol, config in self.configs.items():
            self.add_tab_for_symbol(symbol, config)

    def add_symbol_to_tabs(self, item):
        """Menambahkan simbol yang di-double-click ke tab jika belum ada."""
        symbol = item.text()
        # Cek apakah tab untuk simbol ini sudah ada
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == symbol:
                self.tab_widget.setCurrentIndex(i) # Pindah ke tab yang sudah ada
                return
        
        # Jika belum ada, buat tab baru
        config = self.configs.get(symbol, self.get_default_config(symbol))
        self.add_tab_for_symbol(symbol, config)

    def add_tab_for_symbol(self, symbol, config):
        """Fungsi inti untuk membuat dan menambahkan tab baru."""
        form_widget = SymbolSettingsForm(symbol, config)
        index = self.tab_widget.addTab(form_widget, symbol)
        self.tab_widget.setCurrentIndex(index)

    def close_tab(self, index):
        """Menutup tab dan menanyakan konfirmasi."""
        widget = self.tab_widget.widget(index)
        symbol = self.tab_widget.tabText(index)
        
        reply = QMessageBox.question(self, 'Konfirmasi Hapus', 
                                     f"Anda yakin ingin menghapus '{symbol}' dari daftar konfigurasi aktif?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Hapus dari self.configs jika ada
            if symbol in self.configs:
                del self.configs[symbol]
            self.tab_widget.removeTab(index)
            print(f"Konfigurasi untuk {symbol} dihapus dari sesi ini.")
            self.save_all_configs(show_message=False) # Simpan perubahan setelah hapus
            
    def save_all_configs(self, show_message=True):
        """Menyimpan konfigurasi dari semua tab yang terbuka."""
        new_configs = {}
        for i in range(self.tab_widget.count()):
            form_widget = self.tab_widget.widget(i)
            config = form_widget.get_config()
            if config:
                new_configs[config['symbol']] = config
            else:
                # Jika ada error validasi di salah satu form, hentikan proses penyimpanan
                return 

        self.configs = new_configs
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.configs, f, indent=4)
            if show_message:
                QMessageBox.information(self, "Sukses", f"Berhasil menyimpan {len(self.configs)} konfigurasi.")
        except Exception as e:
            QMessageBox.critical(self, "Error Menyimpan File", f"Gagal menyimpan konfigurasi: {e}")

    def get_all_configs(self):
        """Dipanggil oleh main_v1.py untuk mendapatkan daftar config yang akan dijalankan."""
        self.save_all_configs(show_message=False) # Pastikan data terakhir tersimpan
        return list(self.configs.values())
        
    def get_default_config(self, symbol):
        import hashlib
        magic = int(hashlib.sha1(symbol.encode()).hexdigest(), 16) % 100000 + 200000 
        return {
            "symbol": symbol, "magic_number": magic, "risk_per_trade": 1.0, "risk_reward_ratio": 2.0,
            "ema_macro_period": 50, "ema_fast_period": 9, "ema_slow_period": 21,
            "rsi_period": 14, "rsi_mid_level": 50, "atr_period": 14,
            "atr_sma_period": 20, "sl_atr_multiplier": 1.5
        }

    def load_configs(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return json.load(f)
        except Exception:
            return {}
        return {}

    def closeEvent(self, event):
        self.save_all_configs(show_message=False)
        event.accept()