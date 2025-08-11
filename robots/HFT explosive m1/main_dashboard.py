# main_dashboard.py

import sys
import os
import socket
import json
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QVBoxLayout, QPushButton, QHBoxLayout,
                             QMessageBox, QLabel, QFrame, QStackedWidget, QTableWidgetItem,
                             QSystemTrayIcon, QMenu, QHeaderView,QSizePolicy)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QSize, Qt, QThread, QObject, pyqtSignal, QSettings, QTimer, QPoint
from PyQt6.QtGui import QAction, QFontDatabase
import qtawesome as qta

from account_manager import AccountManager
from report_dashboard_window import ReportDashboardWindow
from global_settings_dialog import GlobalSettingsDialog
from dashboard_widgets import KPIPanel
from report_analyzer import calculate_overall_kpis
from custom_widgets import AnimatedButton
from custom_dialogs import ConfirmationDialog, MessageDialog

from Library.utils.path_finder import (load_known_paths, save_known_paths, 
                                       scan_for_metatrader_enhanced, find_by_smart_search)
import subprocess

class ClientHandler(QObject):
    finished = pyqtSignal()
    message_received = pyqtSignal(dict)

    def __init__(self, connection, address):
        super().__init__()
        self.conn = connection
        self.addr = address
        self.is_running = True

    def run(self):
        buffer = b""
        with self.conn:
            while self.is_running:
                try:
                    data_chunk = self.conn.recv(1024)
                    if not data_chunk:
                        break
                    buffer += data_chunk
                    while b'\n' in buffer:
                        message_part, buffer = buffer.split(b'\n', 1)
                        decoded_data = message_part.decode('utf-8')
                        message = json.loads(decoded_data)
                        self.message_received.emit(message)
                except (ConnectionResetError, json.JSONDecodeError):
                    break
                except Exception as e:
                    print(f"Error pada handler klien {self.addr}: {e}")
                    break
        print(f"Koneksi dari {self.addr} ditutup.")
        self.finished.emit()

class StatusServer(QObject):  
    def __init__(self, port=65432):
        super().__init__()
        self.port = port
        self.host = '127.0.0.1'
        self.is_running = True
        self.server_socket = None
        self.client_threads = []
        self.main_dashboard_handler = None
    
    def set_handler(self, handler_slot):
        self.main_dashboard_handler = handler_slot

    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"Server Status (multi-klien) berjalan di port {self.port}...")
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                client_thread = QThread()
                client_handler = ClientHandler(conn, addr)
                client_handler.moveToThread(client_thread)
                if self.main_dashboard_handler:
                    client_handler.message_received.connect(self.main_dashboard_handler)
                client_thread.started.connect(client_handler.run)
                client_handler.finished.connect(client_thread.quit)
                client_handler.finished.connect(client_handler.deleteLater)
                client_thread.finished.connect(client_thread.deleteLater)
                self.client_threads.append(client_thread)
                client_thread.start()
            except Exception as e:
                if self.is_running: print(f"Server ditutup atau error: {e}"); break
        print("Server Status berhenti.")

    def stop(self):
        self.is_running = False
        if self.server_socket: self.server_socket.close()
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((self.host, self.port))
        except: pass

class KillWorker(QObject):
    finished = pyqtSignal(str)

    def __init__(self, process_to_kill, acc_num_str):
        super().__init__()
        self.process = process_to_kill
        self.acc_num = acc_num_str

    def run(self):
        """Menjalankan proses terminasi paling kuat dengan /T (tree)."""
        if self.process is None or self.process.poll() is not None:
            print(f"KillWorker: Proses untuk akun {self.acc_num} sudah tidak berjalan.")
            self.finished.emit(self.acc_num)
            return

        pid_to_kill = str(self.process.pid)
        print(f"KillWorker: Memulai terminasi paksa untuk pohon proses PID: {pid_to_kill}...")
        
        if sys.platform == "win32":
            # Perintah paling kuat: Force kill Process Tree (/T)
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', pid_to_kill],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
            )
        else:
            # Di Linux/macOS, SIGKILL sudah sangat kuat
            self.process.kill()

        print(f"KillWorker: Perintah terminasi paksa untuk akun {self.acc_num} telah dikirim.")
        self.finished.emit(self.acc_num)

class MainDashboard(QMainWindow):
    def __init__(self, robot_root_path: str):
        super().__init__()
        self.load_custom_fonts()
        self.robot_root_path = robot_root_path

        self.setWindowTitle(self.tr("Main Dashboard - 7FX Automation"))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(200, 200, 1280, 720)
        self.setObjectName("MainDashboard")

        self.dragPos = QPoint()
        self.sidebar_is_expanded = True
        self._is_dragging = False

        self.central_widget = QWidget()
        self.central_widget.setObjectName("MainCentralWidget")
        self.setCentralWidget(self.central_widget)
        
        # Layout terluar
        self.outer_layout = QVBoxLayout(self.central_widget)
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)

        # 1. Buat dan tambahkan Header Kustom
        self.header = self.create_header()
        self.outer_layout.addWidget(self.header)

        # 2. Buat layout utama di bawah header
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.outer_layout.addLayout(self.main_layout)

        self.running_bot_processes = {}
        self.kill_threads = []

        self.bot_heartbeats = {}
        self.shutting_down_bots = set()
        self.watchdog_timer = QTimer(self)
        self.watchdog_timer.timeout.connect(self.check_bot_health)
        self.watchdog_timer.start(15000)

        self.server_thread = QThread()
        self.status_server = StatusServer()
        self.status_server.set_handler(self.handle_bot_status_update)
        self.status_server.moveToThread(self.server_thread)
        self.server_thread.started.connect(self.status_server.run)
        self.server_thread.start()

        self.create_sidebar()
        self.create_main_content()

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.main_content, 1)

        self.settings = QSettings('7FXAutomation', 'MainDashboard')
        self.show_exit_confirmation = self.settings.value('show_exit_confirmation', True, type=bool)
        self.tray_icon = QSystemTrayIcon(qta.icon('fa5s.robot', color='white'), self)
        self.tray_icon.setToolTip(self.tr("7FX Automation Control Panel"))
        tray_menu = QMenu()
        show_action = QAction(self.tr("Show Dashboard"), self)
        quit_action = QAction(self.tr("Exit Application"), self)
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.fully_quit_application)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.force_quit = False
        self.start_background_path_scan()
        self.apply_stylesheet()

    def create_main_content(self):
        """Membuat dan mengisi QStackedWidget untuk konten utama."""
        self.main_content = QStackedWidget()
        self.main_content.setObjectName("MainContent")
        
        # 1. Halaman Dashboard (DIUBAH MENJADI WELCOME PAGE)
        self.dashboard_page = QWidget()
        dashboard_layout = QVBoxLayout(self.dashboard_page)
        dashboard_layout.setContentsMargins(30, 20, 30, 20)
        
        # Buat label selamat datang
        welcome_label = QLabel(
            """
            <h1 style='color: #ffffff; font-family: "Oswald";'>Selamat Datang di 7FX Automation</h1>
            <p style='color: #6a6e79; font-size: 16px;'>
                Pilih menu di sebelah kiri untuk memulai.<br>
                - <b>Account Management:</b> Untuk menambah atau mengelola akun trading Anda.<br>
                - <b>Session Reports:</b> Untuk melihat riwayat dan analisis performa trading.
            </p>
            """
        )
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setWordWrap(True)
        
        dashboard_layout.addStretch()
        dashboard_layout.addWidget(welcome_label)
        dashboard_layout.addStretch()

        self.main_content.addWidget(self.dashboard_page)
        
        # 2. Halaman Manajemen Akun (Tidak berubah)
        self.account_manager_page = AccountManager(robot_root_path=self.robot_root_path)
        self.main_content.addWidget(self.account_manager_page)
        self.account_manager_page.launch_panel_requested.connect(self.launch_account_panel)
        self.account_manager_page.force_kill_requested.connect(self.force_kill_bot)
        
        # 3. Halaman Laporan Sesi (Tidak berubah)
        self.report_page = ReportDashboardWindow(parent=self)
        self.main_content.addWidget(self.report_page)

        # 4. Halaman Pengaturan
        self.settings_page = GlobalSettingsDialog(parent=self)
        self.main_content.addWidget(self.settings_page)

    def create_header(self):
        """Membuat widget header kustom yang bisa di-drag."""
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 0, 5, 0)

        # Ikon dan Judul Aplikasi
        app_icon = QLabel()
        app_icon.setPixmap(qta.icon('fa5s.cogs', color='#01c38e').pixmap(20, 20))
        app_title = QLabel(self.tr("7FX Automation Dashboard"))
        app_title.setObjectName("HeaderTitle")

        # Tombol Kontrol Jendela
        btn_minimize = QPushButton(qta.icon('fa5s.minus', color='#6a6e79'), "")
        btn_maximize = QPushButton(qta.icon('fa5s.square', color='#6a6e79'), "")
        btn_close = QPushButton(qta.icon('fa5s.times', color='#6a6e79'), "")
        
        self.control_buttons = [btn_minimize, btn_maximize, btn_close]
        for btn in self.control_buttons:
            btn.setObjectName("ControlButton")
            btn.setFixedSize(30, 30)

        btn_minimize.clicked.connect(self.showMinimized)
        btn_maximize.clicked.connect(self.toggle_maximize)
        btn_close.clicked.connect(self.close)

        header_layout.addWidget(app_icon)
        header_layout.addWidget(app_title)
        header_layout.addStretch()
        header_layout.addWidget(btn_minimize)
        header_layout.addWidget(btn_maximize)
        header_layout.addWidget(btn_close)
        
        return header

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar_width_expanded = 240
        self.sidebar_width_collapsed = 40
        self.sidebar.setFixedWidth(self.sidebar_width_expanded)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(5, 5, 5, 5)
        self.sidebar_layout.setSpacing(10)
        self.sidebar_layout.setObjectName('SidebarWrapper')
        self.toggle_button = QPushButton(qta.icon('fa5s.bars',color_off='#6a6e79', color_on='white'), "")
        self.toggle_button.setObjectName("ToggleButton")
        self.toggle_button.clicked.connect(self.toggle_sidebar)
        self.toggle_button.setFixedSize(40, 40)
        self.sidebar_layout.addWidget(self.toggle_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.sidebar_layout.addSpacing(20)
        self.btn_dashboard = AnimatedButton(qta.icon('fa5s.home', color_off='#6a6e79', color_on='white'), self.tr(" Dashboard"))
        self.btn_accounts = AnimatedButton(qta.icon('fa5s.users', color_off='#6a6e79', color_on='white'), self.tr(" Account Management"))
        self.btn_reports = AnimatedButton(qta.icon('fa5s.chart-pie', color_off='#6a6e79', color_on='white'), self.tr(" Session Reports"))
        self.btn_settings = AnimatedButton(qta.icon('fa5s.tools', color_off='#6a6e79', color_on='white'), self.tr(" Settings"))
        self.btn_exit = AnimatedButton(qta.icon('fa5s.sign-out-alt', color_off='#6a6e79', color_on='white'), self.tr(" Exit"))
        self.menu_buttons = [self.btn_dashboard, self.btn_accounts, self.btn_reports, self.btn_settings]
        for btn in self.menu_buttons:
            btn.setObjectName("MenuButton")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.sidebar_layout.addWidget(btn)
        self.sidebar_layout.addStretch()
        self.btn_exit.setObjectName("MenuButton")
        self.sidebar_layout.addWidget(self.btn_exit, alignment=Qt.AlignmentFlag.AlignLeft)
        self.btn_dashboard.clicked.connect(lambda: self.handle_menu_click(self.btn_dashboard, self.open_dashboard))
        self.btn_accounts.clicked.connect(lambda: self.handle_menu_click(self.btn_accounts, self.open_account_manager))
        self.btn_reports.clicked.connect(lambda: self.handle_menu_click(self.btn_reports, self.open_report_dashboard))
        self.btn_settings.clicked.connect(lambda: self.handle_menu_click(self.btn_settings, self.open_global_settings))
        self.btn_exit.clicked.connect(self.fully_quit_application)

        self.btn_dashboard.setChecked(True)

    def load_custom_fonts(self):
        """Mendaftarkan font kustom dari folder assets."""
        font_dir = "assets/fonts"
        if os.path.isdir(font_dir):
            for font_file in os.listdir(font_dir):
                if font_file.endswith((".ttf", ".otf")):
                    QFontDatabase.addApplicationFont(os.path.join(font_dir, font_file))

    def handle_menu_click(self, clicked_button, slot):
        """Memastikan hanya satu tombol menu yang aktif dan memanggil fungsi yang sesuai."""
        for btn in self.menu_buttons:
            if btn is not clicked_button:
                btn.setChecked(False)
        clicked_button.setChecked(True)
        slot()

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.header.underMouse():
            for btn in self.control_buttons:
                if btn.underMouse():
                    return # Jangan lakukan apa-apa jika klik di atas tombol

            # Jika semua syarat terpenuhi, aktifkan mode drag dan catat posisi
            self._is_dragging = True
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.dragPos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Dipanggil saat tombol mouse dilepas."""
        # Matikan mode drag
        self._is_dragging = False

    def toggle_sidebar(self):
        target_width = self.sidebar_width_collapsed if self.sidebar_is_expanded else self.sidebar_width_expanded
        self.animation = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.animation.setDuration(300)
        self.animation.setStartValue(self.sidebar.width())
        self.animation.setEndValue(target_width)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.animation.start()
        all_buttons = self.menu_buttons + [self.btn_exit]
        if self.sidebar_is_expanded:
            for btn in all_buttons:
                btn.setText("")
                # Ambil layout item dan set alignment ke tengah
                item = self.sidebar_layout.itemAt(self.sidebar_layout.indexOf(btn))
                item.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.btn_dashboard.setText(self.tr(" Dashboard"))
            self.btn_accounts.setText(self.tr(" Account Management"))
            self.btn_reports.setText(self.tr(" Session Reports"))
            self.btn_settings.setText(self.tr(" Settings"))
            self.btn_exit.setText(self.tr(" Exit"))
            for btn in all_buttons:
                item = self.sidebar_layout.itemAt(self.sidebar_layout.indexOf(btn))
                item.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.sidebar_is_expanded = not self.sidebar_is_expanded

    def open_dashboard(self):
        self.main_content.setCurrentWidget(self.dashboard_page)

    def open_account_manager(self):
        self.main_content.setCurrentWidget(self.account_manager_page)

    def open_report_dashboard(self):
        self.main_content.setCurrentWidget(self.report_page)

    def open_global_settings(self):
        self.main_content.setCurrentWidget(self.settings_page)

    def launch_account_panel(self, account_info: dict):
        acc_num_str = account_info.get('number')
        if acc_num_str in self.running_bot_processes:
            QMessageBox.information(self, self.tr("Info"), self.tr("Panel for account {0} is already running.").format(acc_num_str))
            return
        try:
            self._update_table_row_by_acc(acc_num_str, "LAUNCHING...")
            
            process = subprocess.Popen([sys.executable, 'run_bot_process.py', acc_num_str])
            self.running_bot_processes[acc_num_str] = process
            self.bot_heartbeats[acc_num_str] = time.time()
            print(f"Meluncurkan proses untuk akun {acc_num_str} dengan PID: {process.pid}")

        except Exception as e:
            error_dialog = MessageDialog(
                title=self.tr("Launch Failed"),
                message=self.tr("Failed to run bot process: {0}").format(e),
                parent=self
            )
            error_dialog.exec()

    def handle_bot_status_update(self, message: dict):
        account_number = message.get("account")
        status = message.get("status")

        if account_number and status:
            acc_num_str = str(account_number)
            self.bot_heartbeats[acc_num_str] = time.time()

            self.account_manager_page.update_account_status(acc_num_str, status)

            if status in ["OFFLINE", "CRASHED", "KILLED"]:
                if acc_num_str in self.running_bot_processes:
                    print(f"Panel untuk akun {acc_num_str} tidak aktif. Menghapus dari daftar.")
                    del self.running_bot_processes[acc_num_str]
                if acc_num_str in self.bot_heartbeats:
                    del self.bot_heartbeats[acc_num_str]

            # Panggil fungsi yang benar di AccountManager untuk update bubble
            

    # [BARU] Metode Watchdog
    def check_bot_health(self):
        for acc_num_str, process in list(self.running_bot_processes.items()):
            if process.poll() is not None:
                # Jika proses berhenti, cek apakah kita memang sengaja menghentikannya
                if acc_num_str in self.shutting_down_bots:
                    print(self.tr("WATCHDOG: Process for account {0} stopped normally.").format(acc_num_str))
                    self._update_table_row_by_acc(acc_num_str, "OFFLINE")
                else: # Jika tidak, berarti ini CRASH
                    print(self.tr("WATCHDOG: Process for account {0} detected as CRASHED.").format(acc_num_str))
                    self._update_table_row_by_acc(acc_num_str, "CRASHED")
                if acc_num_str in self.running_bot_processes:
                    del self.running_bot_processes[acc_num_str]
                if acc_num_str in self.bot_heartbeats:
                    del self.bot_heartbeats[acc_num_str]
                continue

            last_heartbeat = self.bot_heartbeats.get(acc_num_str, 0)
            if time.time() - last_heartbeat > 30:
                print(self.tr("WATCHDOG: Process for account {0} detected as UNRESPONSIVE.").format(acc_num_str))
                self._update_table_row_by_acc(acc_num_str, "UNRESPONSIVE")

    def _update_table_row_by_acc(self, acc_num_str, status):
        """Meneruskan perintah update status ke AccountManager."""
        self.account_manager_page.update_account_status(acc_num_str, status)

    def force_kill_bot(self, acc_num_str):
        dialog = ConfirmationDialog(
            title=self.tr("Confirm Force Kill"),
            message=self.tr("Are you sure you want to force kill the bot for account {0}?").format(acc_num_str),
            parent=self
        )
        if dialog.exec():
            if acc_num_str in self.running_bot_processes:
                process = self.running_bot_processes[acc_num_str]

                self.shutting_down_bots.add(acc_num_str)
                self._update_table_row_by_acc(acc_num_str, "STOPPING...")

                thread = QThread()
                worker = KillWorker(process, acc_num_str)
                worker.moveToThread(thread)

                thread.started.connect(worker.run)
                worker.finished.connect(self.on_kill_finished)

                worker.finished.connect(thread.quit)
                worker.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)

                thread.start()
                self.kill_threads.append(thread)
            else:
                info_dialog = MessageDialog(
                    title="Info",
                    message=self.tr("The process for this account is no longer running."),
                    parent=self
                )
                info_dialog.exec()

    def on_kill_finished(self, acc_num_str: str):
        """Dipanggil setelah KillWorker berhasil mematikan proses."""
        print(self.tr("Kill for account {0} finished, updating UI.").format(acc_num_str))
        self._update_table_row_by_acc(acc_num_str, "KILLED")

    def closeEvent(self, event):
        """[VERSI BARU] Sembunyikan ke tray atau keluar sepenuhnya."""
        # Cek apakah ini adalah perintah keluar paksa dari tombol "Keluar"
        if self.force_quit:
            # Jika ada bot berjalan, tampilkan konfirmasi seperti biasa
            if self.running_bot_processes:
                dialog = ConfirmationDialog(
                    title=self.tr("Confirm Exit"),
                    message=self.tr('There are {0} bots running. Are you sure you want to stop them all?').format(len(self.running_bot_processes)),
                    parent=self
                )
                if not dialog.exec(): # Jika pengguna menekan "No"
                    self.force_quit = False
                    event.ignore()
                    return

            # Jalankan proses shutdown di thread terpisah agar UI langsung tertutup
            self.shutdown_thread = QThread()
            self.shutdown_worker = ShutdownWorker(self.running_bot_processes, self.status_server, self.server_thread)
            self.shutdown_worker.moveToThread(self.shutdown_thread)
            self.shutdown_thread.started.connect(self.shutdown_worker.run)
            self.shutdown_worker.finished.connect(QApplication.quit)
            self.shutdown_thread.start()
            
            event.accept() # Terima event agar jendela bisa ditutup
            self.hide() # Sembunyikan UI segera
        else:
            # Jika hanya menekan 'X', sembunyikan jendela ke tray
            self.hide()
            event.ignore()

    def on_tray_icon_activated(self, reason):
        """Hanya menampilkan jendela utama."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()

    def fully_quit_application(self):
        """Memulai proses shutdown yang sebenarnya."""
        # Kita panggil closeEvent secara manual dengan penanda khusus
        # agar ia tahu ini adalah perintah keluar sungguhan.
        self.force_quit = True # Buat atribut baru sebagai penanda
        self.close()

    def start_background_path_scan(self):
        """Mempersiapkan dan memulai worker untuk scan path di latar belakang."""
        self.path_scanner_thread = QThread()
        # Teruskan robot_root_path ke worker
        self.path_scanner_worker = PathScannerWorker(self.robot_root_path)
        self.path_scanner_worker.moveToThread(self.path_scanner_thread)

        # Hubungkan sinyal-sinyal
        self.path_scanner_thread.started.connect(self.path_scanner_worker.run)
        self.path_scanner_worker.finished.connect(self.path_scanner_thread.quit)
        self.path_scanner_worker.finished.connect(self.path_scanner_worker.deleteLater)
        self.path_scanner_thread.finished.connect(self.path_scanner_thread.deleteLater)

        # (Opsional) Hubungkan ke fungsi jika ingin menampilkan notifikasi
        # self.path_scanner_worker.new_paths_found.connect(self.on_new_paths_found)

        # Mulai thread
        self.path_scanner_thread.start()

    def on_new_paths_found(self, count: int):
        """Menampilkan notifikasi di tray icon saat path baru ditemukan."""
        self.tray_icon.showMessage(
            self.tr("Paths Found"),
            self.tr("{0} new MetaTrader 5 installations were found and saved.").format(count),
            QSystemTrayIcon.MessageIcon.Information,
            5000 # durasi notifikasi dalam milidetik
        )

    def apply_stylesheet(self):
        try:
            # [DIUBAH] Tambahkan "css/" pada path file
            with open("css/stylesheet.qss", "r") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print("Warning: css/stylesheet.qss not found. UI will not be styled.")

class ShutdownWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, processes, server, server_thread):
        super().__init__()
        self.processes = processes
        self.server = server
        self.server_thread = server_thread

    def run(self):
        """Menjalankan semua proses shutdown dengan force kill tree."""
        print("ShutdownWorker: Memulai proses shutdown...")
        
        for acc_num, process in self.processes.items():
            if process.poll() is None:
                pid_to_kill = str(process.pid)
                print(f"ShutdownWorker: Menghentikan paksa pohon proses akun {acc_num} (PID: {pid_to_kill})...")
                if sys.platform == "win32":
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', pid_to_kill],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
                    )
                else:
                    process.kill()
        
        print("ShutdownWorker: Menghentikan server status...")
        self.server.stop()
        self.server_thread.quit()
        self.server_thread.wait()
        print("ShutdownWorker: Proses shutdown selesai.")
        
        self.finished.emit()

class PathScannerWorker(QObject):
    """
    Worker untuk menjalankan scan path MT5 di latar belakang
    tanpa memblokir UI utama.
    """
    finished = pyqtSignal()
    # Opsional: sinyal jika ingin memberi notifikasi saat path baru ditemukan
    new_paths_found = pyqtSignal(int) 

    def __init__(self, robot_root_path: str):
        super().__init__()
        self.robot_root_path = robot_root_path

    def run(self):
        """Menjalankan quick scan (registry & smart search) di background."""
        print("PathScannerWorker: Memulai scan path di latar belakang...")
        current_paths = load_known_paths(self.robot_root_path)
        
        # Gabungkan hasil dari dua metode scan cepat
        paths_from_scan = scan_for_metatrader_enhanced() | find_by_smart_search()
        
        # Gabungkan dengan path yang sudah ada
        all_found_paths = current_paths.union(paths_from_scan)

        if len(all_found_paths) > len(current_paths):
            newly_found_count = len(all_found_paths) - len(current_paths)
            print(f"PathScannerWorker: Ditemukan {newly_found_count} path MT5 baru. Menyimpan...")
            save_known_paths(self.robot_root_path, all_found_paths)
            self.new_paths_found.emit(newly_found_count)
        else:
            print("PathScannerWorker: Tidak ada path MT5 baru ditemukan dari quick scan.")

        self.finished.emit()

if __name__ == '__main__':
    from PyQt6.QtCore import Qt
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec())