# Library/exit_strategies/dynamic_profit_protector.py

from typing import List, Dict, Tuple
import MetaTrader5 as mt5
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates

class DynamicProfitProtector:
    exit_name = "Dynamic Profit Protector (BE + ATR Trail)"
    
    live_status_labels = {
        "exit_status": "Exit Status:",
        "trailing_sl": "Trailing SL:"
    }
    
    parameters = {
        "breakeven_rr_ratio": {"display_name": "RR Ratio for Breakeven", "type": "float", "default": 1.0, "step": 0.1},
        "atr_trail_period": {"display_name": "ATR Trailing Period", "type": "int", "default": 14},
        "atr_trail_multiplier": {"display_name": "ATR Trailing Multiplier", "type": "float", "default": 3.0, "step": 0.1},
    }

    def __init__(self, mt5_instance, config: dict):
        self.mt5 = mt5_instance
        self.config = config
        self.log_messages = []

    def log_to_ui(self, symbol, message, level):
        self.log_messages.append((symbol, message, level))

    def check_exit_conditions(self, symbol: str, timeframe: int, open_positions: List, trade_journal: Dict) -> Tuple[List, Dict, Dict]:
        """
        [VERSI BARU] Menganalisis posisi dan mengembalikan:
        (tiket_untuk_ditutup, modifikasi_sl, data_status_live)
        """
        modifications = {}
        live_status = {"exit_status": "Monitoring", "trailing_sl": "-"}
        
        if not open_positions:
            return [], {}, live_status

        # Ambil data pasar dan hitung ATR
        atr_period = self.config.get("atr_trail_period", 14)
        df = get_rates(symbol, timeframe, count=atr_period + 50)
        if df.empty: return [], {}, live_status
        
        df.ta.atr(length=atr_period, append=True)
        atr_value = df.iloc[-1][f'ATRr_{atr_period}']
        tick = self.mt5.symbol_info_tick(symbol)
        if not tick: return [], {}, live_status

        for pos in open_positions:
            journal_entry = next((entry for entry in trade_journal.values() if entry.get('position_id') == pos.ticket), None)
            if not journal_entry or not journal_entry.get('entry_deal'): continue

            entry_price = journal_entry['entry_deal']['price']
            initial_sl = journal_entry['entry_deal']['sl']
            
            # --- LEVEL 1: LOGIKA BREAKEVEN ---
            if not journal_entry.get('breakeven_applied', False):
                initial_risk = abs(entry_price - initial_sl)
                breakeven_rr = self.config.get("breakeven_rr_ratio", 1.0)
                
                if pos.type == self.mt5.POSITION_TYPE_BUY and tick.bid >= entry_price + (initial_risk * breakeven_rr):
                    modifications[pos.ticket] = entry_price
                    self.log_to_ui(symbol, f"EXIT LVL 1: Moving SL to Breakeven for position #{pos.ticket}", "INFO")
                elif pos.type == self.mt5.POSITION_TYPE_SELL and tick.ask <= entry_price - (initial_risk * breakeven_rr):
                    modifications[pos.ticket] = entry_price
                    self.log_to_ui(symbol, f"EXIT LVL 1: Moving SL to Breakeven for position #{pos.ticket}", "INFO")

            # --- LEVEL 2: LOGIKA ATR TRAILING STOP ---
            # Dijalankan jika SL BUKAN di harga entry (artinya, belum breakeven atau sudah dilewati)
            else:
                atr_multiplier = self.config.get("atr_trail_multiplier", 3.0)
                new_sl = None
                
                if pos.type == self.mt5.POSITION_TYPE_BUY:
                    proposed_sl = tick.bid - (atr_value * atr_multiplier)
                    # Hanya pindahkan SL jika lebih tinggi dari SL saat ini
                    if proposed_sl > pos.sl:
                        new_sl = proposed_sl
                elif pos.type == self.mt5.POSITION_TYPE_SELL:
                    proposed_sl = tick.ask + (atr_value * atr_multiplier)
                    # Hanya pindahkan SL jika lebih rendah dari SL saat ini
                    if proposed_sl < pos.sl:
                        new_sl = proposed_sl
                
                if new_sl:
                    modifications[pos.ticket] = new_sl
                    live_status['trailing_sl'] = f"{new_sl:.5f}"
                    self.log_to_ui(symbol, f"EXIT LVL 2: Trailing SL for #{pos.ticket} to {new_sl:.5f}", "INFO")

        return [], modifications, live_status # Saat ini kita tidak menutup, hanya modifikasi SL