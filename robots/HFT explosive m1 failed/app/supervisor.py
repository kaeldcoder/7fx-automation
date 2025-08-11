# app/supervisor.py

import subprocess
import sys
import time
import os
import threading

# Konfigurasi Path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if GRANDPARENT_ROOT not in sys.path:
    sys.path.append(GRANDPARENT_ROOT)


from services.broker_client import BrokerClient

class Supervisor:
    def __init__(self):
        self.processes_to_manage = {
            "Dashboard_UI": "ui/main_dashboard_ui.py",
            "Bot_Manager": "app/bot_manager.py",
        }
        self.active_processes = {}
        self.login_confirmed = threading.Event() # Gunakan Event untuk sinkronisasi thread
        self.broker = BrokerClient()

    def _handle_system_events(self, message: dict):
        """Callback untuk menangani pesan di topik 'system.events'."""
        event = message.get("event")
        if event == "LOGIN_SUCCESS":
            print("[Supervisor] ✅ Sinyal LOGIN_SUCCESS diterima. Melanjutkan startup...")
            self.login_confirmed.set() # Set event, memberitahu loop utama untuk lanjut

    def run(self):
        """Loop utama untuk mengawasi dan me-restart proses."""
        print("🚀 Supervisor dimulai. Menunggu konfirmasi login...")
        
        if not self.broker.is_connected:
            print("❌ Supervisor tidak bisa berjalan tanpa koneksi ke Broker. Keluar.")
            return

        # Berlangganan ke event sistem dan umumkan bahwa supervisor sudah siap
        self.broker.subscribe("system.events", self._handle_system_events)
        self.broker.publish("system.events", {"event": "SUPERVISOR_READY"})

        # Tunggu sinyal login berhasil (dengan timeout 5 menit)
        login_was_successful = self.login_confirmed.wait(timeout=300) 

        if not login_was_successful:
            print("❌ Supervisor tidak menerima sinyal login dalam 5 menit. Timeout.")
            self.stop()
            return
            
        # Setelah login dikonfirmasi, mulai loop pengawasan proses
        try:
            while True:
                for name, script_path in self.processes_to_manage.items():
                    process = self.active_processes.get(name)
                    
                    if process is None or process.poll() is not None:
                        if process is not None:
                            print(f"[{name}] ⚠️ Proses dengan PID {process.pid} terdeteksi mati. Me-restart...")
                        
                        self.active_processes[name] = self._start_process(name, script_path)
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            self.stop()

    def _start_process(self, name, script_path):
        """Fungsi untuk meluncurkan sebuah proses."""
        full_path = os.path.join(PROJECT_ROOT, script_path)
        if not os.path.exists(full_path):
            print(f"[{name}] ❌ Peringatan: Script tidak ditemukan di {full_path}. Proses tidak dapat dimulai.")
            return None
        
        process = subprocess.Popen([sys.executable, full_path])
        print(f"[{name}] ✅ Proses dimulai dengan PID: {process.pid}")
        return process

    def stop(self):
        """Menghentikan semua proses yang dikelola."""
        print("\n🛑 Supervisor menerima sinyal berhenti. Mematikan semua proses...")
        for name, process in self.active_processes.items():
            if process and process.poll() is None:
                print(f"   -> Menghentikan [{name}] dengan PID {process.pid}...")
                process.terminate()
        self.broker.stop()
        print("👋 Semua proses telah dihentikan. Supervisor keluar.")

if __name__ == "__main__":
    supervisor = Supervisor()
    supervisor.run()