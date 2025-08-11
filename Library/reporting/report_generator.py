import pandas as pd
import json
from datetime import datetime
import os
import logging

# --- Konfigurasi Logger ---
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

class ReportGenerator:
    """
    [VERSI FINAL LENGKAP] Memproses data sesi yang telah diverifikasi dan menyimpannya 
    sebagai file JSON terstruktur yang kaya akan metrik analisis.
    """
    def __init__(self, reports_dir='reports'):
        """
        Inisialisasi Report Generator.

        Args:
            reports_dir (str): Nama folder untuk menyimpan file laporan JSON.
        """
        self.reports_dir = reports_dir
        # Membuat direktori jika belum ada, cara yang lebih aman.
        os.makedirs(self.reports_dir, exist_ok=True)
        
    def generate_session_report(self, session_data):
        """
        Membuat file laporan JSON lengkap dari data sesi yang telah selesai.
        
        Args:
            session_data (dict): Dictionary komprehensif dari TradeManager.
        
        Returns:
            str: Path ke file laporan JSON yang berhasil dibuat, atau None jika gagal.
        """
        account_number = session_data.get('account_info', {}).get('login', 'N/A')
        logger.info(f"Mulai membuat laporan lengkap untuk akun {account_number}...")
        
        trades = session_data.get('trades')
        if not isinstance(trades, list) or not trades:
            logger.warning("Tidak ada data trade untuk dilaporkan. Laporan tidak dibuat.")
            return None

        df = pd.DataFrame(trades)
        
        # --- 1. Kalkulasi Metrik Kinerja Dasar ---
        initial_balance = session_data.get('initial_balance', 0)
        final_equity = session_data.get('final_equity', initial_balance)
        
        pnl_currency = df['profit'].sum() + df['commission'].sum() + df['swap'].sum()
        pnl_percent = (pnl_currency / initial_balance) * 100 if initial_balance > 0 else 0
        
        total_trades = len(df)
        wins_df = df[df['profit'] >= 0]
        losses_df = df[df['profit'] < 0]
        
        winning_trades = len(wins_df)
        losing_trades = len(losses_df)
        
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_profit_gross = wins_df['profit'].sum()
        total_loss_gross = abs(losses_df['profit'].sum())
        profit_factor = total_profit_gross / total_loss_gross if total_loss_gross > 0 else float('inf')
        
        avg_win = wins_df['profit'].mean() if not wins_df.empty else 0
        avg_loss = abs(losses_df['profit'].mean()) if not losses_df.empty else 0
        
        expectancy = ((win_rate / 100) * avg_win) - ((100 - win_rate) / 100 * avg_loss)

        # --- 2. Kalkulasi Analisis Profesional Tambahan ---
        
        # P/L per Simbol
        pnl_by_symbol = df.groupby('symbol')['profit'].sum().round(2).to_dict()

        # Durasi Trade
        df['time_open_dt'] = pd.to_datetime(df.get('price_open', df['time']), unit='s')
        df['time_close_dt'] = pd.to_datetime(df['time'], unit='s')
        df['duration_seconds'] = (df['time_close_dt'] - df['time_open_dt']).dt.total_seconds()
        avg_trade_duration_seconds = df['duration_seconds'].mean() if not df.empty else 0

        # Max Consecutive Wins/Losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        for profit in df['profit']:
            if profit >= 0:
                current_wins += 1
                current_losses = 0
            else:
                current_losses += 1
                current_wins = 0
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
            max_consecutive_losses = max(max_consecutive_losses, current_losses)

        # --- 3. Susun Struktur File JSON Final ---
        report_content = {
            'summary': {
                'account_number': account_number,
                'session_start_time': session_data['session_start_time'].isoformat(),
                'session_end_time': session_data['session_end_time'].isoformat(),
                'generation_time': datetime.now().isoformat(),
                'initial_balance': initial_balance,
                'final_equity': final_equity,
                'pnl_currency': round(pnl_currency, 2),
                'pnl_percent': round(pnl_percent, 2),
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
            },
            'analytics': {
                'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
                'expectancy_per_trade': round(expectancy, 2),
                'average_win_currency': round(avg_win, 2),
                'average_loss_currency': round(avg_loss, 2),
                'pnl_per_symbol': pnl_by_symbol,
                'average_trade_duration_seconds': round(avg_trade_duration_seconds, 2),
                'max_consecutive_wins': max_consecutive_wins,
                'max_consecutive_losses': max_consecutive_losses,
            },
            'trades': df.to_dict('records')
        }

        # --- 4. Simpan File JSON ---
        try:
            filename = f"session_{account_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.reports_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_content, f, indent=4)
            
            logger.info(f"Laporan sesi JSON yang lengkap berhasil disimpan: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Gagal menyimpan file laporan JSON: {e}", exc_info=True)
            return None

    def generate_combined_report(self, account_number):
        """Placeholder untuk fungsi pembuatan laporan gabungan di masa depan."""
        logger.info(f"Fungsi laporan gabungan untuk akun {account_number} dipanggil. (Belum diimplementasikan)")
        pass