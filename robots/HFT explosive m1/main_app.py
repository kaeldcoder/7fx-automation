# main_app.py

import sys
import time
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, QObject, pyqtSignal

# Hanya impor modul yang ringan untuk login
from login_window import LoginWindow
from loading_window import GenericLoadingDialog

# --- Konfigurasi Path ---
# current_file_path = os.path.abspath(__file__)
# project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
# if project_root not in sys.path:
#     sys.path.append(project_root)

robot_data_path = os.getcwd()
project_root_for_sys_path = os.path.dirname(os.path.dirname(robot_data_path))
if project_root_for_sys_path not in sys.path:
    sys.path.append(project_root_for_sys_path)

# --- Kelas Aplikasi Utama ---
class MainApplication:
    def __init__(self):
        self.project_root = robot_data_path
        self.login_win = LoginWindow()

        self.loading_dialog = None

        self.dashboard_class = None
        self.dashboard_win = None
        
        # Penanda status untuk menangani race condition
        self.is_loading_finished = False
        self.is_login_successful = False

        self.login_win.login_successful.connect(self.handle_login_success)
        self.login_win.window_is_ready.connect(self.start_background_loader)

        # Setup thread untuk pre-loading
        self.loader_thread = QThread()
        self.dashboard_loader = DashboardLoader()
        self.dashboard_loader.moveToThread(self.loader_thread)
        
        self.loader_thread.started.connect(self.dashboard_loader.run)
        self.dashboard_loader.loading_finished.connect(self.handle_loading_finished)

    def start(self):
        """Mulai aplikasi: tampilkan login & mulai pre-loading."""
        self.login_win.show()

    def start_background_loader(self):
        """Fungsi ini dipanggil oleh sinyal 'window_is_ready'."""
        # Pastikan hanya dijalankan sekali
        if not self.loader_thread.isRunning():
            print("Login UI ready, starting pre-loading in the background...")
            self.loader_thread.start()

    def handle_loading_finished(self, dashboard_class):
        """Dipanggil saat pre-loading di background selesai."""
        self.dashboard_class = dashboard_class
        self.is_loading_finished = True
        print("Dashboard ready.")
        
        # Jika pengguna sudah login duluan, langsung tampilkan dashboard
        if self.is_login_successful:
            self.show_dashboard()

    def handle_login_success(self):
        """Dipanggil saat pengguna berhasil login."""
        self.is_login_successful = True
        
        if self.is_loading_finished:
            # Jika loading sudah selesai, langsung tampilkan
            self.show_dashboard()
        else:
            # Jika loading belum selesai, beri tahu pengguna dan tunggu
            print("Login successful, waiting for pre-loading to finish...")
            
            class DummyWorker(QObject): # Worker palsu yang tidak melakukan apa-apa
                finished = pyqtSignal()
            
            self.loading_dialog = GenericLoadingDialog(
                worker=DummyWorker(), # Beri worker palsu
                start_text=QApplication.translate("MainApplication", "Finalizing preparations..."),
                title=QApplication.translate("MainApplication", "Loading Dashboard"),
                parent=self.login_win
            )
            self.loading_dialog.show()

    def show_dashboard(self):
        """Fungsi terpusat untuk membuat dan menampilkan dashboard."""
        # Pastikan hanya dijalankan sekali dan semua kondisi terpenuhi
        if self.dashboard_class and not self.dashboard_win:
            print("Showing dashboard...")

            if self.loading_dialog and self.loading_dialog.isVisible():
                self.loading_dialog.accept()

            self.dashboard_win = self.dashboard_class(robot_root_path=self.project_root)
            self.dashboard_win.show()
            self.login_win.close()
            self.loader_thread.quit()

# --- Worker untuk memuat Dashboard di background ---
class DashboardLoader(QObject):
    loading_finished = pyqtSignal(object) # Sinyal yang membawa kelas

    def run(self):
        """Metode ini hanya melakukan impor di background."""
        print(self.tr("Pre-loading MainDashboard started in the background..."))
        from main_dashboard import MainDashboard
        print(self.tr("Pre-loading MainDashboard finished."))
        self.loading_finished.emit(MainDashboard)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_app = MainApplication()
    main_app.start()
    sys.exit(app.exec())