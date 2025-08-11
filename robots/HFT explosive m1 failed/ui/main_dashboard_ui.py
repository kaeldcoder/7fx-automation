# main_dashboard.py

import sys
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # -> HFT explosive m1
PARENT_ROOT = os.path.dirname(PROJECT_ROOT) # -> robots
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT) # -> 7FX Automation

# Tambahkan root proyek untuk import internal (services, core, ui)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Tambahkan grandparent root untuk import eksternal (Library)
if GRANDPARENT_ROOT not in sys.path:
    sys.path.append(GRANDPARENT_ROOT)
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QVBoxLayout, QPushButton, QHBoxLayout,
                             QMessageBox, QLabel, QFrame, QStackedWidget, QTableWidgetItem,
                             QSystemTrayIcon, QMenu, QHeaderView)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QSize, Qt, pyqtSignal, QObject
from PyQt6.QtGui import QAction
import qtawesome as qta
from ui.account_manager import AccountManager
from services.broker_client import BrokerClient

class GuiSignalHandler(QObject):
    """
    Objek perantara untuk menangani sinyal dari background thread (Broker)
    agar aman untuk memodifikasi UI dari Main Thread.
    """
    status_update_received = pyqtSignal(dict)

class MainDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Main Dashboard - 7FX Automation")
        self.setWindowIcon(qta.icon('fa5s.cogs', color='white'))
        self.setGeometry(300, 300, 1200, 700)

        self.create_ui_components()

        self.signal_handler = GuiSignalHandler()
        self.signal_handler.status_update_received.connect(self._handle_status_update)

        self.broker = BrokerClient()
        if self.broker.is_connected:
            self.broker.subscribe("bot.status", self.on_message_received)
        else:
            QMessageBox.critical(self, "Koneksi Gagal", 
                                 "Tidak dapat terhubung ke Message Broker (Redis). Pastikan server Redis berjalan.")
            
        self.setup_tray_icon()
                                                           
    def on_message_received(self, message: dict):
        """
        Callback yang dipanggil oleh BrokerClient dari background thread.
        Fungsi ini hanya memancarkan sinyal agar UI diupdate di Main Thread.
        """
        self.signal_handler.status_update_received.emit(message)
    
    def create_ui_components(self):
        self.sidebar_is_expanded = True
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QHBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.create_sidebar()

        self.main_content = QStackedWidget()
        welcome_page = QLabel("<h2>Selamat Datang di Control Panel</h2><p>Pilih menu dari sidebar untuk memulai.</p>")
        welcome_page.setStyleSheet("background-color: white; padding: 20px;")
        welcome_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_content.addWidget(welcome_page)

        self.account_manager_page = AccountManager(PROJECT_ROOT)
        self.main_content.addWidget(self.account_manager_page)

        table = self.account_manager_page.account_table
        col_count = table.columnCount()
        table.setColumnCount(col_count + 1)
        header_labels = [table.horizontalHeaderItem(i).text() for i in range(col_count)] + ["Aksi"]
        table.setHorizontalHeaderLabels(header_labels)
        table.horizontalHeader().setSectionResizeMode(col_count, QHeaderView.ResizeMode.ResizeToContents)

        self.account_manager_page.launch_panel_requested.connect(self.launch_account_panel)
        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.main_content, 1)

    def launch_account_panel(self, account_info: dict):
        """Mengirim perintah untuk meluncurkan bot, BUKAN meluncurkannya sendiri."""
        acc_num_str = account_info.get('number')
        print(f"Mengirim perintah 'launch_bot' untuk akun {acc_num_str}...")
        self.broker.publish("dashboard.commands", {
            "command": "launch_bot",
            "account_number": acc_num_str
        })

    def force_kill_bot(self, acc_num_str: str):
        """Mengirim perintah untuk mematikan paksa sebuah bot."""
        reply = QMessageBox.question(self, 'Konfirmasi Force Kill', f"Anda yakin ingin mematikan paksa bot untuk akun {acc_num_str}?", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            print(f"Mengirim perintah 'kill_bot' untuk akun {acc_num_str}...")
            self.broker.publish("dashboard.commands", {
                "command": "kill_bot",
                "account_number": acc_num_str
            })

    def _handle_status_update(self, message: dict):
        """
        Menangani pembaruan status yang diterima dari Broker.
        Fungsi ini berjalan di Main Thread, aman untuk memodifikasi UI.
        """
        account_number = message.get("account_number")
        status = message.get("status")

        if not account_number or not status:
            return

        table = self.account_manager_page.account_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == account_number:
                self._update_table_row(row, account_number, status)
                break

    def _update_table_row(self, row, acc_num_str, status):
        """Memperbarui satu baris di tabel akun."""
        table = self.account_manager_page.account_table
        
        icon_map = {
            "RUNNING": qta.icon('fa5s.robot', color='green'),
            "COOLDOWN": qta.icon('fa5s.hourglass-half', color='#E67E22'),
            "UNRESPONSIVE": qta.icon('fa5s.question-circle', color='orange'),
            "CRASHED": qta.icon('fa5s.exclamation-triangle', color='darkred'),
            "KILLED": qta.icon('fa5s.skull-crossbones', color='black'),
            "OFFLINE": qta.icon('fa5s.power-off', color='red'),
            "Standby": qta.icon('fa5s.pause-circle', color='grey'),
            "Stopped": qta.icon('fa5s.stop-circle', color='darkorange'),
            "Stalled": qta.icon('fa5s.bolt', color='yellow'),
        }

        status_item = QTableWidgetItem(status)
        status_item.setIcon(icon_map.get(status, icon_map["OFFLINE"]))
        table.setItem(row, 3, status_item)

        # Logika untuk tombol Aksi (Kill)
        is_active = status not in ["OFFLINE", "KILLED", "CRASHED", "Standby", "Stopped"]
        
        if is_active and not table.cellWidget(row, 4):
            kill_button = QPushButton(qta.icon('fa5s.skull-crossbones', color='red'), " Kill")
            kill_button.clicked.connect(lambda _, num=acc_num_str: self.force_kill_bot(num))
            table.setCellWidget(row, 4, kill_button)
        elif not is_active and table.cellWidget(row, 4):
            table.removeCellWidget(row, 4)

    def closeEvent(self, event):
        """Menyembunyikan jendela ke tray saat ditutup."""
        self.hide()
        event.ignore()

    def fully_quit_application(self):
        self.broker.stop()
        QApplication.instance().quit()

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        self.sidebar.setStyleSheet("background-color: #f0f0f0;")
        self.sidebar_width_expanded = 200
        self.sidebar_width_collapsed = 50
        self.sidebar.setFixedWidth(self.sidebar_width_expanded)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(5, 5, 5, 5)
        self.sidebar_layout.setSpacing(10)
        self.toggle_button = QPushButton(qta.icon('fa5s.bars'), "")
        self.toggle_button.clicked.connect(self.toggle_sidebar)
        self.toggle_button.setFixedSize(40, 40)
        self.sidebar_layout.addWidget(self.toggle_button)
        self.btn_accounts = QPushButton(qta.icon('fa5s.users'), " Manajemen Akun")
        self.btn_reports = QPushButton(qta.icon('fa5s.chart-pie'), " Laporan Sesi")
        self.btn_settings = QPushButton(qta.icon('fa5s.tools'), " Pengaturan")
        self.btn_exit = QPushButton(qta.icon('fa5s.sign-out-alt'), " Keluar")
        for btn in [self.btn_accounts, self.btn_reports, self.btn_settings, self.btn_exit]:
            btn.setIconSize(QSize(24, 24))
            self.sidebar_layout.addWidget(btn)
        self.sidebar_layout.addStretch()
        self.btn_accounts.clicked.connect(self.open_account_manager)
        self.btn_exit.clicked.connect(self.fully_quit_application)

    def toggle_sidebar(self):
        target_width = self.sidebar_width_collapsed if self.sidebar_is_expanded else self.sidebar_width_expanded
        self.animation = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.animation.setDuration(300)
        self.animation.setStartValue(self.sidebar.width())
        self.animation.setEndValue(target_width)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.animation.start()
        if self.sidebar_is_expanded:
            for btn, text in zip([self.btn_accounts, self.btn_reports, self.btn_settings, self.btn_exit], ["", "", "", ""]):
                btn.setText(text)
        else:
            for btn, text in zip([self.btn_accounts, self.btn_reports, self.btn_settings, self.btn_exit], 
                                 [" Manajemen Akun", " Laporan Sesi", " Pengaturan", " Keluar"]):
                btn.setText(text)
        self.sidebar_is_expanded = not self.sidebar_is_expanded

    def open_account_manager(self):
        self.main_content.setCurrentWidget(self.account_manager_page)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(qta.icon('fa5s.robot', color='white'), self)
        self.tray_icon.setToolTip("7FX Automation Control Panel")
        tray_menu = QMenu()
        show_action = QAction("Tampilkan Dashboard", self)
        quit_action = QAction("Keluar Aplikasi", self)
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.fully_quit_application)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec())