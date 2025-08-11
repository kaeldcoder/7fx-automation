# D:\7FX Automation\robots\HFT explosive m1\main_gui.py
# VERSI FINAL - DIPERBAIKI SECARA MENYELURUH

import sys
import os
import time
import keyring

# --- Konfigurasi Path ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Impor Pustaka & Modul Kustom ---
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, 
                             QMessageBox, QCheckBox, QGroupBox)
from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QAction
import qtawesome as qta

# Impor jendela-jendela baru kita
from settings_window import SettingsWindow
from monitoring_window import MonitoringWindow

# Impor modul-modul dari Library
from Library.utils.path_finder import (load_known_paths, save_known_paths, load_accounts_data, save_accounts_data,
                                       scan_for_metatrader_enhanced, find_by_smart_search, find_by_searching_disk)
from Library.broker_interface.mt5_connector import connect_to_mt5, shutdown_connection
from Library.technical_analysis.trend.ema_trend_V3 import check_ema_trend # Menggunakan versi terbaru
from Library.risk_management.position_sizer import calculate_lot_size
from Library.broker_interface.mt5_executor import place_pending_order
from Library.broker_interface.mt5_broker import cancel_expired_pending_orders, manage_trailing_stop
from Library.utils.market_analyzer import SpreadAnalyzer
import MetaTrader5 as mt5

# --- Kelas Worker untuk Logika Bot di Background ---
class BotWorker(QObject):
    finished = pyqtSignal()
    log_update = pyqtSignal(str, str)
    status_update = pyqtSignal(dict)

    def __init__(self, configs: list):
        super().__init__()
        self.configs = configs
        self.is_running = True
        self.spread_analyzers = {
            # !! PERBAIKAN: Menggunakan .get() untuk akses yang aman
            config['symbol']: SpreadAnalyzer(
                tolerance_multiplier=config.get('spread_tolerance', 1.5)
            ) for config in self.configs
        }
        self.last_trade_bar_time = {config['symbol']: None for config in self.configs}
        self.last_heartbeat = time.time()
        self.symbol_error_counts = {config['symbol']: 0 for config in self.configs}

    def run(self):
        self.log_update.emit("Global", f"✅ Worker dimulai. Memantau {len(self.configs)} pair...")
        
        while self.is_running:
            for config in self.configs:
                if not self.is_running: break
                
                symbol = config['symbol']
                # !! PERBAIKAN: Menggunakan .get() dengan nilai default yang aman
                magic_number = config.get('magic_number', 12345) 
                
                analyzer = self.spread_analyzers.get(symbol)
                if not analyzer: continue # Lewati jika analyzer tidak ada

                if self.symbol_error_counts.get(symbol, 0) > 5:
                    continue
                
                try:
                    manage_trailing_stop(symbol, magic_number)
                    # !! PERBAIKAN: Pastikan 'order_expiry_seconds' ada di config atau gunakan default
                    expiry_seconds = config.get('order_expiry_seconds', 3600)
                    cancel_expired_pending_orders(magic_number, expiry_seconds)
                except Exception as e:
                    self.log_update.emit(symbol, f"Error saat manajemen order: {e}")

                symbol_info = mt5.symbol_info(symbol)
                tick = mt5.symbol_info_tick(symbol)
                if not symbol_info or not tick:
                    continue
                
                analyzer.add_spread(symbol_info.spread)

                # !! PERBAIKAN: Memastikan 'timeframe' dikirim dengan benar
                market_status = check_ema_trend(
                    symbol, config['timeframe_int'], analyzer, config
                )
                

                
                if market_status:
                    self.status_update.emit(market_status)
                    if "Gagal" in market_status.get("condition", "") or "Tidak Cukup" in market_status.get("condition", ""):
                        self.symbol_error_counts[symbol] = self.symbol_error_counts.get(symbol, 0) + 1
                        if self.symbol_error_counts[symbol] == 1:
                             self.log_update.emit(symbol, "WARNING: Gagal mengambil data. Memeriksa kembali...")
                        elif self.symbol_error_counts[symbol] > 5:
                             self.log_update.emit(symbol, f"❌ ERROR: Gagal mengambil data untuk {symbol} 5x. Pair dihentikan.")
                        continue
                    self.symbol_error_counts[symbol] = 0

                signal_data = market_status.get("trade_signal") if market_status else None
                
                if signal_data:
                    current_bar_time = signal_data.get('bar_time')
                    last_traded_time = self.last_trade_bar_time.get(symbol)

                    entry = signal_data.get('entry')
                    sl = signal_data.get('sl')
                    tp = signal_data.get('tp')
                    signal_type = signal_data.get('signal')

                    signal_type_str = signal_data.get('signal')

                    # --- PERBAIKAN KRUSIAL DI SINI ---
                    # Ubah sinyal string menjadi konstanta integer MT5
                    if "BUY" in signal_type_str.upper():
                        order_type = mt5.ORDER_TYPE_BUY_STOP
                    elif "SELL" in signal_type_str.upper():
                        order_type = mt5.ORDER_TYPE_SELL_STOP
                    else:
                        self.log_update.emit(symbol, f"❌ GAGAL: Tipe sinyal tidak dikenal: {signal_type_str}")
                        continue

                    if all([current_bar_time, entry, sl, tp, signal_type]) and current_bar_time != last_traded_time:
                        self.log_update.emit(symbol, f"Sinyal {signal_type} baru pada bar {current_bar_time}. Mengeksekusi...")
                        
                        lot_size, message = calculate_lot_size(
                            risk_percent=config.get('risk_percent', 1.0),
                            entry_price=entry, # Gunakan variabel yang sudah aman
                            sl_level=sl,       # Gunakan variabel yang sudah aman
                            symbol=symbol
                        )

                        if lot_size is not None and lot_size > 0:
                            # 1. Tangkap hasil kembalian dari fungsi
                            is_placed, result_message = place_pending_order(
                                symbol=symbol,
                                order_type=order_type,
                                volume=lot_size,
                                entry_price=entry,
                                sl_level=signal_data['sl'],
                                tp_level=signal_data['tp'],
                                magic_number=magic_number
                            )

                            # 2. Periksa hasilnya dan catat di log
                            if is_placed:
                                self.log_update.emit(symbol, f"✅ BERHASIL: {result_message}")
                                self.last_trade_bar_time[symbol] = current_bar_time
                            else:
                                self.log_update.emit(symbol, f"❌ GAGAL: {result_message}")
                            self.last_trade_bar_time[symbol] = current_bar_time
                        else:
                            log_msg = message if message else "Lot size adalah 0 atau None."
                            self.log_update.emit(symbol, f"Order tidak ditempatkan. Alasan: {log_msg}")
            
            self.last_heartbeat = time.time()
            time.sleep(2) # Beri jeda 2 detik antar loop
        
        self.log_update.emit("Global", "⏹️ Worker telah dihentikan.")
        self.finished.emit()

    def stop(self):
        self.is_running = False

# --- KELAS GUI UTAMA (RobotApp) ---
# ... (sisa kode GUI Anda sama, tidak perlu diubah, kecuali fungsi toggle_engine)
class RobotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("7FX Automation Control Panel V3")
        self.setWindowIcon(qta.icon('fa5s.robot', color='white'))
        self.setGeometry(200, 200, 450, 500)
        
        self.is_connected = False
        self.worker_thread = None
        self.bot_worker = None
        self.accounts_data = load_accounts_data()
        self.available_symbols = []
        
        self.settings_window = None
        self.monitoring_window = MonitoringWindow(self)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        connection_group = QGroupBox("Koneksi Broker")
        self.create_koneksi_ui(connection_group)
        layout.addWidget(connection_group)
        
        control_group = QGroupBox("Panel Kontrol")
        control_layout = QVBoxLayout(control_group)
        layout.addWidget(control_group)

        self.btn_open_settings = QPushButton(qta.icon('fa5s.cogs'), " Buka Pengaturan Strategi")
        self.btn_open_settings.setEnabled(False)
        self.btn_open_settings.clicked.connect(self.open_settings)
        control_layout.addWidget(self.btn_open_settings)

        self.btn_show_monitor = QPushButton(qta.icon('fa5s.chart-line'), " Tampilkan Monitor Live")
        self.btn_show_monitor.setEnabled(False)
        self.btn_show_monitor.clicked.connect(self.show_monitoring_window)
        control_layout.addWidget(self.btn_show_monitor)

        self.btn_toggle_engine = QPushButton(qta.icon('fa5s.play'), " Start Engine")
        self.btn_toggle_engine.setEnabled(False)
        self.btn_toggle_engine.clicked.connect(self.toggle_engine)
        control_layout.addWidget(self.btn_toggle_engine)

        log_group = QGroupBox("Log Aktivitas Global")
        log_layout = QVBoxLayout(log_group)
        self.global_log_area = QTextEdit()
        self.global_log_area.setReadOnly(True)
        log_layout.addWidget(self.global_log_area)
        layout.addWidget(log_group)

        self.watchdog_timer = QTimer(self)
        self.watchdog_timer.setInterval(5000) # Cek setiap 20 detik
        self.watchdog_timer.timeout.connect(self.check_worker_health)
        
        self.update_dropdown_from_list(load_known_paths())
        if self.input_account.count() > 0:
            self.on_account_selected(self.input_account.currentText())

    def create_koneksi_ui(self, parent_groupbox):
        layout = QGridLayout(parent_groupbox)
        self.path_dropdown = QComboBox(); self.btn_scan = QPushButton("Scan"); self.btn_scan.clicked.connect(self.scan_paths)
        self.input_account = QComboBox(); self.input_account.setEditable(True); self.input_account.addItems(self.accounts_data.keys()); self.input_account.currentTextChanged.connect(self.on_account_selected)
        self.input_password = QLineEdit(); self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_pass_action = QAction(qta.icon('fa5s.eye', color='gray'), "Show/Hide", self); self.show_pass_action.triggered.connect(self.toggle_password_visibility)
        self.input_password.addAction(self.show_pass_action, QLineEdit.ActionPosition.TrailingPosition)
        self.input_server = QLineEdit(); self.input_save_pass = QCheckBox("Save Password")
        self.btn_connect = QPushButton("Connect"); self.btn_connect.clicked.connect(self.toggle_connection)
        layout.addWidget(QLabel("Path MT5:"), 0, 0); layout.addWidget(self.path_dropdown, 0, 1); layout.addWidget(self.btn_scan, 0, 2)
        layout.addWidget(QLabel("Nomor Akun:"), 1, 0); layout.addWidget(self.input_account, 1, 1, 1, 2)
        layout.addWidget(QLabel("Password:"), 2, 0); layout.addWidget(self.input_password, 2, 1, 1, 2)
        layout.addWidget(self.input_save_pass, 3, 1)
        layout.addWidget(QLabel("Server:"), 4, 0); layout.addWidget(self.input_server, 4, 1, 1, 2)
        layout.addWidget(self.btn_connect, 5, 0, 1, 3)

    def open_settings(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Belum Terhubung", "Harap hubungkan ke akun MT5 terlebih dahulu untuk memuat daftar simbol."); return
        if not self.settings_window or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow(self.available_symbols, self); self.settings_window.show()
        else:
            self.settings_window.activateWindow()

    def show_monitoring_window(self):
        if self.monitoring_window and self.worker_thread and self.worker_thread.isRunning():
            self.monitoring_window.show(); self.monitoring_window.activateWindow()
        else:
            QMessageBox.information(self, "Info", "Jendela monitor hanya tersedia saat engine sedang berjalan.")

    def handle_log_update(self, symbol: str, message: str):
        timestamp = f"[{time.strftime('%H:%M:%S')}]"
        if symbol == "Global":
            self.global_log_area.append(f"{timestamp} {message}"); self.global_log_area.verticalScrollBar().setValue(self.global_log_area.verticalScrollBar().maximum())
        else:
            if self.monitoring_window: self.monitoring_window.add_log(symbol, message)

    def on_account_selected(self, account_number: str):
        if account_number in self.accounts_data:
            data = self.accounts_data[account_number]
            self.input_server.setText(data.get("server", ""))
            try:
                password = keyring.get_password("7FX_HFT_Bot", account_number)
                if password: self.input_password.setText(password); self.input_save_pass.setChecked(True)
                else: self.input_password.clear(); self.input_save_pass.setChecked(False)
            except Exception as e:
                self.handle_log_update("Global", f"Info: Gagal mengambil password. {e}"); self.input_password.clear(); self.input_save_pass.setChecked(False)

    def toggle_password_visibility(self):
        if self.input_password.echoMode() == QLineEdit.EchoMode.Password:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Normal); self.show_pass_action.setIcon(qta.icon('fa5s.eye-slash', color='gray'))
        else:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password); self.show_pass_action.setIcon(qta.icon('fa5s.eye', color='gray'))

    def populate_symbols(self):
        self.handle_log_update("Global", "Memuat daftar simbol dari broker...")
        try:
            symbols = mt5.symbols_get()
            if symbols:
                self.available_symbols = sorted([s.name for s in symbols])
                self.handle_log_update("Global", f"✅ Berhasil memuat {len(self.available_symbols)} simbol."); self.btn_open_settings.setEnabled(True)
            else:
                self.handle_log_update("Global", "❌ Gagal mendapatkan daftar simbol.")
        except Exception as e:
            self.handle_log_update("Global", f"❌ Error saat mengambil simbol: {e}")
            
    def update_dropdown_from_list(self, paths: set):
        self.path_dropdown.clear()
        if paths:
            for path in sorted(list(paths)): self.path_dropdown.addItem(os.path.basename(os.path.dirname(path)), userData=path)
        else:
            self.handle_log_update("Global", "Tidak ada path MT5 tersimpan. Coba lakukan Scan.")

    def scan_paths(self):
        self.handle_log_update("Global", "Memulai Quick Scan..."); QApplication.processEvents()
        current_paths = load_known_paths(); paths_registry = scan_for_metatrader_enhanced(); paths_smart = find_by_smart_search()
        newly_found_paths = current_paths | paths_registry | paths_smart
        if len(newly_found_paths) > len(current_paths):
            self.handle_log_update("Global", "✅ Ditemukan path baru! Daftar diperbarui."); self.update_dropdown_from_list(newly_found_paths); save_known_paths(newly_found_paths)
        else:
            self.handle_log_update("Global", "Tidak ada path baru ditemukan dari Quick Scan.")
            if QMessageBox.question(self, 'Scan Cepat Selesai', "Lanjutkan dengan DEEP SCAN? (lambat)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: self.perform_deep_scan()

    def perform_deep_scan(self):
        self.handle_log_update("Global", "Memulai Deep Scan... Harap tunggu."); QApplication.processEvents()
        current_paths = load_known_paths(); paths_deep = find_by_searching_disk()
        newly_found_paths = current_paths | paths_deep
        if len(newly_found_paths) > len(current_paths):
            self.handle_log_update("Global", "✅ Ditemukan path baru dari Deep Scan!"); self.update_dropdown_from_list(newly_found_paths); save_known_paths(newly_found_paths)
        else:
            self.handle_log_update("Global", "Deep Scan selesai. Tidak ada instalasi baru ditemukan.")

    def toggle_connection(self):
        if self.is_connected:
            if self.worker_thread and self.worker_thread.isRunning(): QMessageBox.warning(self, "Proses Berjalan", "Hentikan engine terlebih dahulu."); return
            shutdown_connection(); self.is_connected = False
            self.handle_log_update("Global", "🔌 Koneksi diputus."); self.btn_connect.setText("Connect")
            self.btn_toggle_engine.setEnabled(False); self.btn_open_settings.setEnabled(False); self.available_symbols.clear()
            for widget in [self.input_account, self.input_password, self.input_server, self.path_dropdown, self.input_save_pass]: widget.setEnabled(True)
        else:
            path = self.path_dropdown.currentData(); acc = self.input_account.currentText()
            pwd = self.input_password.text(); srv = self.input_server.text()
            if not all([path, acc, pwd, srv]): QMessageBox.warning(self, "Input Error", "Semua field koneksi harus diisi."); return
            is_ok, msg = connect_to_mt5(acc, pwd, srv, path); self.handle_log_update("Global", msg)
            if is_ok:
                self.is_connected = True; self.btn_connect.setText("Disconnect"); self.btn_toggle_engine.setEnabled(True)
                for widget in [self.input_account, self.input_password, self.input_server, self.path_dropdown, self.input_save_pass]: widget.setEnabled(False)
                self.accounts_data[acc] = {"server": srv}; save_accounts_data(self.accounts_data)
                if self.input_save_pass.isChecked(): keyring.set_password("7FX_HFT_Bot", acc, pwd)
                else:
                    try: keyring.delete_password("7FX_HFT_Bot", acc)
                    except keyring.errors.PasswordDeleteError: pass
                self.populate_symbols()

    def check_worker_health(self):
        if self.worker_thread and self.worker_thread.isRunning() and self.bot_worker:
            time_since_last_heartbeat = time.time() - self.bot_worker.last_heartbeat
            if time_since_last_heartbeat > 30:
                self.handle_log_update("Global", "⚠️ WARNING: Worker terdeteksi macet! Mencoba me-restart...")
                self.bot_worker.stop()
                self.worker_thread.quit()
                self.worker_thread.wait(2000)
                self.toggle_engine() # Coba restart engine lama
                time.sleep(1)
                self.toggle_engine() # Mulai engine baru


    def toggle_engine(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.bot_worker.stop()
            self.watchdog_timer.stop()
            self.btn_toggle_engine.setText("Stopping...")
            self.btn_toggle_engine.setEnabled(False)
            self.handle_log_update("Global", "Mengirim sinyal stop ke worker...")
        else:
            if not self.settings_window: 
                QMessageBox.warning(self, "Pengaturan Kosong", "Buka jendela pengaturan dan tambahkan setidaknya satu pair.")
                return
            all_configs = self.settings_window.get_all_configs()
            if not all_configs: 
                QMessageBox.warning(self, "Pengaturan Kosong", "Tidak ada pair yang dikonfigurasi untuk dijalankan.")
                return

            try:
                account_info = mt5.account_info()
                if not account_info:
                    self.handle_log_update("Global", "❌ ERROR: Tidak bisa mendapatkan info akun. Cek koneksi.")
                    return
                current_balance = account_info.balance
                self.handle_log_update("Global", f"Saldo akun saat ini: {current_balance:.2f}")

                for config in all_configs:
                    config['balance'] = current_balance
            except Exception as e:
                self.handle_log_update("Global", f"❌ FATAL: Gagal mengambil saldo akun: {e}")
                return

            self.monitoring_window.clear_all()
            self.monitoring_window.show()
            self.btn_show_monitor.setEnabled(True)

            self.worker_thread = QThread()
            self.bot_worker = BotWorker(all_configs)
            self.bot_worker.moveToThread(self.worker_thread)

            self.worker_thread.started.connect(self.bot_worker.run)
            self.bot_worker.finished.connect(self.on_worker_finished)
            self.bot_worker.log_update.connect(self.handle_log_update)
            self.bot_worker.status_update.connect(self.monitoring_window.update_pair_data)

            self.worker_thread.start()
            self.watchdog_timer.start()
            self.btn_toggle_engine.setText("Stop Engine")
            self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop'))
            self.btn_open_settings.setEnabled(False)

    def on_worker_finished(self):
        self.watchdog_timer.stop()
        self.btn_toggle_engine.setText("Start Engine"); self.btn_toggle_engine.setIcon(qta.icon('fa5s.play'))
        self.btn_toggle_engine.setEnabled(True); self.btn_open_settings.setEnabled(True); self.btn_show_monitor.setEnabled(False)
        self.handle_log_update("Global", "Thread worker telah berhenti sepenuhnya.")
        self.monitoring_window.clear_all()
        if self.worker_thread:
            self.worker_thread.quit(); self.worker_thread.wait()
        self.worker_thread = None; self.bot_worker = None
        
    def closeEvent(self, event):
        self.watchdog_timer.stop()
        self.monitoring_window.close()
        if self.settings_window: self.settings_window.save_configs(); self.settings_window.close()
        if self.worker_thread and self.worker_thread.isRunning(): self.bot_worker.stop()
        shutdown_connection(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RobotApp()
    window.show()
    sys.exit(app.exec())