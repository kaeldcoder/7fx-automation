# run_bot_process.py

import sys
import os
from PyQt6.QtWidgets import QApplication

# --- Konfigurasi Path ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if GRANDPARENT_ROOT not in sys.path:
    sys.path.append(GRANDPARENT_ROOT)


from ui.account_panel_ui import AccountPanelUI
from core.bot_process import ProcessHandler
from Library.utils.path_finder import load_accounts_data

def main():
    app = QApplication(sys.argv)

    if len(sys.argv) < 2: sys.exit(1)
    account_number = sys.argv[1]

    all_accounts = load_accounts_data(PROJECT_ROOT)
    account_info = all_accounts.get(account_number)
    if not account_info: sys.exit(1)
    account_info['number'] = account_number

    print(f"Meluncurkan Panel Kontrol untuk Akun: {account_number}")

    # 1. Buat instance UI dan Logika secara terpisah
    ui_panel = AccountPanelUI(account_info)
    backend_handler = ProcessHandler(account_info)

    # 2. Hubungkan sinyal dari UI ke slot di Logika
    ui_panel.start_engine_requested.connect(lambda: backend_handler.start_engine(ui_panel))
    ui_panel.stop_engine_requested.connect(lambda: backend_handler.stop_engine(ui_panel))
    # ui_panel.settings_requested.connect(...) # TODO: hubungkan ke fungsi buka settings

    # 3. Mulai proses inisialisasi backend (akan mengupdate UI via sinyal)
    backend_handler.start_initialization(ui_panel)
    
    # 4. Tampilkan UI
    ui_panel.setWindowTitle(f"Panel Kontrol - Akun {account_number}")
    ui_panel.show()

    # Hubungkan sinyal closeEvent dari UI ke fungsi shutdown di backend
    app.aboutToQuit.connect(backend_handler.shutdown)

    sys.exit(app.exec())

if __name__ == '__main__':
    main()