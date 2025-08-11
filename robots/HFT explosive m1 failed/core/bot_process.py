import sys
import os
import keyring
import json
import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# --- Konfigurasi Path (Sama seperti sebelumnya) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT)
if PROJECT_ROOT not in sys.path: sys.path.append(PROJECT_ROOT)
if GRANDPARENT_ROOT not in sys.path: sys.path.append(GRANDPARENT_ROOT)

from services.broker_client import BrokerClient
from Library.broker_interface.mt5_connector import connect_to_mt5, shutdown_connection
from core.pair_analyzer import PairAnalyzer
from Library.risk_management.trade_manager import TradeManager
from Library.risk_management.position_sizer import calculate_lot_size
from Library.broker_interface.mt5_executor import place_pending_order
import MetaTrader5 as mt5

# KELAS LOGIKA: BotController, BotInitializer, dan ProcessHandler
# Semua kelas ini adalah QObject, bukan QWidget.

class BotInitializer(QObject):
    # ... (Kelas BotInitializer tetap sama persis seperti sebelumnya) ...
    initialization_success = pyqtSignal()
    initialization_failed = pyqtSignal(str)
    def __init__(self, account_info: dict):
        super().__init__()
        self.account_info = account_info
    def run(self):
        try:
            acc_num = self.account_info['number']
            password = keyring.get_password("7FX_HFT_Bot", acc_num)
            if not password: raise ValueError(f"Password untuk akun {acc_num} tidak ditemukan.")
            is_ok, msg = connect_to_mt5(acc_num, password, self.account_info['server'], self.account_info['path'])
            if not is_ok: raise ConnectionError(f"Gagal terhubung: {msg}")
            self.initialization_success.emit()
        except Exception as e:
            self.initialization_failed.emit(str(e))

class BotController(QObject):
    # ... (Kelas BotController tetap sama persis seperti sebelumnya) ...
    finished = pyqtSignal()
    log_message = pyqtSignal(str, str)
    def __init__(self, account_number: str, configs: dict, broker: BrokerClient):
        super().__init__()
        self.is_running = True; self.account_number = account_number; self.configs = configs
        self.tm_config = configs.get('tm_config', {}); self.strategy_configs = configs.get('strategy_configs', [])
        self.broker = broker; self.trade_manager = TradeManager(self.tm_config, mt5, None)
        self.pair_analyzer_threads = {}; self.pair_analyzers = {}
    def stop(self):
        self.log_message.emit("Controller", "Menerima sinyal stop..."); self.is_running = False
        for worker in self.pair_analyzers.values(): worker.stop()
        for thread in self.pair_analyzer_threads.values(): thread.quit(); thread.wait(3000)
    def run(self):
        self.log_message.emit("Controller", "Bot Controller dimulai."); self._start_pair_analyzers()
        while self.is_running:
            self.trade_manager.check_pnl_rules()
            if self.trade_manager.session_ending:
                self.log_message.emit("Controller", "Sesi berakhir terdeteksi."); self.stop(); continue
            status = self.trade_manager.get_status_for_ui()
            status_to_send = "Cooldown" if status.get('is_cooldown', False) else "Running"
            self.broker.publish("bot.status", {"account_number": self.account_number, "status": status_to_send})
            time.sleep(2)
        self.finished.emit()
    def _start_pair_analyzers(self):
        for pair_config in self.strategy_configs:
            symbol = pair_config.get('symbol');
            if not symbol: continue
            thread = QThread(); worker = PairAnalyzer(symbol, pair_config); worker.moveToThread(thread)
            worker.trade_signal_found.connect(self._handle_trade_signal)
            worker.log_message.connect(lambda s, m, l: self.log_message.emit(s, m))
            thread.started.connect(worker.run); thread.start()
            self.pair_analyzer_threads[symbol] = thread; self.pair_analyzers[symbol] = worker
            self.log_message.emit("Controller", f"Worker untuk {symbol} dimulai.")
    def _handle_trade_signal(self, signal: dict):
        symbol = signal.get('symbol'); can_trade, reason = self.trade_manager.can_place_new_trade(signal['entry'])
        if not can_trade: self.log_message.emit(symbol, f"Order ditolak: {reason}"); return
        lot_size, msg = calculate_lot_size(signal['risk_per_trade'], signal['entry'], signal['sl'], symbol)
        if not lot_size: self.log_message.emit(symbol, f"Lot gagal: {msg}"); return
        order_type_map = {"BUY_STOP": mt5.ORDER_TYPE_BUY_STOP, "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP, "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT, "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT}
        order_type = order_type_map.get(signal['signal'])
        is_placed, result = place_pending_order(symbol, order_type, lot_size, signal['entry'], signal['sl'], signal['tp'], signal['magic_number'])
        if is_placed and hasattr(result, 'order'):
            self.trade_manager.register_new_pending_order(result.order, symbol, signal['magic_number'], signal['entry'])
            self.log_message.emit(symbol, f"✅ Order #{result.order} berhasil.")
        else: self.log_message.emit(symbol, f"❌ Gagal order: {result}")

class ProcessHandler(QObject):
    """Kelas utama yang mengelola seluruh proses backend untuk satu bot."""
    def __init__(self, account_info: dict, parent=None):
        super().__init__(parent)
        self.account_info = account_info
        self.account_number = account_info.get('number')
        self.broker = BrokerClient()
        self.bot_controller = None
        self.bot_thread = None

    def start_initialization(self, ui):
        """Mulai proses koneksi MT5 dan hubungkan sinyalnya ke UI."""
        self.init_thread = QThread()
        self.initializer = BotInitializer(self.account_info)
        self.initializer.moveToThread(self.init_thread)
        self.initializer.initialization_success.connect(lambda: self.on_init_success(ui))
        self.initializer.initialization_failed.connect(lambda err: self.on_init_failed(ui, err))
        self.init_thread.started.connect(self.initializer.run)
        self.init_thread.start()

    def on_init_success(self, ui):
        ui.set_connection_status("Terhubung", "green")
        ui.set_controls_enabled(True)
        ui.add_log("System", "Koneksi MT5 berhasil. Engine siap.")
    
    def on_init_failed(self, ui, error_message):
        ui.set_connection_status("Gagal", "red")
        ui.add_log("System", f"Error inisialisasi: {error_message}")

    def start_engine(self, ui):
        """Memulai BotController di background thread."""
        ui.add_log("Engine", "Mencoba memulai engine...")
        try:
            config_path = os.path.join(PROJECT_ROOT, 'configs', f"{self.account_number}.json")
            with open(config_path, 'r') as f: configs = json.load(f)
        except Exception as e:
            ui.add_log("Engine", f"Gagal memuat config: {e}")
            return

        self.bot_thread = QThread()
        self.bot_controller = BotController(self.account_number, configs, self.broker)
        self.bot_controller.moveToThread(self.bot_thread)
        
        self.bot_controller.log_message.connect(ui.add_log)
        self.bot_controller.finished.connect(lambda: self.on_engine_stopped(ui))
        self.bot_thread.started.connect(self.bot_controller.run)
        self.bot_thread.start()
        ui.set_engine_running(True)

    def on_engine_stopped(self, ui):
        ui.add_log("Engine", "Controller telah berhenti.")
        self.bot_thread.quit()
        self.bot_thread.wait()
        self.bot_thread = None
        self.bot_controller = None
        ui.set_engine_running(False)

    def stop_engine(self, ui):
        if self.bot_controller:
            self.bot_controller.stop()
            ui.add_log("Engine", "Sinyal stop dikirim...")
    
    def shutdown(self):
        """Fungsi cleanup saat aplikasi ditutup."""
        if self.bot_controller: self.bot_controller.stop()
        shutdown_connection()
        self.broker.publish("bot.status", {"account_number": self.account_number, "status": "OFFLINE"})