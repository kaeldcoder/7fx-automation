# Library/strategies/bb_macd_counter.py

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

class BbMacdCounter:
    # Nama yang akan muncul di UI Dropdown
    strategy_name = "Counter-Trend (Bollinger + MACD)"

    # Label yang akan ditampilkan di MonitoringWindow
    live_status_labels = {
        "condition": "Market Condition:",
        "bb_position": "BB Position:",
        "macd_value": "MACD Value:"
    }
    
    # Parameter yang akan muncul dinamis di SettingsWindow
    parameters = {
        "bb_fast_period": {"display_name": "Fast BB Period", "type": "int", "default": 20},
        "bb_fast_std": {"display_name": "Fast BB Deviation", "type": "float", "default": 2.0, "step": 0.1},
        "bb_slow_period": {"display_name": "Slow BB Period", "type": "int", "default": 100},
        "bb_slow_std": {"display_name": "Slow BB Deviation", "type": "float", "default": 2.0, "step": 0.1},
        "macd_fast": {"display_name": "Fast MACD Period", "type": "int", "default": 12},
        "macd_slow": {"display_name": "Slow MACD Period", "type": "int", "default": 26},
        "macd_signal": {"display_name": "MACD Signal Period", "type": "int", "default": 9},
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0, "step": 0.1},
    }

    def __init__(self, mt5_instance, config: dict, analyzer: SpreadAnalyzer):
        self.mt5 = mt5_instance
        self.config = config
        self.analyzer = analyzer
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe_int')

    def check_signal(self, open_positions_count: int = 0):
        tick = self.mt5.symbol_info_tick(self.symbol)
        symbol_info = get_symbol_info(self.symbol)

        if symbol_info:
            self.analyzer.add_spread(symbol_info.spread)

        status = {
            "symbol": self.symbol,
            "price": tick.bid if tick else 0,
            "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {self.analyzer.average_spread:.1f})",
            "condition": "Analyzing...", "bb_position": "-", "macd_value": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        status["price"] = tick.bid
        self.analyzer.add_spread(symbol_info.spread)
        status["spread_info"] = f"{symbol_info.spread} (Avg: {self.analyzer.average_spread:.1f})"

        

        # Ambil parameter dari konfigurasi
        bb_fast_p = self.config.get("bb_fast_period", 20)
        bb_fast_s = self.config.get("bb_fast_std", 2.0)
        bb_slow_p = self.config.get("bb_slow_period", 100)
        bb_slow_s = self.config.get("bb_slow_std", 2.0)
        macd_f = self.config.get("macd_fast", 12)
        macd_s = self.config.get("macd_slow", 26)
        macd_sig = self.config.get("macd_signal", 9)
        
        df = get_rates(self.symbol, self.timeframe, count=bb_slow_p + macd_s + 5)
        if df.empty:
            status["condition"] = "Failed to retrieve historical data"
            return status
            
        df.ta.bbands(length=bb_fast_p, std=bb_fast_s, prefix="fast", append=True)
        df.ta.bbands(length=bb_slow_p, std=bb_slow_s, prefix="slow", append=True)
        df.ta.macd(fast=macd_f, slow=macd_s, signal=macd_sig, append=True)
        
        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]
        
        macd_line = f'MACD_{macd_f}_{macd_s}_{macd_sig}'
        status['macd_value'] = f"{last_bar[macd_line]:.5f}"
        
        bb_fast_lower = last_bar[f'fast_BBL_{bb_fast_p}_{bb_fast_s}']
        bb_fast_upper = last_bar[f'fast_BBU_{bb_fast_p}_{bb_fast_s}']
        bb_slow_lower = last_bar[f'slow_BBL_{bb_slow_p}_{bb_slow_s}']
        bb_slow_upper = last_bar[f'slow_BBU_{bb_slow_p}_{bb_slow_s}']

        if bb_fast_lower < bb_slow_lower:
            status['bb_position'] = "Fast Below Slow (Buy Potential)"
        elif bb_fast_upper > bb_slow_upper:
            status['bb_position'] = "Fast Above Slow (Sell Potential)"
        else:
            status['bb_position'] = "Normal (Inside Slow Channel)"

        if open_positions_count > 0:
            status["condition"] = "Position already open"
            return status

        trade_signal = None
        point = symbol_info.point
        stops_level_price = symbol_info.trade_stops_level * point
        entry_buffer = stops_level_price + (2 * point)

        # Cek kondisi sinyal secara terpisah
        macd_signal_line = f'MACDs_{macd_f}_{macd_s}_{macd_sig}'
        buy_condition_bb = bb_fast_lower < bb_slow_lower
        buy_condition_macd = last_bar[macd_line] < 0
        buy_condition_cross = prev_bar[macd_line] < prev_bar[macd_signal_line] and \
                              last_bar[macd_line] > last_bar[macd_signal_line]

        if buy_condition_bb and buy_condition_macd and buy_condition_cross:
            entry_price = tick.ask + entry_buffer
            sl = bb_fast_lower
            tp = bb_fast_upper
            if (tp - entry_price) > (2 * symbol_info.spread * point):
                status["condition"] = "Valid Counter-Buy Signal"
                trade_signal = {"signal": "BUY_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Counter-Buy Signal Failed (TP too close)"

        sell_condition_bb = bb_fast_upper > bb_slow_upper
        sell_condition_macd = last_bar[macd_line] > 0
        sell_condition_cross = prev_bar[macd_line] > prev_bar[macd_signal_line] and \
                               last_bar[macd_line] < last_bar[macd_signal_line]

        if sell_condition_bb and sell_condition_macd and sell_condition_cross:
            entry_price = tick.bid - entry_buffer
            sl = bb_fast_upper
            tp = bb_fast_lower
            
            if (entry_price - tp) > (2 * symbol_info.spread * point):
                status["condition"] = "Valid Counter-Sell Signal"
                trade_signal = {"signal": "SELL_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Counter-Sell Signal Failed (TP too close)"
        
        if not trade_signal and status["condition"] == "Analyzing...":
            status["condition"] = "No Signal"

        status["trade_signal"] = trade_signal
        return status