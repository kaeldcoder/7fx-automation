# main.py

import sys
import os
import subprocess
from PyQt6.QtWidgets import QApplication

# Konfigurasi Path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if GRANDPARENT_ROOT not in sys.path:
    sys.path.append(GRANDPARENT_ROOT)

from ui.login_window import LoginWindow
from services.broker_client import BrokerClient

def main():
    app = QApplication(sys.argv)
    
    # 1. Buat instance jendela login
    login_win = LoginWindow()
    # 2. Tampilkan jendela login SEGERA (non-blocking)
    login_win.show()

    # 3. SEGERA setelah UI tampil, luncurkan supervisor di latar belakang
    print("[MainApp] Meluncurkan Supervisor di latar belakang...")
    supervisor_script = os.path.join(PROJECT_ROOT, 'app', 'supervisor.py')
    subprocess.Popen([sys.executable, supervisor_script])

    # 4. Jalankan event loop dialog. Kode akan berhenti di sini sampai jendela login ditutup.
    if login_win.exec():
        # 5. Jika login berhasil...
        print("[MainApp] ✅ Login berhasil. Mengirim sinyal ke Supervisor...")
        
        # Buat koneksi broker HANYA untuk mengirim sinyal sukses
        broker = BrokerClient()
        if broker.is_connected:
            broker.publish("system.events", {"event": "LOGIN_SUCCESS"})
            broker.stop()
        else:
            print("[MainApp] ❌ Gagal mengirim sinyal login, tidak bisa terhubung ke broker.")

    else:
        # 6. Jika login dibatalkan atau gagal...
        print("[MainApp] ❌ Login dibatalkan.")
        # Supervisor akan timeout dan berhenti sendiri, tidak perlu aksi tambahan.
        
    print("[MainApp] Proses login selesai. Keluar.")
    sys.exit()

if __name__ == '__main__':
    main()