# Nama File: master_launcher.py
import subprocess
import platform
import os
import sys
import time
from rich.console import Console
from rich.panel import Panel

# ===============================================================
# >> AREA KONFIGURASI <<
# Masukkan semua pair yang ingin di-backtest secara bersamaan
# ===============================================================
PAIRS_TO_TEST = ['XAUUSD', 'EURUSD'] 
# ===============================================================


# --- PERBAIKAN 1: Tambahkan 'console' sebagai argumen ---
def launch_for_pair(symbol: str, console: Console):
    """Mendeteksi OS dan meluncurkan terminal baru untuk satu pair."""
    launcher_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parallel_launcher.py')
    python_executable = sys.executable
    
    # --- PERBAIKAN 1: Gunakan console.print ---
    console.print(f"Mencoba meluncurkan terminal untuk [bold cyan]{symbol}[/bold cyan]...")
    
    os_name = platform.system()
    
    try:
        if os_name == "Windows":
            # --- PERBAIKAN 2: Tambahkan tanda kutip untuk path Windows ---
            quoted_python = f'"{python_executable}"'
            quoted_script = f'"{launcher_script}"'
            
            # Gabungkan menjadi satu perintah yang aman untuk cmd
            final_command = f"{quoted_python} -m Backtester.parallel_launcher --symbol {symbol}"
            
            # Jalankan dengan 'start' untuk window baru
            # '/k' menjaga window tetap terbuka
            subprocess.Popen(f'start "Backtest for {symbol}" cmd /k {final_command}', shell=True)
            
        elif os_name == "Darwin": # macOS
            command_list = [python_executable, '-m', 'Backtester.parallel_launcher', '--symbol', symbol]
            command_str = " ".join(f'"{arg}"' for arg in command_list)
            apple_script = f'tell app "Terminal" to do script {command_str}'
            subprocess.Popen(['osascript', '-e', apple_script])
            
        else: # Linux
            command_list = [python_executable, '-m', 'Backtester.parallel_launcher', '--symbol', symbol]
            subprocess.Popen(['gnome-terminal', '--'] + command_list)
        
        # --- PERBAIKAN 1: Gunakan console.print ---
        console.print(f"✅ Terminal untuk [bold green]{symbol}[/bold green] berhasil diluncurkan.")
        
    except FileNotFoundError:
        console.print(f"❌ [bold red]Error:[/bold red] Perintah untuk membuka terminal tidak ditemukan.")
    except Exception as e:
        console.print(f"❌ Gagal meluncurkan terminal untuk {symbol}: {e}")

if __name__ == '__main__':
    console = Console()
    
    console.print(Panel("[bold blue]🚀 Master Backtest Launcher 🚀[/bold blue]", expand=False))
    
    if not PAIRS_TO_TEST:
        console.print("⚠️ [yellow]Tidak ada pair yang dikonfigurasi di dalam `PAIRS_TO_TEST`. Edit file master_launcher.py.[/yellow]")
    else:
        console.print(f"Akan meluncurkan backtest untuk pair: [bold]{', '.join(PAIRS_TO_TEST)}[/bold]\n")
        for pair in PAIRS_TO_TEST:
            # --- PERBAIKAN 1: Kirim 'console' ke dalam fungsi ---
            launch_for_pair(pair, console)
            time.sleep(1) 
    
    console.print("\n[bold green]🏁 Semua terminal telah diminta untuk diluncurkan.[/bold green]")