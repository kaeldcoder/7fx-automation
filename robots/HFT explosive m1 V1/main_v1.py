# D:\7FX Automation\robots\HFT explosive m1\main_gui.py

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
from Library.technical_analysis.trend.ema_trend_V1 import check_new_strategy_v1
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
        
        # [FIX] State management untuk mengurangi spam log
        self.last_known_conditions = {} 
        self.placed_orders_cache = {}
        self.last_heartbeat = time.time()
        self.symbol_error_counts = {config['symbol']: 0 for config in self.configs}

    def run(self):
        self.log_update.emit("Global", f"✅ Worker dimulai. Memantau {len(self.configs)} pair...")
        
        while self.is_running:
            current_time = time.time()
            for config in self.configs:
                if not self.is_running: break
                
                symbol = config['symbol']
                
                # [FIX] Struktur loop yang lebih aman untuk mencegah crash
                try:
                    # 1. Analisis pasar & ambil status
                    market_status = check_new_strategy_v1(symbol, config) # atau v2 jika Anda sudah ganti nama
                    
                    if not market_status:
                        # Gagal mendapatkan status, lanjut ke simbol berikutnya
                        if self.symbol_error_counts.get(symbol, 0) < 5:
                           self.symbol_error_counts[symbol] = self.symbol_error_counts.get(symbol, 0) + 1
                           self.log_update.emit(symbol, f"WARNING: Gagal mengambil data untuk {symbol}. (Percobaan {self.symbol_error_counts[symbol]})")
                        continue
                    
                    # Reset error count jika berhasil
                    self.symbol_error_counts[symbol] = 0

                    # 2. Kirim pembaruan ke UI (selalu dikirim agar live)
                    self.status_update.emit(market_status)

                    # 3. Logika untuk mengurangi spam di terminal
                    new_condition = market_status.get("condition")
                    last_condition = self.last_known_conditions.get(symbol)
                    
                    if new_condition != last_condition:
                        self.log_update.emit(symbol, f"Status berubah: {new_condition}")
                        self.last_known_conditions[symbol] = new_condition

                    # 4. Proses sinyal perdagangan jika ada
                    trade_signal_data = market_status.get("trade_signal")
                    if trade_signal_data:
                        entry_price = trade_signal_data['entry']
                        order_key = f"{symbol}_{entry_price}"

                        # Cek cache order agar tidak spam order yang sama
                        if order_key in self.placed_orders_cache and (current_time - self.placed_orders_cache[order_key] < 120):
                            continue

                        sl_level = trade_signal_data['sl']
                        tp_level = trade_signal_data['tp']

                        # Kalkulasi lot size terlebih dahulu
                        lot_size, msg = calculate_lot_size(config['risk_per_trade'], entry_price, sl_level, symbol)

                        # Hanya jika lot size valid, baru kita log sinyal dan tempatkan order
                        if lot_size:
                            # Pindahkan log sinyal ke sini
                            signal_type_str = trade_signal_data['signal']
                            self.log_update.emit(symbol, f"🔥🔥🔥 SINYAL TERDETEKSI: {signal_type_str}.")

                            order_type = mt5.ORDER_TYPE_BUY_STOP if "BUY" in signal_type_str else mt5.ORDER_TYPE_SELL_STOP
                            is_placed, exec_message = place_pending_order(symbol, order_type, lot_size, entry_price, sl_level, tp_level, config['magic_number'])

                            if is_placed:
                                self.placed_orders_cache[order_key] = current_time
                                log_message = (f"✅ ORDER DITEMPATKAN: Lot {lot_size}.\n" f"  ├─ Entry: {entry_price:.5f} SL: {sl_level:.5f} TP: {tp_level:.5f}")
                                self.log_update.emit(symbol, log_message)
                        else:
                            # Jika lot size tidak valid (misal, SL terlalu dekat), log peringatan saja
                            self.log_update.emit(symbol, f"Peringatan: {msg}. Sinyal valid tapi order tidak ditempatkan.")
                
                except Exception as e:
                    self.log_update.emit(symbol, f"❌ ERROR tak terduga di loop utama: {e}")

            self.last_heartbeat = current_time
            # Loop tunggu
            for _ in range(5): # Interval diperpanjang sedikit untuk mengurangi beban
                if not self.is_running: break
                time.sleep(1)
        
        self.log_update.emit("Global", "⏹️ Worker telah dihentikan.")
        self.finished.emit()

    def stop(self):
        self.is_running = False

class RobotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("7FX Automation Control Panel V1")
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
        """Fungsi yang dipanggil oleh timer untuk mengecek apakah worker macet."""
        if self.worker_thread and self.worker_thread.isRunning() and self.bot_worker:
            time_since_last_heartbeat = time.time() - self.bot_worker.last_heartbeat
            
            # Jika worker tidak memberi kabar selama lebih dari 30 detik, anggap macet
            if time_since_last_heartbeat > 30:
                self.handle_log_update("Global", "⚠️ WARNING: Worker terdeteksi macet! Mencoba me-restart engine...")
                
                # Hentikan paksa thread yang lama
                if self.worker_thread.isRunning():
                    self.bot_worker.stop()
                    self.worker_thread.quit()
                    self.worker_thread.wait(2000) # Tunggu 2 detik
                
                # Mulai engine baru
                self.toggle_engine()

    def toggle_engine(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.bot_worker.stop()
            self.watchdog_timer.stop()
            self.btn_toggle_engine.setText("Stopping...")
            self.btn_toggle_engine.setEnabled(False)
            self.handle_log_update("Global", "Mengirim sinyal stop ke worker...")
        else:
            if not self.settings_window: QMessageBox.warning(self, "Pengaturan Kosong", "Buka jendela pengaturan dan tambahkan setidaknya satu pair."); return
            all_configs = self.settings_window.get_all_configs()
            if not all_configs: return
            self.monitoring_window.clear_all(); self.monitoring_window.show(); self.btn_show_monitor.setEnabled(True)
            self.worker_thread = QThread(); self.bot_worker = BotWorker(all_configs)
            self.bot_worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.bot_worker.run)
            self.bot_worker.finished.connect(self.on_worker_finished)
            self.bot_worker.log_update.connect(self.handle_log_update)
            # [PERBAIKAN] Koneksi sinyal yang benar
            self.bot_worker.status_update.connect(self.monitoring_window.update_pair_data)
            self.worker_thread.start()
            self.watchdog_timer.start()
            self.btn_toggle_engine.setText("Stop Engine"); self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop'))
            self.btn_open_settings.setEnabled(False)

    def on_worker_finished(self):
        self.watchdog_timer.stop()
        self.btn_toggle_engine.setText("Start Engine"); self.btn_toggle_engine.setIcon(qta.icon('fa5s.play'))
        self.btn_toggle_engine.setEnabled(True); self.btn_open_settings.setEnabled(True); self.btn_show_monitor.setEnabled(False)
        self.handle_log_update("Global", "Thread worker telah berhenti sepenuhnya.")
        # [PERBAIKAN] Tambahkan reset monitor
        self.monitoring_window.clear_all()
        if self.worker_thread:
            self.worker_thread.quit(); self.worker_thread.wait()
        self.worker_thread = None; self.bot_worker = None
        
    def closeEvent(self, event):
        self.watchdog_timer.stop()
        self.monitoring_window.close()
        if self.settings_window: self.settings_window.save_all_configs(show_message=False); self.settings_window.close()
        if self.worker_thread and self.worker_thread.isRunning(): self.bot_worker.stop()
        shutdown_connection(); event.accept()

# --- BLOK EKSEKUSI UTAMA ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Stylesheet bisa ditambahkan di sini jika perlu
    window = RobotApp()
    window.show()
    sys.exit(app.exec())