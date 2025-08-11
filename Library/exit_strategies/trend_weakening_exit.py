import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from typing import List, Dict, Tuple

# Impor fungsi kustom Anda untuk mendapatkan data
from Library.data_handler.data_handler import get_rates

class TrendWeakeningExit:
    """
    Modul Smart Exit yang akan menutup posisi profit
    saat tren menunjukkan tanda-tanda pelemahan.
    """
    # Nama yang akan muncul di UI Dropdown
    exit_name = "Exit on Weakening Trend (ADX + EMA)"

    live_status_labels = {
        "exit_trend_status": "Trend Status (Exit):",
        "exit_adx_value": "ADX Value (Exit):"
    }
    
    # Definisikan parameter yang dibutuhkan oleh modul exit ini
    # Ini akan digunakan oleh SettingsWindow untuk membuat UI dinamis
    parameters = {
        "exit_ema_period": {"display_name": "Exit EMA Period", "type": "int", "default": 50, "min": 10, "max": 200},
        "exit_adx_period": {"display_name": "Exit ADX Period", "type": "int", "default": 14, "min": 5, "max": 50},
        "exit_adx_threshold": {"display_name": "Exit ADX Threshold", "type": "int", "default": 25, "min": 15, "max": 40},
    }

    def __init__(self, mt5_instance, config: dict):
        self.mt5 = mt5_instance
        self.config = config
        self.log_messages = []
    
    def log_to_ui(self, symbol, message, level):
        """Menyimpan pesan log untuk diambil oleh BotWorker."""
        self.log_messages.append((symbol, message, level))

    def check_exit_conditions(self, symbol: str, timeframe: int, open_positions: list, trade_journal: Dict) -> Tuple[List, Dict, Dict]:
        """
        [VERSI BARU] Menganalisis pasar dan posisi terbuka.
        Mengembalikan: (tiket_untuk_ditutup, modifikasi_sl, data_status_live)
        """
        live_status = {
            "exit_trend_status": "-",
            "exit_adx_value": "-"
        }

        profitable_positions = [p for p in open_positions if p.profit > 0]
        if not profitable_positions:
            # [PERBAIKAN] Kembalikan 3 nilai
            return [], {}, live_status

        ema_period = self.config.get("exit_ema_period", 50)
        adx_period = self.config.get("exit_adx_period", 14)
        
        required_data_count = max(ema_period, adx_period) + 50
        df = get_rates(symbol, timeframe, count=required_data_count)

        if df.empty:
            print(f"Warning (Smart Exit): Failed to retrieve data for {symbol}")
            # [PERBAIKAN] Kembalikan 3 nilai
            return [], {}, live_status
            
        df.ta.ema(length=ema_period, append=True)
        df.ta.adx(length=adx_period, append=True)

        last_bar = df.iloc[-1]
        tick = self.mt5.symbol_info_tick(symbol)
        if not tick:
            # [PERBAIKAN] Kembalikan 3 nilai
            return [], {}, live_status
        
        ema_col = f'EMA_{ema_period}'
        adx_col = f'ADX_{adx_period}'
        
        current_adx = last_bar[adx_col]
        live_status["exit_adx_value"] = f"{current_adx:.2f}"

        is_trend_weakening = current_adx < self.config.get("exit_adx_threshold", 25)
        live_status["exit_trend_status"] = "Weakening" if is_trend_weakening else "strengthening"

        positions_to_close = []
        if is_trend_weakening:
            for pos in profitable_positions:
                is_buy_position = pos.type == self.mt5.POSITION_TYPE_BUY
                is_sell_position = pos.type == self.mt5.POSITION_TYPE_SELL
                
                price_crossed_below_ema = tick.bid < last_bar[ema_col]
                price_crossed_above_ema = tick.ask > last_bar[ema_col]

                if (is_buy_position and price_crossed_below_ema) or \
                   (is_sell_position and price_crossed_above_ema):
                    self.log_to_ui(symbol, f"SMART EXIT: Marking position #{pos.ticket} for closure.")
                    positions_to_close.append(pos.ticket)

        # [PERBAIKAN] Kembalikan 3 nilai, dengan modifikasi SL sebagai dictionary kosong
        return positions_to_close, {}, live_status