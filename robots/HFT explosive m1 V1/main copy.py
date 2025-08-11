# D:\7FX Automation\robots\HFT explosive m1\main_gui.py

import sys
import os
import time
import keyring

# --- Konfigurasi Path ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# --- Impor Pustaka GUI dan Bot ---
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit, 
                             QComboBox, QDoubleSpinBox, QSpinBox, QMessageBox, QCheckBox, 
                             QCompleter, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
                             QDialog)
from PyQt6.QtCore import QThread, QObject, pyqtSignal, Qt, QSize
from PyQt6.QtGui import QAction, QColor, QIcon
import qtawesome as qta

# Impor semua modul dari Library kita
from Library.utils.path_finder import (load_known_paths, save_known_paths, load_accounts_data, save_accounts_data,
                                       scan_for_metatrader_enhanced, find_by_smart_search, find_by_searching_disk)
from Library.broker_interface.mt5_connector import connect_to_mt5, shutdown_connection
from Library.technical_analysis.trend.ema_trend import check_ema_trend
from Library.risk_management.position_sizer import calculate_lot_size
from Library.broker_interface.mt5_executor import execute_market_order
import MetaTrader5 as mt5

# --- [UPGRADE] Stylesheet Global untuk Tampilan Futuristik ---
QSS_STYLE = """
    #MainWindow {
        background-color: #1e2228;
        border-radius: 10px;
    }
    #TitleBar {
        background-color: #282c34;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
    }
    #Sidebar {
        background-color: #282c34;
        border-right: 1px solid #3d424b;
    }
    #ContentArea {
        background-color: #1e2228;
    }
    QLabel {
        color: #abb2bf;
        font-weight: bold;
    }
    QGroupBox {
        color: #00aaff;
        font-weight: bold;
        border: 1px solid #3d424b;
        border-radius: 5px;
        margin-top: 1ex;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center;
        padding: 0 10px;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        color: #e6e6e6;
        background-color: #21252b;
        border: 1px solid #3d424b;
        border-radius: 4px;
        padding: 6px;
    }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
        border-color: #00aaff;
    }
    QPushButton {
        color: white;
        background-color: #007acc;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #008ae6;
    }
    QPushButton:pressed {
        background-color: #006bb3;
    }
    QPushButton:disabled {
        background-color: #3d424b;
        color: #7f8c8d;
    }
    #ScanButton {
        padding: 6px 10px;
    }
    #ControlButton {
        background-color: transparent;
        border: none;
    }
    #ControlButton:hover {
        background-color: #3d424b;
    }
    #PowerButton {
        border-radius: 40px; /* Membuat tombol lingkaran */
        min-width: 80px;
        max-width: 80px;
        min-height: 80px;
        max-height: 80px;
    }
    #PowerButton_On {
        background-color: #c0392b;
    }
    #PowerButton_On:hover {
        background-color: #e74c3c;
    }
    #PowerButton_Off {
        background-color: #27ae60;
    }
    #PowerButton_Off:hover {
        background-color: #2ecc71;
    }
    QTabWidget::pane {
        border: none;
    }
    QTabBar::tab {
        background: #282c34;
        color: #abb2bf;
        padding: 10px 20px;
        border: 1px solid #282c34;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        font-weight: bold;
    }
    QTabBar::tab:selected {
        background: #1e2228;
        border-color: #3d424b;
    }
    QTabBar::tab:!selected:hover {
        background: #3d424b;
    }
    QTableWidget {
        background-color: #21252b;
        color: #abb2bf;
        gridline-color: #3d424b;
        border: 1px solid #3d424b;
        border-radius: 5px;
    }
    QHeaderView::section {
        background-color: #282c34;
        color: #00aaff;
        padding: 6px;
        border: 1px solid #3d424b;
        font-weight: bold;
    }
"""

class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("TitleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon('fa5s.robot', color='#00aaff').pixmap(QSize(16, 16)))
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        title_label = QLabel("7FX Automation Control Panel")
        title_label.setStyleSheet("font-weight: bold; color: #abb2bf; margin-left: 5px;")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        self.btn_minimize = QPushButton(qta.icon('fa5.window-minimize', color='#abb2bf'), "")
        self.btn_minimize.setObjectName("ControlButton")
        self.btn_minimize.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.btn_minimize)

        self.btn_close = QPushButton(qta.icon('fa5s.times', color='#abb2bf'), "")
        self.btn_close.setObjectName("ControlButton")
        self.btn_close.clicked.connect(self.parent.close)
        layout.addWidget(self.btn_close)

    def mousePressEvent(self, event):
        self.parent.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.parent.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.parent.mouseReleaseEvent(event)


# --- [BARU] Jendela Khusus untuk Logging ---
class LogWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Aktivitas Bot")
        self.setWindowIcon(qta.icon('fa5s.terminal', color='white'))
        self.setGeometry(900, 200, 600, 500)
        
        self.log_tabs = QTabWidget()
        self.log_widgets = {} # Mapping: symbol -> QTextEdit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.addWidget(self.log_tabs)
        self.setStyleSheet("background-color: #1e2228;")

    def add_log(self, symbol, message):
        if symbol not in self.log_widgets:
            new_log_area = QTextEdit()
            new_log_area.setReadOnly(True)
            new_log_area.setStyleSheet("background-color: #21252b; color: #abb2bf; border: 1px solid #3d424b;")
            self.log_widgets[symbol] = new_log_area
            self.log_tabs.addTab(new_log_area, symbol)
        
        timestamp = time.strftime('%H:%M:%S')
        self.log_widgets[symbol].append(f"[{timestamp}] {message}")
        self.log_widgets[symbol].verticalScrollBar().setValue(self.log_widgets[symbol].verticalScrollBar().maximum())


    def clear_logs(self):
        for log_widget in self.log_widgets.values():
            log_widget.clear()
        self.log_widgets.clear()
        self.log_tabs.clear()

# --- Widget Kustom untuk Pengaturan per Pair ---
class StrategyTab(QWidget):
    def __init__(self, available_symbols: list, initial_magic: int):
        super().__init__()
        layout = QGridLayout(self)
        layout.setColumnStretch(1, 2)

        # Simbol
        layout.addWidget(QLabel("Simbol:"), 0, 0)
        self.input_symbol = QComboBox()
        self.input_symbol.setEditable(True)
        self.input_symbol.addItems(available_symbols)
        completer = QCompleter(available_symbols)
        self.input_symbol.setCompleter(completer)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        layout.addWidget(self.input_symbol, 0, 1)

        # Timeframe
        layout.addWidget(QLabel("Timeframe:"), 1, 0)
        self.input_timeframe = QComboBox()
        self.timeframe_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4
        }
        self.input_timeframe.addItems(self.timeframe_map.keys())
        self.input_timeframe.setCurrentText("M1")
        layout.addWidget(self.input_timeframe, 1, 1)

        # EMA Period
        layout.addWidget(QLabel("EMA Period:"), 2, 0)
        self.input_ema = QSpinBox()
        self.input_ema.setRange(10, 200); self.input_ema.setValue(50)
        layout.addWidget(self.input_ema, 2, 1)

        # Risk/Trade (%)
        layout.addWidget(QLabel("Risk/Trade (%):"), 3, 0)
        self.input_risk = QDoubleSpinBox()
        self.input_risk.setRange(0.1, 5.0); self.input_risk.setSingleStep(0.1); self.input_risk.setValue(1.0)
        layout.addWidget(self.input_risk, 3, 1)

        # Risk:Reward Ratio
        layout.addWidget(QLabel("Risk:Reward Ratio:"), 4, 0)
        self.input_rr = QDoubleSpinBox()
        self.input_rr.setRange(0.5, 10.0); self.input_rr.setSingleStep(0.1); self.input_rr.setValue(1.5)
        layout.addWidget(self.input_rr, 4, 1)

        # SL Lookback Period
        layout.addWidget(QLabel("SL Lookback Period:"), 5, 0)
        self.input_sl_lookback = QSpinBox()
        self.input_sl_lookback.setRange(1, 10); self.input_sl_lookback.setValue(3)
        layout.addWidget(self.input_sl_lookback, 5, 1)
        
        # Magic Number
        layout.addWidget(QLabel("Magic Number:"), 6, 0)
        self.input_magic = QLineEdit(str(initial_magic))
        layout.addWidget(self.input_magic, 6, 1)

    def get_config(self) -> dict:
        try:
            magic_number = int(self.input_magic.text())
        except (ValueError, TypeError):
            magic_number = 0

        return {
            'symbol': self.input_symbol.currentText(),
            'timeframe_str': self.input_timeframe.currentText(),
            'timeframe': self.timeframe_map[self.input_timeframe.currentText()],
            'ema_period': self.input_ema.value(),
            'rr_ratio': self.input_rr.value(),
            'risk_per_trade': self.input_risk.value(),
            'magic_number': magic_number,
            'sl_lookback': self.input_sl_lookback.value()
        }

class BotWorker(QObject):
    finished = pyqtSignal()
    log_update = pyqtSignal(str, str) # Diubah: (symbol, message)
    status_update = pyqtSignal(dict)

    def __init__(self, configs: list):
        super().__init__()
        self.configs = configs
        self.is_running = True

    def run(self):
        self.log_update.emit("Global", f"✅ Worker dimulai. Memantau {len(self.configs)} pair...")
        
        while self.is_running:
            for config in self.configs:
                if not self.is_running: break
                
                symbol = config['symbol']
                
                market_status = check_ema_trend(
                    symbol, 
                    config['timeframe'], 
                    ema_length=config['ema_period'], 
                    rr_ratio=config['rr_ratio'],
                    sl_lookback=config['sl_lookback']
                )
                
                if market_status:
                    market_status['symbol'] = symbol
                    self.status_update.emit(market_status)

                trade_signal_data = market_status.get("trade_signal") if market_status else None
                
                if trade_signal_data:
                    self.log_update.emit(symbol, f"🔥🔥🔥 SINYAL: {trade_signal_data['signal']}.")
                    
                    order_type_str = trade_signal_data['signal']
                    entry_price = trade_signal_data['entry']
                    sl_level = trade_signal_data['sl']
                    tp_level = trade_signal_data['tp']
                    
                    order_type = mt5.ORDER_TYPE_BUY_STOP if "BUY" in order_type_str else mt5.ORDER_TYPE_SELL_STOP
                    
                    lot_size, msg = calculate_lot_size(config['risk_per_trade'], entry_price, sl_level, symbol)
                    
                    if lot_size:
                        self.log_update.emit(symbol, f"Lot: {lot_size}. Menempatkan Pending Order...")
                        execute_market_order(symbol, order_type, lot_size, entry_price, sl_level, tp_level, config['magic_number'])
                    else:
                        self.log_update.emit(symbol, f"Peringatan: {msg}. Order tidak ditempatkan.")

            # Tunggu sebelum memulai siklus pengecekan berikutnya
            for _ in range(5):
                if not self.is_running: break
                time.sleep(1)
        
        self.log_update.emit("Global", "⏹️ Worker telah dihentikan.")
        self.finished.emit()

    def stop(self):
        self.is_running = False

# --- Kelas Utama untuk Aplikasi GUI ---
class RobotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Membuat jendela tanpa bingkai standar Windows
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("MainWindow")
        self.setGeometry(200, 200, 950, 700)
        
        # Inisialisasi variabel internal
        self._old_pos = None
        self.is_connected = False
        self.worker_thread = None
        self.bot_worker = None
        self.accounts_data = load_accounts_data()
        self.available_symbols = []
        self.base_magic_number = 12345
        self.symbol_row_map = {}
        self.log_window = LogWindow(self)

        # --- Wadah Utama ---
        main_container = QWidget()
        self.setCentralWidget(main_container)
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Title Bar Kustom
        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        # 2. Area Konten Utama
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        main_layout.addWidget(content_widget)

        # --- Splitter untuk memisahkan Sidebar dan Area Konten ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_layout.addWidget(main_splitter)
        
        # 3. Sidebar (Panel Kiri)
        sidebar_widget = QWidget()
        sidebar_widget.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        main_splitter.addWidget(sidebar_widget)
        
        connection_group = QGroupBox("KONEKSI & KONTROL")
        self.create_koneksi_ui(connection_group)
        sidebar_layout.addWidget(connection_group)
        sidebar_layout.addStretch()

        # Tombol Start/Stop Utama
        power_button_layout = QHBoxLayout()
        power_button_layout.addStretch()
        self.btn_toggle_engine = QPushButton()
        self.btn_toggle_engine.setObjectName("PowerButton")
        self.btn_toggle_engine.clicked.connect(self.toggle_engine)
        self.update_power_button_ui(is_running=False) # Set tampilan awal
        power_button_layout.addWidget(self.btn_toggle_engine)
        power_button_layout.addStretch()
        sidebar_layout.addLayout(power_button_layout)
        sidebar_layout.addStretch()

        # 4. Konten Utama (Panel Kanan)
        main_content_widget = QWidget()
        main_content_widget.setObjectName("ContentArea")
        main_content_layout = QVBoxLayout(main_content_widget)
        main_content_layout.setContentsMargins(10, 10, 10, 10)
        main_splitter.addWidget(main_content_widget)

        # Splitter vertikal untuk memisahkan tab strategi dan status
        content_splitter = QSplitter(Qt.Orientation.Vertical)
        main_content_layout.addWidget(content_splitter)

        # Wadah untuk tab-tab strategi
        self.strategy_tabs = QTabWidget()
        self.strategy_tabs.setTabsClosable(True)
        self.strategy_tabs.tabCloseRequested.connect(self.remove_strategy_tab)
        self.btn_add_pair = QPushButton(qta.icon('fa5s.plus'), " Add Pair")
        self.btn_add_pair.clicked.connect(self.add_strategy_tab)
        self.btn_add_pair.setEnabled(False)
        self.strategy_tabs.setCornerWidget(self.btn_add_pair, Qt.Corner.TopLeftCorner)
        content_splitter.addWidget(self.strategy_tabs)

        # Wadah untuk tabel status
        status_container = QWidget()
        status_layout = QVBoxLayout(status_container)
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(4)
        self.status_table.setHorizontalHeaderLabels(["Pair", "Harga", "Kondisi Pasar", "Info Tambahan"])
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        status_layout.addWidget(QLabel("<b>LIVE MARKET STATUS</b>"))
        status_layout.addWidget(self.status_table)
        content_splitter.addWidget(status_container)
        
        # Atur ukuran awal splitter
        main_splitter.setSizes([350, 600])
        content_splitter.setSizes([400, 250])

        # Inisialisasi Data Awal
        self.update_dropdown_from_list(load_known_paths())
        if self.input_account.count() > 0:
            self.on_account_selected(self.input_account.currentText())
    
    # --- FUNGSI UNTUK MEMBUAT UI DI DALAM SIDEBAR ---
    def create_koneksi_ui(self, parent_groupbox):
        layout = QGridLayout(parent_groupbox)
        
        self.path_dropdown = QComboBox(); self.btn_scan = QPushButton("Scan"); self.btn_scan.setObjectName("ScanButton")
        self.btn_scan.clicked.connect(self.scan_paths)
        self.input_account = QComboBox(); self.input_account.setEditable(True)
        self.input_account.addItems(self.accounts_data.keys()); self.input_account.currentTextChanged.connect(self.on_account_selected)
        self.input_password = QLineEdit(); self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_pass_action = QAction(qta.icon('fa5s.eye', color='gray'), "Show/Hide", self)
        self.show_pass_action.triggered.connect(self.toggle_password_visibility)
        self.input_password.addAction(self.show_pass_action, QLineEdit.ActionPosition.TrailingPosition)
        self.input_server = QLineEdit(); self.input_save_pass = QCheckBox("Save Password")
        self.btn_connect = QPushButton("Connect"); self.btn_connect.clicked.connect(self.toggle_connection)
        
        layout.addWidget(QLabel("Path MT5:"), 0, 0); layout.addWidget(self.path_dropdown, 0, 1); layout.addWidget(self.btn_scan, 0, 2)
        layout.addWidget(QLabel("Nomor Akun:"), 1, 0); layout.addWidget(self.input_account, 1, 1, 1, 2)
        layout.addWidget(QLabel("Password:"), 2, 0); layout.addWidget(self.input_password, 2, 1, 1, 2)
        layout.addWidget(self.input_save_pass, 3, 1)
        layout.addWidget(QLabel("Server:"), 4, 0); layout.addWidget(self.input_server, 4, 1, 1, 2)
        layout.addWidget(self.btn_connect, 5, 0, 1, 3)

    # --- FUNGSI UNTUK MEMBUAT JENDELA BISA DIGESER ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._old_pos is not None:
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._old_pos = None

    # --- FUNGSI-FUNGSI LOGIKA (SLOTS) ---

    def update_power_button_ui(self, is_running: bool):
        """Memperbarui tampilan tombol power utama."""
        if is_running:
            self.btn_toggle_engine.setIcon(qta.icon('fa5s.stop', color='white', scale_factor=1.5))
            self.btn_toggle_engine.setToolTip("Stop Engine")
            # Nama objek diubah untuk menerapkan style QSS yang berbeda
            self.btn_toggle_engine.setObjectName("PowerButton_On") 
        else:
            self.btn_toggle_engine.setIcon(qta.icon('fa5s.play', color='white', scale_factor=1.5))
            self.btn_toggle_engine.setToolTip("Start Engine")
            self.btn_toggle_engine.setObjectName("PowerButton_Off")
        
        # Terapkan ulang style agar perubahan nama objek terbaca
        self.btn_toggle_engine.style().unpolish(self.btn_toggle_engine)
        self.btn_toggle_engine.style().polish(self.btn_toggle_engine)
    
    def add_strategy_tab(self):
        """Membuat dan menambahkan tab strategi baru."""
        new_magic = self.base_magic_number + self.strategy_tabs.count()
        new_tab = StrategyTab(self.available_symbols, new_magic)
        index = self.strategy_tabs.addTab(new_tab, f"Pair {self.strategy_tabs.count() + 1}")
        self.strategy_tabs.setCurrentIndex(index)

    def remove_strategy_tab(self, index: int):
        """Menghapus tab strategi saat ikon 'x' diklik."""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Aksi Ditolak", "Harap hentikan engine terlebih dahulu sebelum mengubah tab.")
            return
        if self.strategy_tabs.count() > 1:
            self.strategy_tabs.removeTab(index)
        else:
            QMessageBox.warning(self, "Aksi Ditolak", "Setidaknya harus ada satu tab strategi.")

    def on_account_selected(self, account_number: str):
        """Otomatis mengisi server dan password saat akun dipilih."""
        if account_number in self.accounts_data:
            data = self.accounts_data[account_number]
            self.input_server.setText(data.get("server", ""))
            try:
                password = keyring.get_password("7FX_HFT_Bot", account_number)
                if password:
                    self.input_password.setText(password)
                    self.input_save_pass.setChecked(True)
                else:
                    self.input_password.clear(); self.input_save_pass.setChecked(False)
            except Exception:
                self.input_password.clear(); self.input_save_pass.setChecked(False)

    def toggle_password_visibility(self):
        """Mengubah visibilitas password di input field."""
        if self.input_password.echoMode() == QLineEdit.EchoMode.Password:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Normal)
            self.show_pass_action.setIcon(qta.icon('fa5s.eye-slash', color='#abb2bf'))
        else:
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_pass_action.setIcon(qta.icon('fa5s.eye', color='#abb2bf'))

    def populate_symbols(self):
        """Meminta daftar simbol dari broker dan mengisinya ke UI."""
        self.log_window.add_log("Global", "Memuat daftar simbol dari broker...")
        try:
            symbols = mt5.symbols_get()
            if symbols:
                self.available_symbols = sorted([s.name for s in symbols])
                self.log_window.add_log("Global", f"✅ Berhasil memuat {len(self.available_symbols)} simbol.")
                self.btn_add_pair.setEnabled(True)
                if self.strategy_tabs.count() == 0: self.add_strategy_tab()
            else:
                self.log_window.add_log("Global", "❌ Gagal mendapatkan daftar simbol.")
        except Exception as e:
            self.log_window.add_log("Global", f"❌ Error saat mengambil simbol: {e}")
            
    def update_dropdown_from_list(self, paths: set):
        self.path_dropdown.clear()
        if paths:
            for path in sorted(list(paths)):
                friendly_name = os.path.basename(os.path.dirname(path))
                self.path_dropdown.addItem(f"{friendly_name}", userData=path)

    def scan_paths(self):
        """Menjalankan Quick Scan untuk path MT5."""
        self.log_window.add_log("Global", "Memulai Quick Scan...")
        QApplication.processEvents()
        current_paths = load_known_paths()
        paths_registry = scan_for_metatrader_enhanced()
        paths_smart = find_by_smart_search()
        newly_found_paths = current_paths | paths_registry | paths_smart
        if len(newly_found_paths) > len(current_paths):
            self.log_window.add_log("Global", "✅ Ditemukan path baru! Daftar diperbarui.")
            self.update_dropdown_from_list(newly_found_paths)
            save_known_paths(newly_found_paths)
        else:
            self.log_window.add_log("Global", "Tidak ada path baru ditemukan dari Quick Scan.")
            reply = QMessageBox.question(self, 'Scan Cepat Selesai', 
                                         "Tidak ditemukan instalasi baru.\n\nApakah Anda ingin menjalankan DEEP SCAN? (proses ini bisa lambat)",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes: self.perform_deep_scan()

    def perform_deep_scan(self):
        self.log_window.add_log("Global", "Memulai Deep Scan... Harap tunggu.")
        QApplication.processEvents()
        current_paths = load_known_paths()
        paths_deep = find_by_searching_disk()
        newly_found_paths = current_paths | paths_deep
        if len(newly_found_paths) > len(current_paths):
            self.log_window.add_log("Global", "✅ Ditemukan path baru dari Deep Scan!")
            self.update_dropdown_from_list(newly_found_paths)
            save_known_paths(newly_found_paths)
        else:
            self.log_window.add_log("Global", "Deep Scan selesai. Tidak ada instalasi baru ditemukan.")

    def toggle_connection(self):
        """Menangani logika saat tombol Connect/Disconnect diklik."""
        if self.is_connected:
            if self.worker_thread and self.worker_thread.isRunning():
                QMessageBox.warning(self, "Proses Berjalan", "Hentikan engine terlebih dahulu."); return
            shutdown_connection()
            self.is_connected = False; self.log_window.add_log("Global", "🔌 Koneksi diputus.")
            self.btn_connect.setText("Connect"); self.btn_toggle_engine.setEnabled(False); self.btn_add_pair.setEnabled(False)
            self.available_symbols.clear()
            for i in [self.input_account, self.input_password, self.input_server, self.path_dropdown, self.input_save_pass]: i.setEnabled(True)
        else:
            path = self.path_dropdown.currentData(); acc = self.input_account.currentText()
            pwd = self.input_password.text(); srv = self.input_server.text()
            if not all([path, acc, pwd, srv]):
                QMessageBox.warning(self, "Input Error", "Semua field koneksi harus diisi."); return
            is_ok, msg = connect_to_mt5(acc, pwd, srv, path)
            self.log_window.add_log("Global", msg)
            if is_ok:
                self.is_connected = True; self.btn_connect.setText("Disconnect"); self.btn_toggle_engine.setEnabled(True)
                for i in [self.input_account, self.input_password, self.input_server, self.path_dropdown, self.input_save_pass]: i.setEnabled(False)
                self.accounts_data[acc] = {"server": srv}; save_accounts_data(self.accounts_data)
                if self.input_save_pass.isChecked(): keyring.set_password("7FX_HFT_Bot", acc, pwd)
                else:
                    try: keyring.delete_password("7FX_HFT_Bot", acc)
                    except keyring.errors.PasswordDeleteError: pass
                self.populate_symbols()

    def update_status_panel(self, status_data: dict):
        symbol = status_data.get('symbol');
        if not symbol: return
        if symbol not in self.symbol_row_map:
            row_position = self.status_table.rowCount()
            self.status_table.insertRow(row_position); self.symbol_row_map[symbol] = row_position
            self.status_table.setItem(row_position, 0, QTableWidgetItem(symbol))
        row = self.symbol_row_map[symbol]
        price_item = QTableWidgetItem(f"{status_data.get('price', 0):.5f}")
        condition_item = QTableWidgetItem(status_data.get('condition', '-'))
        info_item = QTableWidgetItem(f"{status_data.get('trend_info', '-')}, {status_data.get('volume_info', '-')}")
        condition_text = status_data.get('condition', '').lower()
        if "bullish" in condition_text: condition_item.setForeground(QColor("#2ecc71"))
        elif "bearish" in condition_text: condition_item.setForeground(QColor("#e74c3c"))
        for item in [price_item, condition_item, info_item]: item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_table.setItem(row, 1, price_item); self.status_table.setItem(row, 2, condition_item); self.status_table.setItem(row, 3, info_item)

    def toggle_engine(self):
        """Menangani logika saat tombol Start/Stop Engine diklik."""
        if self.worker_thread and self.worker_thread.isRunning():
            self.bot_worker.stop()
            self.btn_toggle_engine.setEnabled(False)
            self.log_window.add_log("Global", "Mengirim sinyal stop ke worker...")
        else:
            if self.strategy_tabs.count() == 0:
                QMessageBox.warning(self, "Tidak Ada Strategi", "Harap tambahkan setidaknya satu tab strategi."); return
            all_configs = []
            for i in range(self.strategy_tabs.count()):
                config = self.strategy_tabs.widget(i).get_config()
                if not config['symbol']:
                    QMessageBox.warning(self, "Input Error", f"Harap pilih simbol di Tab Pair {i+1}."); return
                all_configs.append(config)
            
            self.status_table.setRowCount(0); self.symbol_row_map.clear()
            self.log_window.clear_logs(); self.log_window.show()
            self.worker_thread = QThread()
            self.bot_worker = BotWorker(all_configs)
            self.bot_worker.moveToThread(self.worker_thread)
            self.worker_thread.started.connect(self.bot_worker.run)
            self.bot_worker.finished.connect(self.on_worker_finished)
            self.bot_worker.log_update.connect(self.handle_log_update)
            self.bot_worker.status_update.connect(self.update_status_panel)
            self.worker_thread.start()
            self.update_power_button_ui(is_running=True)
            self.btn_add_pair.setEnabled(False); self.strategy_tabs.setTabsClosable(False)

    def handle_log_update(self, symbol, message):
        self.log_window.add_log(symbol, message)

    def on_worker_finished(self):
        """Membersihkan resource setelah worker selesai."""
        self.update_power_button_ui(is_running=False)
        self.btn_toggle_engine.setEnabled(True)
        self.btn_add_pair.setEnabled(True); self.strategy_tabs.setTabsClosable(True)
        if self.worker_thread:
            self.worker_thread.quit(); self.worker_thread.wait()
        self.worker_thread = None; self.bot_worker = None
        
    def closeEvent(self, event):
        """Memastikan semua proses berhenti saat aplikasi ditutup."""
        self.log_window.close()
        if self.worker_thread and self.worker_thread.isRunning(): self.bot_worker.stop()
        shutdown_connection()
        event.accept()

# --- BLOK EKSEKUSI UTAMA ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    window = RobotApp()
    window.show()
    sys.exit(app.exec())