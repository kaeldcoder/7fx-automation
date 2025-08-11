# FILE 1 # D:\7FX Automation\robots\HFT explosive m1\account_control_panel.py

import sys
import os
import time as time_mod
import keyring
import json
from datetime import datetime, timedelta, time
import pytz
import importlib
import re
import inspect
import socket
import threading
import traceback

import warnings
from pandas.errors import ChainedAssignmentError
warnings.filterwarnings("ignore", category=FutureWarning)

def camel_to_snake(name):
    """Mengubah NamaKelas (CamelCase) menjadi nama_kelas (snake_case) untuk nama file."""
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

# --- Konfigurasi Path ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Impor Pustaka & Modul Kustom ---
from PyQt6.QtWidgets import (QMainWindow, QApplication, QWidget, QVBoxLayout, QGridLayout, 
                             QLabel, QPushButton, QTextEdit, QMessageBox, QGroupBox, QFrame, QHBoxLayout, QDialog)
from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer, QMutex, Qt, QPoint
import qtawesome as qta

# Impor jendela-jendela baru kita
from settings_window import SettingsWindow
from monitoring_window import MonitoringWindow
from communication_client import StatusClient
from loading_window import GenericLoadingDialog
from shutdown_worker import ShutdownWorker

# Impor modul-modul dari Library
from Library.utils.path_finder import (load_known_paths, load_accounts_data)
from Library.broker_interface.mt5_connector import connect_to_mt5, shutdown_connection
import Library.broker_interface.mt5_broker as mt5_broker
from Library.risk_management.position_sizer import calculate_lot_size
from Library.broker_interface.mt5_executor import place_pending_order, place_market_order
from Library.risk_management.trade_manager import TradeManager
from Library.utils.market_analyzer import SpreadAnalyzer
import MetaTrader5 as mt5

class AccountInfoWorker(QObject):
    """Worker untuk mengambil info akun MT5 secara aman di thread terpisah."""
    finished = pyqtSignal(dict)  # Sinyal jika berhasil, membawa data akun
    error = pyqtSignal(str)      # Sinyal jika terjadi error

    def run(self):
        """Metode ini akan dijalankan di thread terpisah."""
        try:
            # Lakukan operasi blocking di sini
            if not mt5.account_info():
                # Coba lagi sekali jika gagal pertama kali untuk memberi waktu MT5 merespon
                time_mod.sleep(1) 
                if not mt5.account_info():
                    raise ConnectionError("Failed to retrieve account info from MT5.")
            
            acc_info = mt5.account_info()._asdict()
            self.finished.emit(acc_info) # Kirim data kembali ke UI thread
        except Exception as e:
            # Buat pesan error yang lebih informatif
            error_message = f"Error fetching account info: {e}\n\n" \
                            "Pastikan terminal MT5 sudah berjalan, login berhasil, dan koneksi internet stabil."
            self.error.emit(error_message)

class ControlPanelWindow(QMainWindow):
    """
    Kelas ini bertindak sebagai 'bingkai' utama yang frameless untuk panel kontrol.
    """
    def __init__(self, account_info: dict, available_symbols: list, parent=None):
        super().__init__(parent)
        self.account_info = account_info
        
        # --- Pengaturan Window Frameless ---
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("MainDashboard") # Gunakan ObjectName yang sama untuk style
        self.dragPos = QPoint()

        # --- Widget Kontainer Utama ---
        self.central_widget = QWidget()
        self.central_widget.setObjectName("PanelCentralWidget")
        self.setCentralWidget(self.central_widget)
        
        outer_layout = QVBoxLayout(self.central_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        self._is_dragging = False
        self.header = self._create_header()
        outer_layout.addWidget(self.header)
        
        # Buat widget konten utama (kelas AccountControlPanel yang lama)
        # dan tambahkan ke layout
        self.content_panel = AccountControlPanel(account_info, available_symbols)
        outer_layout.addWidget(self.content_panel)

    def _create_header(self):
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 0, 5, 0)
        
        acc_num = self.account_info.get("number", "N/A")
        app_title = QLabel(self.tr(f"Control Panel - Account {acc_num}"))
        app_title.setObjectName("HeaderTitle")

        btn_minimize = QPushButton(qta.icon('fa5s.minus', color='#6a6e79'), "")
        btn_minimize.clicked.connect(self.showMinimized)
        btn_close = QPushButton(qta.icon('fa5s.times', color='#6a6e79'), "")
        btn_close.clicked.connect(self.close)
        
        for btn in [btn_minimize, btn_close]:
            btn.setObjectName("ControlButton")
            btn.setFixedSize(30, 30)

        header_layout.addWidget(app_title)
        header_layout.addStretch()
        header_layout.addWidget(btn_minimize)
        header_layout.addWidget(btn_close)
        return header

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.header.geometry().contains(event.pos()):
                widget_under_cursor = self.childAt(event.pos())
                if widget_under_cursor and widget_under_cursor.objectName() == "ControlButton":
                    super().mousePressEvent(event)
                    return

                self._is_dragging = True
                self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Dipanggil saat tombol mouse dilepas."""
        self._is_dragging = False
        super().mouseReleaseEvent(event)
    
    def closeEvent(self, event):
        panel = self.content_panel
        panel.handle_log_update(panel.tr("Global"), panel.tr("Window closed, initiating full shutdown..."))
    
        shutdown_worker = ShutdownWorker(
            panel.bot_worker, panel.worker_thread,
            panel.heartbeat_worker, panel.heartbeat_thread,
            panel.status_client, panel.account_number,
            full_shutdown=True
        )
        loading_dialog = GenericLoadingDialog(shutdown_worker, 
                                            start_text=panel.tr("Finalizing all processes..."),
                                            title=panel.tr("Closing..."),
                                            parent=self)
        loading_dialog.execute()
        event.accept()

class HeartbeatWorker(QObject):
    finished = pyqtSignal()
    send_status_to_dashboard = pyqtSignal(int, str)

    def __init__(self, account_number: int, bot_worker_ref: 'BotWorker', mutex: QMutex):
        super().__init__()
        self.account_number = account_number
        self.bot_worker = bot_worker_ref
        self.tm_mutex = mutex
        self.is_running = True
        self.last_bot_worker_heartbeat = 0
        self.current_status = "Standby"
        self.manual_override_status = None

    def run(self):
        while self.is_running:
            if self.manual_override_status:
                self.current_status = self.manual_override_status
            elif self.bot_worker and self.bot_worker.is_running:
                self.last_bot_worker_heartbeat = self.bot_worker.last_heartbeat
                time_since_last_beat = time_mod.time() - self.last_bot_worker_heartbeat

                if time_since_last_beat > 20:
                    self.current_status = "STALLED"
                else:
                    self.tm_mutex.lock()
                    tm_status = self.bot_worker.trade_manager.get_status_for_ui()
                    self.tm_mutex.unlock()
                    if tm_status.get('is_cooldown', False):
                        self.current_status = "COOLDOWN"
                    else:
                        self.current_status = "RUNNING"
            elif self.bot_worker and not self.bot_worker.is_running:
                self.current_status = "STOPPED"
            else:
                self.current_status = "STANDBY"

            self.send_status_to_dashboard.emit(self.account_number, self.current_status)

            time_mod.sleep(5)
        self.finished.emit()
    def stop(self):
        self.is_running = False

# --- Kelas Worker untuk Logika Bot di Background ---
class BotWorker(QObject):
    finished = pyqtSignal()
    log_update = pyqtSignal(str, str)
    trade_log_update = pyqtSignal(str, str, str)
    status_update = pyqtSignal(dict)
    tm_status_update = pyqtSignal(dict) 

    def __init__(self, configs: list, tm_config: dict, mutex: QMutex):
        super().__init__()
        self.configs = configs
        self.is_running = True
        self.tm_mutex = mutex
        self.trade_manager = TradeManager(tm_config, mt5, mt5_broker, bot_worker_ref=self)
        self.engine_mode = "RUNNING"

        self.active_strategies = {}
        self.last_order_times = {}
        self.engine_start_time = 0
        self.last_heartbeat = time_mod.time()
        self._load_strategies() 
        self.last_heartbeat = 0

        self.order_cooldown_seconds = tm_config.get('order_cooldown_seconds', 1.0)
        self.last_signal_cache = {}
        self.signal_cache_duration = 60
        self.last_debug_messages = {}

    def _load_strategies(self):
        """Helper untuk memuat semua strategi yang dikonfigurasi."""
        for config in self.configs:
            symbol = config.get('symbol')
            if not symbol: continue

            try:
                entry_class_name = config.get('strategy_class')
                if entry_class_name:
                    entry_module_name = camel_to_snake(entry_class_name)
                    entry_module = importlib.import_module(f"Library.strategies.{entry_module_name}")
                    EntryStrategyClass = getattr(entry_module, entry_class_name)
                    analyzer = SpreadAnalyzer(tolerance_multiplier=config.get('spread_tolerance', 1.5))
                    entry_instance = EntryStrategyClass(mt5, config, analyzer)
                    self.active_strategies[symbol] = {'entry': entry_instance, 'exit': None}
                    log_msg = self.tr("Entry Strategy '{0}' loaded.").format(EntryStrategyClass.strategy_name)
                    self.log_update.emit(symbol, log_msg)
                else:
                    self.log_update.emit(symbol, self.tr("Warning: No entry strategy selected."))
                    continue

                # Memuat Strategi Exit jika diaktifkan
                if config.get('use_smart_exit', False):
                    exit_class_name = config.get('exit_strategy_class')
                    if exit_class_name:
                        exit_module_name = camel_to_snake(exit_class_name)
                        exit_module = importlib.import_module(f"Library.exit_strategies.{exit_module_name}")
                        ExitStrategyClass = getattr(exit_module, exit_class_name)
                        exit_instance = ExitStrategyClass(mt5, config)
                        self.active_strategies[symbol]['exit'] = exit_instance
                        log_msg = self.tr("-> Exit Strategy '{0}' enabled.").format(ExitStrategyClass.exit_name)
                        self.log_update.emit(symbol, log_msg)

            except Exception as e:
                log_msg = self.tr("FAILED to load strategy. Error: {0}").format(e)
                self.log_update.emit(symbol, log_msg)

    def _send_status_update(self):
        self.last_heartbeat = time_mod.time()
        self.tm_mutex.lock()
        tm_status_ui = self.trade_manager.get_status_for_ui()
        self.tm_mutex.unlock()

        tm_status_ui['engine_mode'] = self.engine_mode
        
        elapsed_seconds = time_mod.time() - self.engine_start_time
        minutes, seconds = divmod(elapsed_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        tm_status_ui['runtime_str'] = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        tm_status_ui['last_heartbeat'] = self.last_heartbeat
        
        self.tm_status_update.emit(tm_status_ui)

    def enter_cooldown_mode(self):
        self.log_update.emit(self.tr("Global"), self.tr(">>> BotWorker: enter_cooldown_mode FUNCTION CALLED."))
        self.engine_mode = "COOLDOWN"
        end_time_obj = self.trade_manager.cooldown_end_time
        if end_time_obj:
            end_time_str = end_time_obj.strftime('%A, %d %b %Y %H:%M')
            self.log_update.emit(self.tr("Global"), self.tr("ENGINE MODE CHANGED -> COOLDOWN until {0}.").format(end_time_str))
        else:
            self.log_update.emit(self.tr("Global"), self.tr("ENGINE MODE CHANGED -> COOLDOWN."))

    def running_loop_iteration(self):
        try:
            self.tm_mutex.lock()
            if self.trade_manager.is_closing_actively:
                return 
            self.trade_manager.check_pnl_rules()
        finally:
            self.tm_mutex.unlock()

        for symbol, strategy_pair in self.active_strategies.items():
            if not self.is_running: break

            entry_strategy = strategy_pair['entry']
            exit_strategy = strategy_pair.get('exit')
            magic_number = entry_strategy.config.get('magic_number')

            mt5_broker.manage_trailing_stop(symbol, magic_number)
            mt5_broker.cancel_expired_pending_orders(magic_number, 3600)
            
            open_positions_count = len(mt5_broker.get_open_positions(symbol, magic_number) or [])

            sig = inspect.signature(entry_strategy.check_signal)
            if len(sig.parameters) > 0:
                market_status = entry_strategy.check_signal(open_positions_count)
            else:
                market_status = entry_strategy.check_signal()
            if not market_status: continue

            try:
                self.tm_mutex.lock()

                market_status['entry_strategy_name'] = entry_strategy.strategy_name
                market_status['entry_labels'] = entry_strategy.live_status_labels

                if exit_strategy:
                    try:
                        open_positions = mt5_broker.get_open_positions(symbol, magic_number)
                        result = exit_strategy.check_exit_conditions(symbol, entry_strategy.timeframe, open_positions or [], self.trade_manager.tracked_orders)
                    
                        if isinstance(result, tuple) and len(result) == 3:
                            tickets_to_close, sl_modifications, exit_live_status = result
                            if tickets_to_close: self.trade_manager.close_specific_positions(tickets_to_close, self.tr("Smart Exit Triggered"))
                            if sl_modifications: self.trade_manager.modify_positions_sl(sl_modifications)
                            market_status.update(exit_live_status)
                            market_status['exit_strategy_name'] = exit_strategy.exit_name
                            market_status['exit_labels'] = exit_strategy.live_status_labels
                        else:
                            self.log_update.emit(symbol, self.tr("Warning: Exit strategy '{0}' returned incorrect data format.").format(exit_strategy.exit_name))
                    
                        if hasattr(exit_strategy, 'log_messages') and exit_strategy.log_messages:
                            for log_symbol, log_message, log_level in exit_strategy.log_messages: self.trade_log_update.emit(log_symbol, log_message, log_level)
                            exit_strategy.log_messages.clear()           

                    except Exception as e:
                        self.log_update.emit(symbol, self.tr("ERROR inside exit strategy '{0}': {1}").format(exit_strategy.exit_name, e))

                self.status_update.emit(market_status)
                trade_signal_data = market_status.get("trade_signal")
            
                if trade_signal_data:
                    self.trade_log_update.emit(symbol, self.tr("Signal detected: {0}.").format(trade_signal_data['signal']), "INFO")

                    current_time = time_mod.time()
                    last_order_time = self.last_order_times.get(symbol, 0)
                    if current_time - last_order_time < self.order_cooldown_seconds:
                        self.trade_log_update.emit(symbol, self.tr("{0} second cooldown active, signal ignored.").format(self.order_cooldown_seconds), "INFO")
                        continue

                    can_trade, reason = self.trade_manager.can_place_new_trade(trade_signal_data['entry'])
                        
                    if not can_trade:
                        self.trade_log_update.emit(symbol, self.tr("Signal ignored: {0}").format(reason), "WARNING")
                        continue           

                    self.last_order_times[symbol] = time_mod.time()

                    lot_mode = entry_strategy.config.get("lot_mode", "FIXED")
                    if lot_mode == "FIXED":
                        lot_size = entry_strategy.config.get("lot_size", 0.1)
                    else:
                        lot_size, msg = calculate_lot_size(entry_strategy.config.get('risk_per_trade', 1.0), 
                                                            trade_signal_data['entry'], 
                                                            trade_signal_data['sl'], 
                                                            symbol)

                    if not lot_size:
                        self.trade_log_update.emit(symbol, self.tr("⚠️ Warning: {0}. Order not placed.").format(msg), "WARNING")
                        continue

                    signal_type = trade_signal_data['signal']
                    if "STOP" in signal_type or "LIMIT" in signal_type:
                        order_type = mt5.ORDER_TYPE_BUY_STOP if signal_type == "BUY_STOP" else \
                                     mt5.ORDER_TYPE_SELL_STOP if signal_type == "SELL_STOP" else \
                                     mt5.ORDER_TYPE_BUY_LIMIT if signal_type == "BUY_LIMIT" else \
                                     mt5.ORDER_TYPE_SELL_LIMIT
                    
                        is_placed, result = place_pending_order(
                            symbol, order_type, lot_size, 
                            trade_signal_data['entry'], 
                            trade_signal_data['sl'], 
                            trade_signal_data['tp'], 
                            magic_number
                        )
                    
                        if is_placed and result and hasattr(result, 'order'):
                            strategy_info = {
                                'entry_strategy': entry_strategy.strategy_name,
                                'exit_strategy': exit_strategy.exit_name if exit_strategy else 'None'
                            }
                            self.trade_manager.register_new_pending_order(
                                result.order, symbol, magic_number, 
                                trade_signal_data['entry'],
                                strategy_info
                            )
                            log_message = (self.tr("✅ Order {0} #{1} @ {2} successfully placed.").format(signal_type, result.order, trade_signal_data['entry']))
                            self.trade_log_update.emit(symbol, log_message, "SUCCESS")
                            time_mod.sleep(2)
                        else:
                            self.trade_log_update.emit(symbol, self.tr("❌ Failed to place order: {0}").format(result), "ERROR")

                    else: 
                        order_type = mt5.ORDER_TYPE_BUY if signal_type == "BUY" else mt5.ORDER_TYPE_SELL

                        positions_to_close = market_status.get("positions_to_close", [])
                        for pos in positions_to_close:
                            mt5.close(pos)
                            time_mod.sleep(0.5)
                        sl = trade_signal_data.get("sl", 0.0)
                        tp = trade_signal_data.get("tp", 0.0)

                        is_placed, result = place_market_order(
                            symbol, order_type, lot_size, 
                            sl, 
                            tp, 
                            magic_number
                        )
                    
                        if is_placed and result and hasattr(result, 'deal'):
                            self.last_order_times[symbol] = time_mod.time()
                            self.trade_manager.last_global_order_time = time_mod.time()
                            log_message = (self.tr("✅ Order {0} #{1} successfully executed.").format(signal_type, result.deal))
                            self.trade_log_update.emit(symbol, log_message, "SUCCESS")
                            time_mod.sleep(2)
                        else:
                            self.trade_log_update.emit(symbol, self.tr("❌ Failed to execute order: {0}").format(result), "ERROR")
                        
            finally:
                self.tm_mutex.unlock()

    def cooldown_loop_iteration(self):
        if datetime.now(pytz.utc) > self.trade_manager.cooldown_end_time:
            self.log_update.emit(self.tr("Global"), self.tr("Cooldown finished. Resetting session & returning to RUNNING mode."))
            self.trade_manager.reset_session()
            self.engine_mode = "RUNNING"

    def run(self):
        self.engine_start_time = time_mod.time()
        self.log_update.emit(self.tr("Global"), self.tr("✅ Worker & TradeManager started. Mode: {0}.").format(self.engine_mode))
        
        while self.is_running:
            self._send_status_update()
            if self.engine_mode == "RUNNING":
                self.running_loop_iteration()
            elif self.engine_mode == "COOLDOWN":
                self.cooldown_loop_iteration()

            time_mod.sleep(1)
        
        self.log_update.emit(self.tr("Global"), self.tr("⏹️ Worker has been stopped."))
        self.finished.emit()

    def enter_stopping_mode(self, reason: str):
        if self.engine_mode != "RUNNING": return 
            
        self.log_update.emit(self.tr("Global"), self.tr("ENGINE MODE CHANGED -> STOPPING. Closing all positions..."))
        self.trade_manager.close_all_positions_and_orders(reason)
        self.log_update.emit(self.tr("Global"), self.tr("All positions closed. Initiating cooldown process..."))
        self.trade_manager.check_session_completion_and_report()
        self.enter_cooldown_mode()

    def stop(self):
        self.is_running = False

class AccountControlPanel(QWidget):
    panel_closed = pyqtSignal(int)
    engine_status_changed = pyqtSignal(int, str)

    def __init__(self, account_info: dict,available_symbols: list, parent=None):
        super().__init__(parent)
        self.account_info = account_info
        self.account_number = int(self.account_info.get('number'))
        self.mt5_path = self.account_info.get('path')
        self.server = self.account_info.get('server')
        self.is_connected = True
        self.available_symbols = available_symbols
        self.worker_thread = None
        self.bot_worker = None
        self.heartbeat_thread = None
        self.heartbeat_worker = None
        self.settings_window = None
        self.monitoring_window = None
        self.status_client = StatusClient()
        self.tm_mutex = QMutex()
        self.is_weekend_cooldown = False
        self.cooldown_end_time_dt = None
        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.setInterval(1000) # Tick setiap 1 detik
        self.cooldown_timer.timeout.connect(self._update_cooldown_timer)
        self.init_ui()
        self.post_load_setup()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(15)

        info_group = QGroupBox(self.tr("Account Info"))
        info_layout = QGridLayout(info_group)
        info_layout.addWidget(QLabel(self.tr("MT5 Path:")), 0, 0)
        info_layout.addWidget(QLabel(f"<b>{os.path.basename(os.path.dirname(self.mt5_path))}</b>"), 0, 1)
        info_layout.addWidget(QLabel(self.tr("Server:")), 1, 0)
        info_layout.addWidget(QLabel(f"<b>{self.server}</b>"), 1, 1)
        main_layout.addWidget(info_group)

        control_group = QGroupBox(self.tr("Engine Control"))
        control_layout = QHBoxLayout(control_group)

        self.btn_toggle_engine = QPushButton(qta.icon('fa5s.play', color='white'), self.tr(" Start Engine"))
        self.btn_open_settings = QPushButton(qta.icon('fa5s.cogs', color='white'), self.tr(" Settings"))
        self.btn_show_monitor = QPushButton(qta.icon('fa5s.chart-line', color='white'), self.tr(" Monitor"))
        
        buttons = [self.btn_toggle_engine, self.btn_open_settings, self.btn_show_monitor]
        for btn in buttons:
            btn.setObjectName("AccountActionButton")
            control_layout.addWidget(btn)

        self.btn_toggle_engine.clicked.connect(self.toggle_engine)
        self.btn_open_settings.clicked.connect(self.open_settings)
        self.btn_show_monitor.clicked.connect(self.show_monitoring_window)
        main_layout.addWidget(control_group)

        # --- Sisa dari UI tidak perlu diubah ---
        status_group = QGroupBox(self.tr("Live Session Status"))
        status_layout = QGridLayout(status_group)
        status_layout.addWidget(QLabel(self.tr("Engine Status:")), 0, 0)
        self.engine_status_label = QLabel("<b>OFFLINE</b>")
        status_layout.addWidget(self.engine_status_label, 0, 1)
        self.cooldown_countdown_label = QLabel("")
        self.cooldown_countdown_label.setStyleSheet("font-weight: bold; color: #E67E22;")
        status_layout.addWidget(self.cooldown_countdown_label, 0, 2, 1, 2)
        status_layout.addWidget(QLabel(self.tr("Runtime:")), 1, 0)
        self.runtime_label = QLabel("00:00:00")
        status_layout.addWidget(self.runtime_label, 1, 1)
        status_layout.addWidget(QLabel(self.tr("Session P/L:")), 1, 2)
        self.pnl_label = QLabel("0.00%")
        status_layout.addWidget(self.pnl_label, 1, 3)
        status_layout.addWidget(QLabel(self.tr("Balance:")), 2, 0)
        self.balance_label = QLabel("$0.00")
        status_layout.addWidget(self.balance_label, 2, 1)
        status_layout.addWidget(QLabel(self.tr("Equity:")), 2, 2)
        self.equity_label = QLabel("$0.00")
        status_layout.addWidget(self.equity_label, 2, 3)
        status_layout.addWidget(QLabel(self.tr("Status Message:")), 3, 0)
        self.message_label = QLabel(self.tr("Engine is not running."))
        status_layout.addWidget(self.message_label, 3, 1, 1, 3)
        status_layout.addWidget(QLabel(self.tr("Profit Target at:")), 4, 0)
        self.target_profit_label = QLabel("$0.00")
        status_layout.addWidget(self.target_profit_label, 4, 1)
        status_layout.addWidget(QLabel(self.tr("Loss Limit at:")), 4, 2)
        self.loss_target_label = QLabel("$0.00")
        status_layout.addWidget(self.loss_target_label, 4, 3)
        status_layout.setColumnStretch(1, 1)
        status_layout.setColumnStretch(3, 1)
        main_layout.addWidget(status_group)
        
        log_group = QGroupBox(self.tr("Account Activity Log"))
        log_group.setObjectName("LogGroup")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        main_layout.addWidget(log_group)

    def post_load_setup(self):
        self.btn_toggle_engine.setEnabled(False)
        self.btn_open_settings.setEnabled(False)
        self.btn_show_monitor.setEnabled(False)

        self.balance_label.setText("<i>Loading...</i>")
        self.equity_label.setText("<i>Loading...</i>")
        
        self.fetch_account_data_async()

        if self.status_client.connect():
            self.send_status_update(self.account_number, "Standby")
            self.start_heartbeat_worker()
        else:
            QMessageBox.critical(self, self.tr("Connection Failed"), self.tr("Failed to connect to the status server on the Main Dashboard."))

    def fetch_account_data_async(self):
        self.handle_log_update("Global", "Fetching initial account data...")
        self.info_worker_thread = QThread()
        self.info_worker = AccountInfoWorker()
        self.info_worker.moveToThread(self.info_worker_thread)

        self.info_worker.finished.connect(self.on_account_data_received)
        self.info_worker.error.connect(self.on_account_data_error)
        
        self.info_worker_thread.finished.connect(self.info_worker_thread.deleteLater)
        self.info_worker.finished.connect(self.info_worker_thread.quit)
        self.info_worker.error.connect(self.info_worker_thread.quit)

        self.info_worker_thread.started.connect(self.info_worker.run)
        self.info_worker_thread.start()

    def on_account_data_received(self, acc_info: dict):
        self.handle_log_update("Global", "Account data received successfully.")
        
        config_path = f"configs/{self.account_number}.json"
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f).get('tm_config', {})
        self.update_live_display(acc_info, config)

        self.btn_toggle_engine.setEnabled(True)
        self.btn_open_settings.setEnabled(True)

    def on_account_data_error(self, error_message: str):
        self.handle_log_update("Global", f"ERROR: Could not retrieve account data.")
        self.balance_label.setText("<b><font color='red'>Error</font></b>")
        self.equity_label.setText("<b><font color='red'>Error</font></b>")
        QMessageBox.critical(self, "MT5 Connection Error", error_message)

    def _handle_hide_request(self):
        if self.monitoring_window and self.monitoring_window.isVisible():
            self.monitoring_window.hide()
        self.hide()

    def _handle_show_request(self):
        self.showNormal()
        self.activateWindow()
        if self.monitoring_window:
            self.monitoring_window.show()

    def update_live_display(self, acc_info: dict, tm_config: dict):
        balance = acc_info.get('balance', 0)
        equity = acc_info.get('equity', 0)
        self.balance_label.setText(f"<b>${balance:,.2f}</b>")
        self.equity_label.setText(f"<b>${equity:,.2f}</b>")

        pt_cfg = tm_config.get('profit_target', {})
        if pt_cfg.get('type') == 'percent':
            pt_val = balance * (1 + pt_cfg.get('value', 0) / 100)
        else:
            pt_val = balance + pt_cfg.get('value', 0)
        self.target_profit_label.setText(f"<b>${pt_val:,.2f}</b>")

        lt_cfg = tm_config.get('loss_target', {})
        if lt_cfg.get('type') == 'percent':
            lt_val = balance * (1 - lt_cfg.get('value', 0) / 100)
        else:
            lt_val = balance - lt_cfg.get('value', 0)
        self.loss_target_label.setText(f"<b>${lt_val:,.2f}</b>")

    def send_status_update(self, account_number: int, status: str):
        self.status_client.send_status(account_number, status)

    def open_settings(self):
        if not self.is_connected:
            QMessageBox.warning(self, self.tr("Not Connected"), self.tr("Please connect to the MT5 account first to load the symbol list.")); return
        dialog = SettingsWindow(self.available_symbols, self.account_number, self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            current_tm_config = dialog.get_tm_config()
            self.update_thresholds_from_settings(current_tm_config)
            log_msg = self.tr("Settings for account {0} have been saved.").format(self.account_number)
            self.handle_log_update(self.tr("Global"), log_msg)

    def update_thresholds_from_settings(self, tm_config: dict):
        try:
            acc_info = mt5.account_info()._asdict()
            self.update_live_display(acc_info, tm_config)
        except Exception as e:
            print(self.tr("Failed to update live threshold: {0}").format(e))
    
    def show_monitoring_window(self):
        if self.worker_thread and self.worker_thread.isRunning():
            if not self.monitoring_window:
                self.monitoring_window = MonitoringWindow(self)
            self.monitoring_window.show()
            self.monitoring_window.activateWindow()
        else:
            QMessageBox.information(self, self.tr("Info"), self.tr("The monitor window is only available when the engine is running."))
    
    def handle_log_update(self, symbol: str, message: str):
        timestamp = f"[{time_mod.strftime('%H:%M:%S')}]"
        self.log_area.append(f"{timestamp} [{symbol}] {message}")
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def start_heartbeat_worker(self):
        self.heartbeat_thread = QThread()
        self.heartbeat_worker = HeartbeatWorker(self.account_number, self.bot_worker, self.tm_mutex)
        self.heartbeat_worker.moveToThread(self.heartbeat_thread)
        self.heartbeat_worker.send_status_to_dashboard.connect(self.send_status_update)
        self.heartbeat_thread.started.connect(self.heartbeat_worker.run)
        self.heartbeat_thread.finished.connect(self.heartbeat_thread.deleteLater)
        self.heartbeat_worker.finished.connect(self.heartbeat_worker.deleteLater)
        self.heartbeat_thread.start()
        self.handle_log_update(self.tr("Global"), self.tr("Heartbeat worker started."))

    def toggle_engine(self):
        if (self.worker_thread and self.worker_thread.isRunning()) or self.is_weekend_cooldown:
            if self.is_weekend_cooldown:
                self.handle_log_update(self.tr("Global"), self.tr("Weekend cooldown stopped by user."))
                self.on_engine_stopped()
                return

            self.handle_log_update(self.tr("Global"), self.tr("Stopping engine..."))
            shutdown_worker = ShutdownWorker(
                self.bot_worker, self.worker_thread,
                self.heartbeat_worker, self.heartbeat_thread,
                self.status_client, self.account_number,
                full_shutdown=False
            )
            loading_dialog = GenericLoadingDialog(shutdown_worker, 
                                                  start_text=self.tr("Stopping engine..."),
                                                  parent=self)
            loading_dialog.execute()
            self.on_engine_stopped()

        else:
            config_path = f"configs/{self.account_number}.json"
            if not os.path.exists(config_path):
                QMessageBox.warning(self, self.tr("Configuration Not Found"),
                                      self.tr("Configuration file '{0}' not found.\nPlease open 'Strategy Settings' and save the settings first.").format(config_path))
                return
            try:
                with open(config_path, 'r') as f: saved_data = json.load(f)
                tm_config = saved_data.get('tm_config', {})
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error Reading Config"), self.tr("Failed to process configuration file: {0}").format(e))
                return
            
            weekend_cooldown_end = self._get_weekend_cooldown_end_time(tm_config)
            if weekend_cooldown_end:
                QMessageBox.information(self, self.tr("Market Closed"), 
                                          self.tr("It is currently the weekend (market is closed).\nThe engine will enter Cooldown mode until the market reopens."))
                self.is_weekend_cooldown = True

                if self.heartbeat_worker:
                    self.heartbeat_worker.manual_override_status = "COOLDOWN"
                
                self.engine_status_label.setText("<b><font color='#E67E22'>COOLDOWN</font></b>")
                self.message_label.setText(self.tr("Waiting for the market to open."))
                self.handle_log_update(self.tr("Global"), self.tr("Start attempt during market holiday. Entering Cooldown mode."))

                self.cooldown_end_time_dt = weekend_cooldown_end
                if not self.cooldown_timer.isActive():
                    self.cooldown_timer.start()

                self.btn_toggle_engine.setText(self.tr("Stop Engine"))
                self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop'))
                self.btn_open_settings.setEnabled(False)
                return

            try:
                all_configs = saved_data.get('strategy_configs', [])
                if not all_configs: 
                    QMessageBox.warning(self, self.tr("No Strategies"), self.tr("Add at least one pair in the 'Strategy per Pair' tab."))
                    return
            except Exception as e:
                QMessageBox.critical(self, self.tr("Validation Error/Reading Config"), self.tr("Failed to process configuration file: {0}").format(e))
                return
            
            self.bot_worker = BotWorker(all_configs, tm_config, self.tm_mutex)
            if self.heartbeat_worker:
                self.heartbeat_worker.bot_worker = self.bot_worker
            else:
                self.start_heartbeat_worker()
                self.heartbeat_worker.bot_worker = self.bot_worker
            if not self.bot_worker.active_strategies:
                QMessageBox.critical(self, self.tr("Failed to Load Strategies"),
                                       self.tr("No strategies were loaded successfully.\nEnsure all pair configurations (especially Symbol and Strategy) are filled out correctly."))
                return
            if not self.monitoring_window:
                self.monitoring_window = MonitoringWindow(self)
            self.monitoring_window.clear_all(); self.monitoring_window.show(); self.btn_show_monitor.setEnabled(True)
            self.worker_thread = QThread()
            
            self.bot_worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.bot_worker.run)
            self.worker_finished_connection = self.bot_worker.finished.connect(self.on_worker_finished)
            self.bot_worker.log_update.connect(self.handle_log_update)
            self.bot_worker.tm_status_update.connect(self.handle_tm_status_update)
            if self.monitoring_window:
                self.bot_worker.status_update.connect(self.monitoring_window.update_pair_data)
                self.bot_worker.trade_log_update.connect(self.monitoring_window.add_log)
            
            self.worker_thread.start()
            self.btn_toggle_engine.setText("Stop Engine"); self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop'))
            self.btn_open_settings.setEnabled(False)

    def on_engine_stopped(self):
        if self.heartbeat_worker:
            self.heartbeat_worker.bot_worker = None
            self.heartbeat_worker.manual_override_status = None

        self.is_weekend_cooldown = False
        self.bot_worker = None
        self.worker_thread = None

        self.engine_status_label.setText("<b><font color='red'>OFFLINE</font></b>")
        self.runtime_label.setText("00:00:00")
        self.btn_toggle_engine.setText(self.tr("Start Engine"))
        self.btn_toggle_engine.setIcon(qta.icon('fa5s.play'))
        self.btn_toggle_engine.setEnabled(True)
        self.btn_open_settings.setEnabled(True)
        self.btn_show_monitor.setEnabled(False)

        if self.cooldown_timer.isActive():
            self.cooldown_timer.stop()
        self.cooldown_countdown_label.setText("")
    
    def on_worker_finished(self):
        self.on_engine_stopped()

    def handle_tm_status_update(self, tm_status: dict):
        balance = tm_status.get('balance', 0)
        equity = tm_status.get('equity', 0)
        pnl = tm_status.get('pnl_percent', '0.00')
        runtime = tm_status.get('runtime_str', '00:00:00')
        message = tm_status.get('status_message', '')
        is_cooldown = tm_status.get('is_cooldown', False)

        if is_cooldown:
            # Ambil waktu dari backend
            self.cooldown_end_time_dt = tm_status.get('cooldown_end_dt')
            # Mulai timer jika belum berjalan
            if not self.cooldown_timer.isActive():
                self.cooldown_timer.start()
        else:
            # Jika tidak dalam mode cooldown, hentikan timer dan bersihkan label
            if self.cooldown_timer.isActive():
                self.cooldown_timer.stop()
            self.cooldown_countdown_label.setText("")
            self.cooldown_end_time_dt = None

        engine_mode = tm_status.get('engine_mode', 'RUNNING')

        if engine_mode == "COOLDOWN":
            self.engine_status_label.setText("<b><font color='#E67E22'>COOLDOWN</font></b>")
        elif engine_mode == "STOPPING":
            self.engine_status_label.setText("<b><font color='orange'>STOPPING...</font></b>")
        else: # Mode RUNNING
            self.engine_status_label.setText("<b><font color='green'>RUNNING</font></b>")

        self.balance_label.setText(f"<b>${balance:,.2f}</b>")
        self.equity_label.setText(f"<b>${equity:,.2f}</b>")
        self.pnl_label.setText(f"<b>{pnl}</b>")
        self.runtime_label.setText(runtime)
        self.message_label.setText(message)
        self.target_profit_label.setText(f"<b>${tm_status.get('profit_threshold', 0):,.2f}</b>")
        self.loss_target_label.setText(f"<b>${tm_status.get('loss_threshold', 0):,.2f}</b>")

        if is_cooldown:
            self.engine_status_changed.emit(self.account_number, "COOLDOWN")

    def _update_cooldown_timer(self):
        if self.cooldown_end_time_dt:
            # Dapatkan zona waktu dari sistem untuk perbandingan yang akurat
            now = datetime.now(self.cooldown_end_time_dt.tzinfo)
            
            if now < self.cooldown_end_time_dt:
                remaining = self.cooldown_end_time_dt - now
                
                # Format timedelta ke H:M:S
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                countdown_str = f"({remaining.days}d {hours:02}:{minutes:02}:{seconds:02})"
                self.cooldown_countdown_label.setText(countdown_str)
            else:
                # Waktu cooldown habis
                self.cooldown_countdown_label.setText(self.tr("(Finished)"))
                self.cooldown_timer.stop()

    def _get_weekend_cooldown_end_time(self, tm_config: dict):
        """
        Memeriksa apakah saat ini akhir pekan. 
        Jika ya, kembalikan waktu berakhir cooldown di Senin pagi.
        Jika tidak, kembalikan None.
        """
        timezone_str = tm_config.get('timezone', 'UTC')
        try:
            user_tz = pytz.timezone(timezone_str)
            now = datetime.now(user_tz)
        except pytz.UnknownTimeZoneError:
            # Jika timezone tidak valid, gunakan UTC sebagai fallback
            user_tz = pytz.utc
            now = datetime.now(user_tz)
            self.handle_log_update(self.tr("Global"), self.tr("Warning: Timezone '{0}' is invalid, using UTC.").format(timezone_str))

        if now.weekday() >= 5: # 5 = Sabtu, 6 = Minggu

            cooldown_cfg = tm_config.get('cooldown_config', {})

            if cooldown_cfg.get('mode') == 'next_day_at':
                target_time_str = cooldown_cfg.get('time', '08:00')
                user_target_time = datetime.strptime(target_time_str, '%H:%M').time()
                
                days_to_monday = 7 - now.weekday()
                next_monday_date = (now + timedelta(days=days_to_monday)).date()
                
                user_cooldown_end = user_tz.localize(datetime.combine(next_monday_date, user_target_time))
                return user_cooldown_end

            # 2. Untuk mode lain (duration/next_candle), hitung waktu buka pasar
            days_until_sunday = 6 - now.weekday()
            upcoming_sunday_date = (now + timedelta(days=days_until_sunday)).date()
            
            market_open_utc = pytz.utc.localize(
                datetime.combine(upcoming_sunday_date, time(22, 0))
            )
            
            market_open_local = market_open_utc.astimezone(user_tz)
            return market_open_local
            
        return None