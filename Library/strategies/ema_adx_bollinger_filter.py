import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

class EmaAdxBollingerFilter:
    strategy_name = "EMA Trend + ADX & Bollinger Filter"

    live_status_labels = {
        "condition": "Market Condition:",
        "trend_info": "Trend Info:",
        "volume_info": "Volume Info:",
        "adx_value": "ADX Value:",
        "volatility_info": "Volatility Info:"
    }

    parameters = {
        "ema_period": {"display_name": "EMA Period", "type": "int", "default": 50},
        "adx_period": {"display_name": "ADX Period", "type": "int", "default": 14},
        "adx_threshold": {"display_name": "ADX Threshold", "type": "int", "default": 25},
        "bb_period": {"display_name": "Bollinger Period", "type": "int", "default": 20},
        "bb_std_dev": {"display_name": "Bollinger Std Dev", "type": "float", "default": 2.0, "step": 0.1},
        "bb_squeeze_threshold": {"display_name": "Squeeze Threshold (%)", "type": "float", "default": 4.0, "step": 0.1},
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1},
        "rr_ratio": {"display_name": "Risk/Reward Ratio", "type": "float", "default": 1.5, "min": 0.5, "max": 10.0, "step": 0.1},
        "sl_lookback": {"display_name": "SL Lookback Period", "type": "int", "default": 3, "min": 1, "max": 10},
        "spread_tolerance": {"display_name": "Spread Tolerance", "type": "float", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1}
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
            "condition": "Analyzing...", "trend_info": "-", "volume_info": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status
        
        ema_length = self.config.get("ema_period", 50)
        adx_length = self.config.get("adx_period", 14)
        adx_threshold = self.config.get("adx_threshold", 25)
        bb_length = self.config.get("bb_period", 20)
        bb_std = self.config.get("bb_std_dev", 2.0)
        squeeze_threshold_percent = self.config.get("bb_squeeze_threshold", 4.0)
        rr_ratio = self.config.get("rr_ratio", 1.5)
        sl_lookback = self.config.get("sl_lookback", 3)

        required_data_count = max(ema_length, adx_length, bb_length) + 50 
        df = get_rates(self.symbol, self.timeframe, count=required_data_count)

        if df.empty:
            status["condition"] = "Failed to retrieve historical data"
            return status
        
        ema_col_name = f'EMA_{ema_length}'
        df.ta.ema(length=ema_length, append=True)
        df.ta.adx(length=adx_length, append=True)
        df.ta.bbands(length=bb_length, std=bb_std, append=True)
        df.ta.obv(volume=df['tick_volume'], append=True)
        df['tick_volume_ma_short'] = df['tick_volume'].rolling(window=10).mean()
        df['tick_volume_ma_long'] = df['tick_volume'].rolling(window=50).mean()

        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]

        status["price"] = tick.bid
        if last_bar['close'] > last_bar[ema_col_name]: status["trend_info"] = f"Uptrend (above EMA)"
        else: status["trend_info"] = f"Downtrend (below EMA)"
        if last_bar['OBV'] > prev_bar['OBV']: status["volume_info"] = "Accumulation (Bullish)"
        else: status["volume_info"] = "Distribution (Bearish)"
        
        # --- [FILTER RANGING BARU YANG LEBIH CANGGIH] ---
        current_adx = last_bar[f'ADX_{adx_length}']
        bb_upper = last_bar[f'BBU_{bb_length}_{bb_std}']
        bb_lower = last_bar[f'BBL_{bb_length}_{bb_std}']
        
        # Hitung lebar Bollinger Bands sebagai persentase dari harga tengah
        bb_width_percent = ((bb_upper - bb_lower) / last_bar['close']) * 100
        
        status['adx_value'] = f"{current_adx:.2f}"
        status['volatility_info'] = f"BB Width: {bb_width_percent:.2f}%"

        # Cek kondisi ranging
        is_ranging = current_adx < adx_threshold and bb_width_percent < squeeze_threshold_percent
        
        if is_ranging:
            status["condition"] = f"Market Squeeze (Low ADX & BBands)"
            status["trade_signal"] = None
            return status
        
        point = symbol_info.point
        sl_buffer = max(symbol_info.spread * point, symbol_info.trade_stops_level * point) + (2 * point)

        is_uptrend = "Uptrend" in status["trend_info"]
        is_accumulation = "Akumulasi" in status["volume_info"]
        is_volume_increasing = last_bar['tick_volume_ma_short'] > last_bar['tick_volume_ma_long']
        is_spread_ok = self.analyzer.is_spread_tight(symbol_info.spread)

        trade_signal = None
        # Tentukan kondisi bullish
        if is_uptrend and is_accumulation and is_volume_increasing:
            if is_spread_ok:
                status["condition"] = "Valid Bullish Signal"
                entry_price = last_bar['high'] + sl_buffer
                sl = min(df['low'].tail(sl_lookback)) - (2 * point)
                tp = entry_price + ((entry_price - sl) * rr_ratio)
                trade_signal = {"signal": "BUY_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Bullish Signal (Awaiting Spread)"
        # Tentukan kondisi bearish
        elif not is_uptrend and not is_accumulation and is_volume_increasing:
            if is_spread_ok:
                status["condition"] = "Valid Bearish Signal"
                entry_price = last_bar['low'] - sl_buffer
                sl = max(df['high'].tail(sl_lookback)) + (2 * point)
                tp = entry_price - ((sl - entry_price) * rr_ratio)
                trade_signal = {"signal": "SELL_STOP", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Bearish Signal (Awaiting Spread)"
        # Kondisi lainnya
        else:
            status["condition"] = "Transition / Neutral"

        status["trade_signal"] = trade_signal
        return status