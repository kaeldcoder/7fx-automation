# Nama File: parallel_launcher.py

import subprocess
import platform
import itertools
import os
import math
import time
import sys
import json
import threading
import queue
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TaskProgressColumn
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.align import Align
import argparse

HISTORY_DIR = os.path.join('Backtester', 'History_Logs')

def load_history(symbol: str):
    """Memuat data histori dari file JSON spesifik untuk satu simbol."""
    history_file = os.path.join(HISTORY_DIR, f"{symbol}_history.json")
    try:
        if not os.path.exists(history_file):
            return {} # Kembalikan dictionary kosong jika file belum ada
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_history(symbol: str, data: dict):
    """Menyimpan data histori ke file JSON spesifik untuk satu simbol."""
    os.makedirs(HISTORY_DIR, exist_ok=True) # Pastikan folder histori ada
    history_file = os.path.join(HISTORY_DIR, f"{symbol}_history.json")
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def get_run_id(params: dict) -> str:
    """ID unik kombinasi parameter (toleran nama lama/baru)."""
    def pick(*names, default=None):
        for n in names:
            if n in params and params.get(n) is not None:
                return params.get(n)
        return default

    use_adx = bool(pick('use_adx', 'use_adx_filter', default=False))
    use_sl  = bool(pick('use_sl', 'use_stop_loss', default=False))

    norm = {
        'lot_size':    pick('lot_size', 'fixed_lot_size'),
        'start_time':  pick('start_time', 'trade_start_time'),
        'end_time':    pick('end_time', 'trade_end_time'),
        'wave_period': pick('wave_period'),
        'use_adx':     use_adx,
        'adx_threshold': pick('adx_threshold') if use_adx else None,
        'use_sl':      use_sl,
        'sl_points':   pick('sl_points', 'stop_loss_points') if use_sl else None,
    }
    return json.dumps(norm, sort_keys=True)

def simulate_equity_stops(equity_curve, initial_balance, gain_target_percent, loss_limit_percent):
    if not equity_curve: return "Data kurva ekuitas tidak tersedia."

    def to_dt(x):
        if isinstance(x, (int, float)):   # epoch-ms
            return datetime.fromtimestamp(float(x)/1000.0)
        if isinstance(x, str):            # ISO 8601
            return datetime.fromisoformat(x)
        return x                          # sudah datetime

    try:
        equity_curve_dt = [(to_dt(t), float(e)) for t, e in equity_curve]
    except Exception:
        return "Format data kurva ekuitas tidak valid."

    gt = initial_balance * (1 + gain_target_percent/100)
    sl = initial_balance * (1 - loss_limit_percent/100)
    for dt, bal in equity_curve_dt:
        if bal >= gt: return f"✅ TP {gain_target_percent}% Equity Tercapai: {dt:%Y-%m-%d}"
        if bal <= sl: return f"❌ SL {loss_limit_percent}% Equity Tersentuh: {dt:%Y-%m-%d}"
    return "Equity tidak menyentuh target TP/SL."

def output_reader(proc, out_queue):
    """Membaca output dari proses dan memasukkannya ke dalam queue."""
    try:
        for line in iter(proc.stdout.readline, b''):
            out_queue.put(line.decode('utf-8').strip())
    except Exception as e:
        # Mungkin terjadi error jika pipe ditutup secara tak terduga
        out_queue.put(json.dumps({"status": f"Reader error: {e}", "progress": 1, "total": 1}))

def run_parallel_backtests(symbol: str, symbol_history: dict):
    error_log_path = os.path.join('Backtester', 'error_log.txt')
    if os.path.exists(error_log_path):
        os.remove(error_log_path)
    console = Console()
    # =================================================================
    # >> AREA KONFIGURASI <<
    # =================================================================
    BATCH_SIZE = 3
    # --- PERUBAHAN 1: Gunakan variabel 'symbol' yang diterima dari argumen ---
    base_params = {
        'symbol': symbol, 'year': 2025,
        'initial_balance': 10000.0,
        'start_month': 1, 'end_month': 7,
    }
    optimization_params = {
        'lot_size': [0.5, 1.0],
        'start_time': ['16:30'],
        'end_time': ['19:30'],
        'wave_period': [54], 
        'adx_period': [15],
        # 'sl_points': [5.0, 10.0, 15.0, 20.0],
        'use_adx': [True], 
        'use_sl': [False]
    }
    # =================================================================

    keys, values = zip(*optimization_params.items())
    all_possible_combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    total_possible = len(all_possible_combinations)

    # --- Logika filter yang sekarang akan bekerja karena `symbol_history` sudah didefinisikan ---
    console.print("[yellow]Mengecek histori untuk melewati backtest yang sudah ada...[/yellow]")
    past_runs = symbol_history.get('all_runs', [])
    past_run_ids = {get_run_id(run['parameters']) for run in past_runs}

    combinations_to_run = []
    for params in all_possible_combinations:
        full_params_for_id = {**base_params, **params}
        run_id = get_run_id(full_params_for_id)
        if run_id not in past_run_ids:
            combinations_to_run.append(params)

    num_to_run = len(combinations_to_run)
    num_skipped = total_possible - num_to_run
    
    # --- Panel konfirmasi yang sekarang akan bekerja karena `symbol` sudah didefinisikan ---
    if num_to_run == 0:
        console.print(Panel(f"[bold green]✅ SEMUA {total_possible} KOMBINASI UNTUK {symbol} SUDAH PERNAH DI-BACKTEST.[/bold green]\nTidak ada proses baru yang perlu dijalankan.", 
            title="[bold blue]Status Proses[/bold blue]", expand=False))
        return None 

    panel_info = (
        f"[bold]Total Semua Kombinasi Parameter:[/bold] {total_possible}\n"
        f"[bold yellow]Sudah Pernah Dites (Dilewati):[/bold yellow] {num_skipped}\n"
        f"--------------------------------------------------\n"
        f"[bold green]Akan Dites Sekarang:[/bold green] {num_to_run}\n\n"
        f"[bold]Ukuran Batch:[/bold] {BATCH_SIZE} proses/kelompok\n"
        f"[bold]Total Batch Baru:[/bold] {math.ceil(num_to_run / BATCH_SIZE)}"
    )
    console.print(Panel(panel_info, title="[bold blue]Konfigurasi Tes Paralel (Update)[/bold blue]", expand=False))

    try:
        if console.input("\n[bold]Lanjutkan? (y/n):[/bold] ").lower() != 'y':
            console.print("[yellow]Proses dibatalkan.[/yellow]"); return None
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Proses dibatalkan.[/yellow]"); return None

    # --- Sisa kode di bawah ini sudah benar dan tidak perlu diubah ---
    launcher_dir = os.path.dirname(os.path.abspath(__file__))
    worker_script_path = os.path.join(launcher_dir, 'worker_backtest.py')
    python_executable = sys.executable
    total_completed = 0
    progress_bar = Progress(TextColumn("[bold blue]Total Progress:"), BarColumn(bar_width=None), TaskProgressColumn(), TextColumn("•"), TimeElapsedColumn())
    main_task = progress_bar.add_task("Processing...", total=num_to_run)
    
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main_progress", size=3),
        Layout(name="active_tasks", ratio=2),
        Layout(name="footer", ratio=1, minimum_size=5)
    )
    layout["header"].update(Align.center(f"[bold]Memulai Backtest Paralel untuk [cyan]{symbol}[/cyan][/bold]")) # Menggunakan `symbol` dari argumen
    layout["main_progress"].update(progress_bar)
    layout["footer"].update(Panel("Menunggu proses... Laporan error akan muncul di sini jika ada.", title="[yellow]Log Error[/yellow]"))
    
    error_logs = []

    with Live(layout, console=console, screen=True, redirect_stderr=False, vertical_overflow="visible") as live:
        for i in range(0, num_to_run, BATCH_SIZE):
            batch = combinations_to_run[i:i + BATCH_SIZE]
            current_batch_num = (i // BATCH_SIZE) + 1
            total_batches = math.ceil(num_to_run / BATCH_SIZE)
            active_processes = {}

            for params in batch:
                current_params = {**base_params, **params}
                cmd_args_list = []
                for key, value in current_params.items():
                    if isinstance(value, bool) and value: cmd_args_list.append(f'--{key}')
                    elif not isinstance(value, bool): cmd_args_list.append(f'--{key} {value}')
                
                command_list = [python_executable, worker_script_path] + " ".join(cmd_args_list).split()
                proc = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.path.dirname(launcher_dir))

                q = queue.Queue()
                t = threading.Thread(target=output_reader, args=(proc, q))
                t.daemon = True
                t.start()

                param_str = ", ".join(f"{k}={v}" for k,v in params.items())
                active_processes[proc] = {
                    "params": param_str,
                    "queue": q,
                    "thread": t,
                    "status_msg": "Inisialisasi...",
                    "progress": 0,
                    "total": 1
                }

            while active_processes:
                task_table = Table(title=f"Batch {current_batch_num}/{total_batches}", expand=True)
                task_table.add_column("No.", style="magenta", width=5)
                task_table.add_column("Parameter Aktif", style="cyan", ratio=3)
                task_table.add_column("Status Terkini", style="yellow", ratio=2)
                task_table.add_column("Progress Langkah", style="green", ratio=2)

                for proc, data in active_processes.items():
                    try:
                        while True: 
                            line = data["queue"].get_nowait()
                            try:
                                status_data = json.loads(line)
                                data["status_msg"] = status_data.get("status", data["status_msg"])
                                data["progress"] = status_data.get("progress", data["progress"])
                                data["total"] = status_data.get("total", data["total"])
                            except json.JSONDecodeError:
                                data["status_msg"] = line 
                    except queue.Empty:
                        pass

                done_procs = []
                for idx, (proc, data) in enumerate(active_processes.items()):
                    if proc.poll() is not None:
                        done_procs.append(proc)
                        total_completed += 1
                        if proc.returncode != 0:
                            data['thread'].join(timeout=1)
                            stderr_output = proc.stderr.read()
                            error_message = stderr_output.decode('utf-8', errors='ignore').strip()
                            full_error_log = f"❌ Error pada Parameter: {data['params']}\n---\n{error_message}\n\n"
                            with open(error_log_path, 'a', encoding='utf-8') as f:
                                f.write(full_error_log)
                            error_logs.append(f"❌ [bold red]Error pada: {data['params']}[/bold red] (Detail lihat di {error_log_path})")
                            layout["footer"].update(Panel("\n".join(error_logs), title="[yellow]Log Error[/yellow]", border_style="yellow"))
                    else:
                        step_progress = Progress(BarColumn(), TextColumn("{task.completed}/{task.total}"))
                        step_progress.add_task("step", total=data['total'], completed=data['progress'])
                        task_table.add_row(
                            str(idx + 1), 
                            data['params'], 
                            data['status_msg'],
                            step_progress
                        )
                
                for proc in done_procs:
                    del active_processes[proc]
                
                progress_bar.update(main_task, completed=total_completed)
                layout["active_tasks"].update(Align.center(task_table))
                time.sleep(0.5)

    console.print(Panel("[bold green]✅ SEMUA PROSES BACKTEST BARU TELAH SELESAI.[/bold green]"))
    return num_to_run

def display_result_panel(result, title, console):
    """Fungsi bantuan untuk menampilkan panel hasil yang diformat dengan rapi."""
    if not result:
        # Jika tidak ada hasil (misal: tidak ada yang profit untuk kategori 'paling aman')
        console.print(Panel(f"[yellow]Tidak ditemukan kandidat yang valid untuk kategori ini.[/yellow]",
            title=f"⚠️ {title} ⚠️", expand=False, border_style="yellow"))
        print("\n")
        return

    params = result.get('parameters', {})
    param_str = (
        f"Lot Size: {params.get('fixed_lot_size')}, "
        f"Wave Period: {params.get('wave_period')}, "
        f"Start Time: {params.get('trade_start_time')}, "
        f"End Time: {params.get('trade_end_time')}\n"
        f"Use ADX: {params.get('use_adx_filter')} (T:{params.get('adx_threshold')}), "
        f"Use SL: {params.get('use_stop_loss')} (P:{params.get('stop_loss_points')})"
    )

    drawdown_details = result.get('total_drawdown_details')
    if drawdown_details:
        dd_percent = drawdown_details.get('percentage', 0)
        dd_value = drawdown_details.get('value', 0)
        dd_peak = drawdown_details.get('peak_equity', 0)
        dd_trough = drawdown_details.get('trough_equity', 0)
        dd_start = drawdown_details.get('start_date', 'N/A')
        dd_end = drawdown_details.get('end_date', 'N/A')
        drawdown_str = (
            f"[bold red]Max Drawdown: {dd_percent:,.2f}% (${dd_value:,.2f})[/bold red]\n"
            f"    (Peak: ${dd_peak:,.2f} pada {dd_start} | Trough: ${dd_trough:,.2f} pada {dd_end})"
        )
    else:
        # Penanganan untuk format data lama jika masih ada
        drawdown_str = f"[bold red]Max Drawdown: {result.get('max_drawdown', 'N/A'):.2f}%[/bold red]"

    equity_curve = result.get('equity_curve_data', [])
    initial_balance = params.get('initial_balance', 10000.0)
    simulation_info = simulate_equity_stops(equity_curve, initial_balance, 30, 15) # Target 30% TP, 15% SL

    dynamics = result.get('trading_dynamics', {})
    profit_factor = dynamics.get('profit_factor', 0)
    payoff_ratio = dynamics.get('payoff_ratio', 0)
    max_losses = dynamics.get('max_consecutive_losses', 0)
    sharpe_ratio = dynamics.get('sharpe_ratio', 0)

    # Hitung metrik tambahan
    total_profit = result.get('total_profit', 0)
    total_trades = result.get('total_trades', 0)
    roi_percent = (total_profit / initial_balance) * 100 if initial_balance > 0 else 0
    avg_profit_per_trade = total_profit / total_trades if total_trades > 0 else 0

    stats_line_1 = (
        f"[bold]Win Rate:[/bold] {result.get('overall_win_rate', 0):.2f}%{'':<10}"
        f"[bold]Profit Factor:[/bold] {profit_factor:.2f}{'':<10}"
        f"[bold]Payoff Ratio:[/bold] {payoff_ratio:.2f}"
    )
    stats_line_2 = (
        f"[bold]Total Trades:[/bold] {total_trades:<10}"
        f"[bold]Avg Profit/Trade:[/bold] ${avg_profit_per_trade:,.2f}{'':<5}"
        f"[bold]Max Loss Streak:[/bold] {max_losses} trades"
    )

    console.print(Panel(
        f"[bold green]Total Profit: ${total_profit:,.2f}[/bold green] ([bold cyan]ROI: {roi_percent:.2f}%[/bold cyan])\n"
        f"{drawdown_str}\n"
        f"[bold][blue]Skor Keseimbangan:[/blue][/bold] {result.get('balance_score', 'N/A'):.2f}{'':<5}"
        f"[bold][purple]Sharpe Ratio:[/purple][/bold] {sharpe_ratio:.2f}{'':<5}\n\n"
        # --- BLOK STATISTIK BARU ---
        f"{stats_line_1}\n"
        f"{stats_line_2}\n\n"
        # --- AKHIR BLOK STATISTIK ---
        f"[bold]Parameter Terbaik:[/bold]\n{param_str}\n\n"
        f"[bold]Laporan PDF Lengkap:[/bold]\n[cyan]{result.get('pdf_report_path', 'N/A')}[/cyan]",
        title=title,
        expand=False,
        border_style="yellow"
    ))


def main():
    """Fungsi utama yang dirombak total untuk mengelola alur kerja baru."""
    # --- Langkah 0: Parsing Argumen ---
    parser = argparse.ArgumentParser(description="Menjalankan backtest paralel untuk simbol tertentu.")
    parser.add_argument('--symbol', type=str, required=True, help='Simbol trading untuk di backtest, misal: XAUUSD')
    args = parser.parse_args()
    symbol = args.symbol
    console = Console()
    console.set_window_title(f"Backtester - {symbol}")

    # --- Langkah 1: Muat & Tampilkan Histori Lama ---
    console.print(Panel(f"[bold]Membaca histori dari file untuk [cyan]{symbol}[/cyan]...[/bold]", border_style="blue"))
    symbol_history = load_history(symbol) # Langsung load file spesifik
    best_results_old = symbol_history.get('best_results', {})

    if not best_results_old:
        console.print(f"[yellow]Belum ada histori backtest ditemukan untuk {symbol}.[/yellow]\n")
    else:
        console.print("[bold]--------------- 🏆 HASIL TERBAIK TERAKHIR 🏆 ---------------[/bold]")
        display_result_panel(best_results_old.get('most_balanced'), f"⚖️ {symbol}: Paling Seimbang (Lama)", console)
        display_result_panel(best_results_old.get('most_profitable'), f"💰 {symbol}: Profit Tertinggi (Lama)", console)
        display_result_panel(best_results_old.get('safest_profitable'), f"🛡️ {symbol}: Paling Aman (Lama)", console)

    # --- Langkah 2: Jalankan Backtest Baru ---
    start_time = time.time()
    num_combinations_run = run_parallel_backtests(symbol, symbol_history)
    if num_combinations_run is None:
        console.print("[yellow]Tidak ada backtest baru yang dijalankan.[/yellow]")
        return
    end_time = time.time()
    
    # --- Langkah 3: Analisis, Gabungkan, dan Simpan Hasil ---
    console.print(Panel(f"[bold]Menganalisis & Menggabungkan Hasil untuk [cyan]{symbol}[/cyan]...[/bold]", style="cyan"))
    results_path = os.path.join('Backtester', 'Hasil Laporan PDF', symbol)
    newly_completed_results = []
    
    if os.path.exists(results_path):
        for root, _, files in os.walk(results_path):
            if 'result.json' in files:
                try:
                    with open(os.path.join(root, 'result.json'), 'r') as f:
                        data = json.load(f)
                        profit = data.get('total_profit', 0)
                        dd_details = data.get('total_drawdown_details')
                        if dd_details and 'percentage' in dd_details:
                            drawdown = dd_details.get('percentage', 100)
                        else:
                            # Jika tidak ada, gunakan fallback ke format lama
                            drawdown = data.get('max_drawdown', 100)
                        data['balance_score'] = (profit / drawdown) if drawdown > 0.01 else (profit * 1000)
                        if 'max_drawdown' not in data:
                            data['max_drawdown'] = drawdown
                        newly_completed_results.append(data)
                except Exception as e:
                    console.print(f"[bold red]Error membaca file JSON di {root}: {e}[/bold red]")

    # --- Gabungkan dengan histori lama, hindari duplikat ---
    all_runs_for_symbol = symbol_history.get('all_runs', [])
    existing_run_ids = {get_run_id(run['parameters']) for run in all_runs_for_symbol}

    for new_run in newly_completed_results:
        run_id = get_run_id(new_run['parameters'])
        if run_id not in existing_run_ids:
            all_runs_for_symbol.append(new_run)

    if not all_runs_for_symbol:
        console.print(f"[bold red]Tidak ada hasil backtest yang bisa dianalisis untuk {symbol}.[/bold red]")
        return

    # --- Langkah 4: Cari Juara Baru dari SEMUA data (lama + baru) ---
    console.print("[bold]--------------- 🥇 HASIL TERBAIK KESELURUHAN (UPDATE) 🥇 ---------------[/bold]")
    
    # 1. Paling Seimbang
    best_balance_result = max(all_runs_for_symbol, key=lambda x: x.get('balance_score', -float('inf')))
    display_result_panel(best_balance_result, f"⚖️ {symbol}: Paling Seimbang (Terbaru)", console)
    
    # 2. Profit Tertinggi
    best_profit_result = max(all_runs_for_symbol, key=lambda x: x.get('total_profit', -float('inf')))
    display_result_panel(best_profit_result, f"💰 {symbol}: Profit Tertinggi (Terbaru)", console)

    # 3. Paling Aman (Drawdown Terendah dari yang Profit)
    profitable_results = [r for r in all_runs_for_symbol if r.get('total_profit', 0) > 0]
    safest_result = min(profitable_results, key=lambda x: x.get('max_drawdown', float('inf'))) if profitable_results else None
    display_result_panel(safest_result, f"🛡️ {symbol}: Paling Aman & Profit (Terbaru)", console)

    # --- Langkah 5: Simpan Histori yang Sudah Diperbarui ---
    new_symbol_history_data = {
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'best_results': {
            'most_balanced': best_balance_result,
            'most_profitable': best_profit_result,
            'safest_profitable': safest_result
        },
        'all_runs': all_runs_for_symbol
    }
    save_history(symbol, new_symbol_history_data)
    history_file_path = os.path.join(HISTORY_DIR, f"{symbol}_history.json")
    console.print(f"\n[bold green]✅ Histori untuk {symbol} telah diperbarui di [cyan]{history_file_path}[/cyan][/bold green]")

    # --- Laporan Kinerja Program (tetap sama) ---
    total_duration = end_time - start_time
    minutes, seconds = divmod(total_duration, 60)
    console.print(Panel(
        f"Total Kombinasi Dites Sesi Ini: [bold yellow]{num_combinations_run}[/bold yellow]\n" # <--- PERUBAHAN DI SINI
        f"Total Waktu Eksekusi Sesi Ini: [bold yellow]{int(minutes)} menit {int(seconds)} detik[/bold yellow]",
        title=f"📊 [bold green]Laporan Kinerja Program - {symbol}[/bold green] 📊",
        expand=False
    ))


if __name__ == '__main__':
    
    from rich.panel import Panel
    from rich.console import Console
    main()