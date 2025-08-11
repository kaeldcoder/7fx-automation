# Library/strategies/ema_trend_basic.py

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

class EmaTrendBasic:
    # Nama strategi yang akan muncul di UI Dropdown
    strategy_name = "EMA Trend Basic"
    
    live_status_labels = {
        "condition": "Market Condition:",
        "trend_info": "Trend Info:",
        "volume_info": "Volume Info:"
    }

    parameters = {
        "ema_period": {"display_name": "EMA Period", "type": "int", "default": 50, "min": 10, "max": 200},
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1},
        "rr_ratio": {"display_name": "Risk/Reward Ratio", "type": "float", "default": 1.5, "min": 0.5, "max": 10.0, "step": 0.1},
        "sl_lookback": {"display_name": "SL Lookback Period", "type": "int", "default": 3, "min": 1, "max": 10},
        "spread_tolerance": {"display_name": "Spread Tolerance", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1}
    }

    def __init__(self, mt5_instance, config: dict, analyzer: SpreadAnalyzer):
        """
        Inisialisasi strategi dengan konfigurasi spesifik per pair.
        
        Args:
            mt5_instance: Instance MetaTrader5 yang aktif.
            config (dict): Konfigurasi dari satu tab 'Strategi per Pair'.
            analyzer (SpreadAnalyzer): Instance analyzer untuk pair ini.
        """
        self.mt5 = mt5_instance
        self.config = config
        self.analyzer = analyzer
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe_int')

    def check_signal(self):
        """
        [FUNGSI UTAMA] Menganalisis kondisi pasar dan menghasilkan sinyal.
        Ini adalah isi dari fungsi check_ema_trend() Anda yang lama.
        """
        tick = self.mt5.symbol_info_tick(self.symbol)
        symbol_info = get_symbol_info(self.symbol)

        if symbol_info:
            self.analyzer.add_spread(symbol_info.spread)

        status = {
            "symbol": self.symbol,
            "price": tick.bid if tick else 0,
            "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {self.analyzer.average_spread:.1f})",
            "condition": "Analyzing...", "trend_info": "-", "volume_info": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        ema_length = self.config.get("ema_period", 50)
        required_data_count = ema_length + 50 
        df = get_rates(self.symbol, self.timeframe, count=required_data_count)

        if df.empty:
            status["condition"] = "Failed to retrieve historical data"
            return status
            
        rr_ratio = self.config.get("rr_ratio", 1.5)
        sl_lookback = self.config.get("sl_lookback", 3)

        # Lakukan semua kalkulasi teknikal...
        ema_col_name = f'EMA_{ema_length}'
        df.ta.ema(length=ema_length, append=True)
        df.ta.obv(volume=df['tick_volume'], append=True)
        df['tick_volume_ma_short'] = df['tick_volume'].rolling(window=10).mean()
        df['tick_volume_ma_long'] = df['tick_volume'].rolling(window=50).mean()
        
        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]
        point = symbol_info.point
        
        current_spread_price = symbol_info.spread * point
        stops_level_price = symbol_info.trade_stops_level * point
        sl_buffer = max(current_spread_price, stops_level_price) + (2 * point)

        # Analisis Tren dan Volume
        status["price"] = tick.bid
        if last_bar['close'] > last_bar[ema_col_name]: status["trend_info"] = f"Uptrend (above EMA)"
        else: status["trend_info"] = f"Downtrend (below EMA)"
        if last_bar['OBV'] > prev_bar['OBV']: status["volume_info"] = "Accumulation (Bullish)"
        else: status["volume_info"] = "Distribution (Bearish)"

        is_uptrend = "Uptrend" in status["trend_info"]
        is_accumulation = "Akumulasi" in status["volume_info"]
        is_volume_increasing = last_bar['tick_volume_ma_short'] > last_bar['tick_volume_ma_long']
        is_spread_ok = self.analyzer.is_spread_tight(symbol_info.spread)

        # Logika Sinyal
        if is_uptrend and is_accumulation and is_volume_increasing:
            if is_spread_ok:
                status["condition"] = "Valid Bullish Signal"
                entry_price = last_bar['high'] + stops_level_price + (2 * point)
                lowest_low = min(df['low'].tail(sl_lookback))
                sl = lowest_low - sl_buffer
                tp = entry_price + ((entry_price - sl) * rr_ratio)
                status["trade_signal"] = {"signal": "BUY_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Bullish Signal (Awaiting Spread)"
                
        elif not is_uptrend and not is_accumulation and is_volume_increasing:
            if is_spread_ok:
                status["condition"] = "Valid Bearish Signal"
                entry_price = last_bar['low'] - stops_level_price - (2 * point)
                highest_high = max(df['high'].tail(sl_lookback))
                sl = highest_high + sl_buffer
                tp = entry_price - ((sl - entry_price) * rr_ratio)
                status["trade_signal"] = {"signal": "SELL_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Bearish Signal (Awaiting Spread)"
        else:
            status["condition"] = "Transition / Ranging"

        return status