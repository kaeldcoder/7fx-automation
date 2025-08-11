# Library/strategies/ema_rsi_pullback.py

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

class EmaRsiPullback:
    # Nama yang akan muncul di UI Dropdown
    strategy_name = "Trend Pullback (RSI + EMA)"

    # Label yang akan ditampilkan di MonitoringWindow
    live_status_labels = {
        "condition": "Market Condition:",
        "main_trend": "Main Trend:",
        "rsi_value": "RSI Value:"
    }
    
    # Parameter yang akan muncul dinamis di SettingsWindow
    parameters = {
        "ema_period": {"display_name": "Trend EMA Period", "type": "int", "default": 200},
        "rsi_period": {"display_name": "RSI Period", "type": "int", "default": 14},
        "rsi_oversold_level": {"display_name": "RSI Oversold Level (Buy)", "type": "int", "default": 40},
        "rsi_overbought_level": {"display_name": "RSI Overbought Level (Sell)", "type": "int", "default": 60},
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0, "step": 0.1},
        "rr_ratio": {"display_name": "Risk/Reward Ratio (TP)", "type": "float", "default": 1.5, "step": 0.1},
        "spread_tolerance": {"display_name": "Spread Tolerance", "type": "float", "default": 1.5, "step": 0.1}
    }

    def __init__(self, mt5_instance, config: dict, analyzer: SpreadAnalyzer):
        self.mt5 = mt5_instance
        self.config = config
        self.analyzer = analyzer
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe_int')

    def check_signal(self):
        tick = self.mt5.symbol_info_tick(self.symbol)
        symbol_info = get_symbol_info(self.symbol)

        if symbol_info:
            self.analyzer.add_spread(symbol_info.spread)

        status = {
            "symbol": self.symbol,
            "price": tick.bid if tick else 0,
            "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {self.analyzer.average_spread:.1f})",
            "condition": "Analyzing...", "main_trend": "-", "rsi_value": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        ema_period = self.config.get("ema_period", 200)
        rsi_period = self.config.get("rsi_period", 14)
        rsi_oversold = self.config.get("rsi_oversold_level", 40)
        rsi_overbought = self.config.get("rsi_overbought_level", 60)
        rr_ratio = self.config.get("rr_ratio", 1.5)
        
        df = get_rates(self.symbol, self.timeframe, count=ema_period + rsi_period + 5)
        if df.empty:
            status["condition"] = "Failed to retrieve historical data"
            return status
            
        ema_col = f'EMA_{ema_period}'
        rsi_col = f'RSI_{rsi_period}'
        df.ta.ema(length=ema_period, append=True)
        df.ta.rsi(length=rsi_period, append=True)
        
        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]
        
        status['rsi_value'] = f"{last_bar[rsi_col]:.2f}"

        trade_signal = None
        point = symbol_info.point
        is_spread_ok = self.analyzer.is_spread_tight(symbol_info.spread)

        # [PERUBAHAN] Hitung jarak aman untuk pending order
        stops_level_price = symbol_info.trade_stops_level * point
        entry_buffer = stops_level_price + (2 * point)

        is_uptrend = last_bar['close'] > last_bar[ema_col]
        is_downtrend = last_bar['close'] < last_bar[ema_col]
        
        if is_uptrend:
            status['main_trend'] = "Uptrend"
            if prev_bar[rsi_col] < rsi_oversold and last_bar[rsi_col] > rsi_oversold:
                if is_spread_ok:
                    status["condition"] = "Valid Pullback Buy Signal"
                    # [PERUBAHAN] Gunakan pending order
                    entry_price = tick.ask + entry_buffer
                    sl = df['low'].tail(10).min() - (symbol_info.spread * point)
                    tp = entry_price + ((entry_price - sl) * rr_ratio)
                    trade_signal = {"signal": "BUY_STOP", "entry": entry_price, "sl": sl, "tp": tp}
                else:
                    status["condition"] = "Pullback Buy Signal (Awaiting Spread)"
        
        elif is_downtrend:
            status['main_trend'] = "Downtrend"
            if prev_bar[rsi_col] > rsi_overbought and last_bar[rsi_col] < rsi_overbought:
                if is_spread_ok:
                    status["condition"] = "Valid Pullback Sell Signal"
                    # [PERUBAHAN] Gunakan pending order
                    entry_price = tick.bid - entry_buffer
                    sl = df['high'].tail(10).max() + (symbol_info.spread * point)
                    tp = entry_price - ((sl - entry_price) * rr_ratio)
                    trade_signal = {"signal": "SELL_STOP", "entry": entry_price, "sl": sl, "tp": tp}
                else:
                    status["condition"] = "Pullback Sell Signal (Awaiting Spread)"
        
        else:
            status['main_trend'] = "Sideways / Ranging"
            status["condition"] = "No-Trade Zone (No Clear Trend)"

        if not trade_signal and status["condition"] == "Analyzing...":
            status["condition"] = "No Pullback Signal"

        status["trade_signal"] = trade_signal
        return status