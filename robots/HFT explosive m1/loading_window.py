# loading_window.py

import sys
import os
import keyring
import time
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QWidget
from PyQt6.QtCore import QThread, QObject, pyqtSignal, Qt
import qtawesome as qta

# Impor yang diperlukan
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from Library.broker_interface.mt5_connector import connect_to_mt5
import MetaTrader5 as mt5

class Mt5LoaderWorker(QObject):
    """Worker untuk tugas loading di background."""
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(bool, str, list, dict)  # success (bool), message (str), symbols (list)

    def __init__(self, account_info):
        super().__init__()
        self.account_info = account_info

    def run(self):
        try:
            acc_num_str = self.account_info.get('number')
            server = self.account_info.get('server')
            path = self.account_info.get('path')

            self.status_updated.emit(self.tr("Retrieving password from Keyring..."))
            password = keyring.get_password("7FX_HFT_Bot", acc_num_str)
            if password is None: # Cek jika password tidak ada
                self.finished.emit(False, f"Password for account {acc_num_str} not found in Keyring.", [], self.account_info)
                return

            self.status_updated.emit(self.tr("Connecting to MetaTrader 5..."))
            is_ok, result = connect_to_mt5(int(acc_num_str), password, server, path, timeout=10000)

            if is_ok:
                # Jika sukses, 'result' adalah daftar simbol
                self.status_updated.emit(self.tr("Setup complete!"))
                self.finished.emit(True, "Successfully connected.", result, self.account_info)
            
            else:
                # Jika gagal, 'result' adalah pesan error
                self.finished.emit(False, result, [], self.account_info)

        except Exception as e:
            self.finished.emit(False, f"An unexpected error occurred: {e}", [], self.account_info)

class GenericLoadingDialog(QDialog):
    def __init__(self, worker: QObject, start_text=None, title=None, parent=None):
        super().__init__(parent)
        self.worker = worker

        if start_text is None:
            start_text = self.tr("Starting process...")
        if title is None:
            title = self.tr("Please Wait...")

        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 220)
        self.setModal(True)

        self.main_widget = QWidget()
        self.main_widget.setObjectName("MainWidget")
        
        layout = QVBoxLayout(self.main_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        spinner_icon = qta.icon('fa5s.spinner', color='#01c38e', animation=qta.Spin(self))
        spinner_label = QLabel()
        spinner_label.setPixmap(spinner_icon.pixmap(50, 50))
        spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.status_label = QLabel(start_text)
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)

        layout.addWidget(spinner_label)
        layout.addSpacing(10)
        layout.addWidget(self.status_label)

        final_layout = QVBoxLayout(self)
        final_layout.setContentsMargins(0,0,0,0)
        final_layout.addWidget(self.main_widget)

        self.apply_stylesheet()

        # Logika generik untuk menjalankan worker apa pun
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        # Hubungkan sinyal secara dinamis
        if hasattr(self.worker, 'status_updated'):
            self.worker.status_updated.connect(self.status_label.setText)
        
        # Sinyal finished dari worker akan menutup dialog
        self.worker.finished.connect(self.on_worker_finished)
        self.thread.started.connect(self.worker.run)

    def execute(self):
        """Mulai thread dan tampilkan dialog. Panggil ini, bukan exec()."""
        self.thread.start()
        super().exec()

    def on_worker_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.accept() # Menutup dialog

    def apply_stylesheet(self):
        self.setStyleSheet("""
            #MainWidget {
                background-color: #1a1e29; border-radius: 10px;
                font-family: Segoe UI, Arial, sans-serif;
            }
            #StatusLabel { color: #ffffff; font-size: 16px; font-weight: bold; }
        """)

def run_mt5_loader(account_info):
    """Fungsi pembungkus untuk menjalankan loading koneksi MT5."""
    worker = Mt5LoaderWorker(account_info)
    dialog = GenericLoadingDialog(worker, 
                                  start_text=QApplication.translate("run_mt5_loader", "Loading Account: {0}").format(account_info.get('number', 'N/A')),
                                  title=QApplication.translate("run_mt5_loader", "Connecting..."))
    
    # Hubungkan sinyal 'finished' dari worker ke fungsi yang menangani hasilnya
    worker.finished.connect(on_mt5_loading_finished)
    dialog.execute()

def on_mt5_loading_finished(success, message, available_symbols, account_info):
    from account_control_panel import AccountControlPanel
    import run_bot_process
    """Fungsi ini akan dieksekusi setelah worker koneksi MT5 selesai."""
    if success:
        run_bot_process.main_panel = AccountControlPanel(account_info, available_symbols)
        run_bot_process.main_panel.setWindowTitle(QApplication.translate("on_mt5_loading_finished", "Control Panel - Account {0} [PID: {1}]").format(account_info['number'], os.getpid()))
        run_bot_process.main_panel.show()
    else:
        print(QApplication.translate("on_mt5_loading_finished", "ERROR DURING LOADING: {0}").format(message))
        QApplication.instance().quit()

