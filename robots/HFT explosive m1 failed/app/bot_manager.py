# app/bot_manager.py

import subprocess
import sys
import time
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
GRANDPARENT_ROOT = os.path.dirname(PARENT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
if GRANDPARENT_ROOT not in sys.path:
    sys.path.append(GRANDPARENT_ROOT)


from services.broker_client import BrokerClient

class BotManager:
    def __init__(self):
        print("🚀 Manajer Proses Bot dimulai...")
        self.broker = BrokerClient()
        self.running_bot_processes = {} # Format: { "acc_number": process_object }

        if not self.broker.is_connected:
            print("❌ Manajer Bot tidak bisa berjalan tanpa koneksi ke Broker. Keluar.")
            sys.exit(1)

        # Berlangganan ke topik perintah dari dashboard UI
        self.broker.subscribe("dashboard.commands", self._handle_command)

    def _handle_command(self, message: dict):
        """Menangani perintah yang masuk dari Dashboard UI."""
        command = message.get("command")
        account_number = message.get("account_number")

        print(f"📥 Menerima perintah '{command}' untuk akun {account_number}")

        if command == "launch_bot":
            self.launch_bot(account_number)
        elif command == "kill_bot":
            self.kill_bot(account_number)
        else:
            print(f"⚠️ Perintah tidak dikenali: {command}")

    def launch_bot(self, account_number: str):
        """Meluncurkan proses bot trading untuk akun tertentu."""
        if account_number in self.running_bot_processes:
            print(f"⚠️ Peringatan: Proses untuk akun {account_number} sudah berjalan.")
            return

        try:
            # Path ke skrip peluncur bot
            bot_launcher_script = os.path.join(PROJECT_ROOT, 'run_bot_process.py')
            
            # Menjalankan skrip sebagai proses baru
            process = subprocess.Popen([sys.executable, bot_launcher_script, account_number])
            
            self.running_bot_processes[account_number] = process
            print(f"✅ Bot untuk akun {account_number} diluncurkan dengan PID: {process.pid}")
            # Kirim status kembali ke UI bahwa proses sedang inisialisasi
            self.broker.publish("bot.status", {"account_number": account_number, "status": "Standby"})

        except Exception as e:
            print(f"❌ GAGAL meluncurkan bot untuk akun {account_number}: {e}")

    def kill_bot(self, account_number: str):
        """Mematikan paksa proses bot untuk akun tertentu."""
        process = self.running_bot_processes.get(account_number)
        if process:
            print(f"🛑 Mematikan paksa bot untuk akun {account_number} (PID: {process.pid})...")
            process.terminate()
            # Hapus dari daftar setelah dimatikan
            del self.running_bot_processes[account_number]
            self.broker.publish("bot.status", {"account_number": account_number, "status": "KILLED"})
        else:
            print(f"⚠️ Peringatan: Tidak ada proses berjalan untuk akun {account_number} untuk dimatikan.")

    def run_manager(self):
        """Loop utama untuk manajer."""
        try:
            while True:
                # TODO: Tambahkan logika watchdog untuk memeriksa kesehatan bot di sini
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Manajer Proses Bot menerima sinyal berhenti. Membersihkan...")
            for acc_num in list(self.running_bot_processes.keys()):
                self.kill_bot(acc_num)
            self.broker.stop()
            print("👋 Manajer Proses Bot berhenti.")

if __name__ == "__main__":
    manager = BotManager()
    manager.run_manager()