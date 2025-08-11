import sys
import os
import warnings
import json
import keyring

# --- Konfigurasi Path ---
warnings.filterwarnings("ignore", category=FutureWarning)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import QTimer

# [DIUBAH] Impor yang diperlukan untuk menjalankan loader secara lokal
from Library.utils.path_finder import load_accounts_data
from account_control_panel import ControlPanelWindow
from loading_window import Mt5LoaderWorker, GenericLoadingDialog 
from custom_dialogs import RetryConnectionDialog

main_panel = None
app = None
account_info_global = None

def attempt_connection():
    """Fungsi untuk menjalankan satu siklus upaya koneksi."""
    global account_info_global
    if not account_info_global:
        print("Error: Account info not available for connection attempt.")
        app.quit()
        return

    # Menjalankan worker dan dialog loading
    worker = Mt5LoaderWorker(account_info_global)
    dialog = GenericLoadingDialog(worker, 
                                  start_text=f"Loading Account: {account_info_global.get('number', 'N/A')}",
                                  title="Connecting...")
    worker.finished.connect(on_mt5_loading_finished)
    dialog.execute()

def on_mt5_loading_finished(success, message, available_symbols, account_info):
    global main_panel, app
    if success:
        main_panel = ControlPanelWindow(account_info, available_symbols)
        main_panel.show()
    else:
        # Jika GAGAL, tampilkan dialog retry/cancel
        error_details = (
            f"<b>Failed to connect:</b><br>{message}<br><br>"
            "Please check your internet connection and ensure the MetaTrader 5 terminal is running and logged in."
        )
        retry_dialog = RetryConnectionDialog("Connection Failed", error_details)
        
        if retry_dialog.exec() == QDialog.DialogCode.Accepted:
            # Jika pengguna menekan "Retry"
            QTimer.singleShot(0, attempt_connection)
        else:
            # Jika pengguna menekan "Cancel"
            app.quit()

def main():
    global app, account_info_global
    app = QApplication(sys.argv)
    
    try:
        with open("css/stylesheet.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Warning: css/stylesheet.qss not found. UI will not be styled.")

    if len(sys.argv) < 2:
        print("Error: Nomor akun tidak disediakan."); sys.exit(1)
    
    account_number = sys.argv[1]
    robot_root_path = os.path.dirname(os.path.abspath(__file__))
    all_accounts = load_accounts_data(robot_root_path)
    account_info = all_accounts.get(account_number)

    if not account_info:
        print(f"Error: Data untuk akun {account_number} tidak ditemukan."); sys.exit(1)
        
    account_info['number'] = account_number
    if 'path' not in account_info or not account_info['path']:
         print(f"Error: Path MT5 untuk akun {account_number} tidak ditemukan."); sys.exit(1)

    account_info_global = account_info
    
    # Mulai upaya koneksi pertama
    attempt_connection()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()