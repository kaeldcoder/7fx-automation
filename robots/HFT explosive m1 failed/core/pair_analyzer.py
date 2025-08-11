# core/pair_analyzer.py

import time
import sys
import os
import importlib
import re
from PyQt6.QtCore import QObject, pyqtSignal

# Menentukan path root proyek agar import dari Library berjalan
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from Library.data_handler.data_handler import get_rates
from Library.utils.market_analyzer import SpreadAnalyzer
import MetaTrader5 as mt5

# Definisikan konstanta untuk setiap state agar kode mudah dibaca
STATE_IDLE = 0
STATE_FETCHING_DATA = 1
STATE_ANALYZING = 2

def camel_to_snake(name):
    """Mengubah NamaKelas (CamelCase) menjadi nama_kelas (snake_case) untuk nama file."""
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

class PairAnalyzer(QObject):
    finished = pyqtSignal()
    trade_signal_found = pyqtSignal(dict)
    status_update = pyqtSignal(dict)
    log_message = pyqtSignal(str, str, str) # symbol, message, level

    def __init__(self, symbol, config):
        super().__init__()
        self.is_running = True
        self.symbol = symbol
        self.config = config
        
        self.current_state = STATE_IDLE
        self.last_analysis_time = 0
        self.analysis_interval = 2 # Detik, seberapa sering melakukan analisis
        self.dataframe = None
        self.strategy_instance = None
        self._load_strategy()

    def _load_strategy(self):
        """Memuat instance kelas strategi berdasarkan konfigurasi."""
        try:
            class_name = self.config.get('strategy_class')
            if not class_name:
                self.log_message.emit(self.symbol, "Error: Tidak ada 'strategy_class' di konfigurasi.", "ERROR")
                return

            module_name = camel_to_snake(class_name)
            module = importlib.import_module(f"Library.strategies.{module_name}")
            StrategyClass = getattr(module, class_name)
            
            # Buat analyzer spread khusus untuk pair ini
            analyzer = SpreadAnalyzer(tolerance_multiplier=self.config.get('spread_tolerance', 1.5))
            
            # Buat instance strategi
            self.strategy_instance = StrategyClass(mt5, self.config, analyzer)
            self.log_message.emit(self.symbol, f"Strategi '{StrategyClass.strategy_name}' berhasil dimuat.", "INFO")

        except Exception as e:
            self.log_message.emit(self.symbol, f"Gagal memuat strategi: {e}", "ERROR")
            self.strategy_instance = None

    def stop(self):
        """Metode untuk memberi sinyal agar thread berhenti."""
        self.log_message.emit(self.symbol, "Menerima sinyal stop...", "INFO")
        self.is_running = False

    def run(self):
        """Loop utama State Machine yang akan dijalankan di dalam QThread."""
        if not self.strategy_instance:
            self.log_message.emit(self.symbol, "Tidak ada strategi, worker berhenti.", "ERROR")
            self.finished.emit()
            return

        while self.is_running:
            # === STATE 0: IDLE / ISTIRAHAT ===
            if self.current_state == STATE_IDLE:
                if time.time() - self.last_analysis_time > self.analysis_interval:
                    self.current_state = STATE_ANALYZING # Langsung ke analisis
                else:
                    time.sleep(0.5) # Cek setiap setengah detik

            # === STATE 2: MENGANALISIS & CEK SINYAL ===
            elif self.current_state == STATE_ANALYZING:
                try:
                    # Panggil metode check_signal dari instance strategi
                    market_status = self.strategy_instance.check_signal()
                    
                    if market_status:
                        # Kirim status live ke UI Monitoring
                        self.status_update.emit(market_status)
                        
                        # Cek apakah ada sinyal trading
                        trade_signal = market_status.get("trade_signal")
                        if trade_signal:
                            # Tambahkan info penting lain sebelum dikirim
                            trade_signal['symbol'] = self.symbol
                            trade_signal['magic_number'] = self.config.get('magic_number')
                            trade_signal['risk_per_trade'] = self.config.get('risk_per_trade')
                            self.trade_signal_found.emit(trade_signal)
                
                except Exception as e:
                    self.log_message.emit(self.symbol, f"Error saat analisis: {e}", "ERROR")
                
                # Setelah analisis selesai, kembali ke mode istirahat
                self.current_state = STATE_IDLE
                self.last_analysis_time = time.time()
        
        # Loop berhenti, kirim sinyal 'finished'
        self.log_message.emit(self.symbol, "Worker telah berhenti.", "INFO")
        self.finished.emit()