import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

class HeikenAshiMaReversal:
    # Nama yang akan muncul di UI Dropdown
    strategy_name = "Reversal (Heiken Ashi + MA Channel)"

    # Label yang akan ditampilkan di MonitoringWindow
    live_status_labels = {
        "condition": "Market Condition:",
        "trend_info": "Trend Info:",
        "ha_color": "Heiken Ashi:"
    }
    
    # Parameter yang akan muncul dinamis di SettingsWindow
    parameters = {
        "ema_channel_period": {"display_name": "EMA Channel Period", "type": "int", "default": 55},
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0, "step": 0.1},
        "rr_ratio": {"display_name": "Risk/Reward Ratio (TP)", "type": "float", "default": 1.5, "step": 0.1},
        "spread_tolerance": {"display_name": "Spread Tolerance", "type": "float", "default": 1.5, "step": 0.1},
        "sl_lookback_candle": {"display_name": "SL Candle Lookback Amount", "type": "int", "default": 5}
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
            "condition": "Analyzing...", "trend_info": "-", "ha_color": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        ema_period = self.config.get("ema_channel_period", 55)
        rr_ratio = self.config.get("rr_ratio", 1.5)
        
        df = get_rates(self.symbol, self.timeframe, count=ema_period + 5)
        if df.empty:
            status["condition"] = "Failed to retrieve historical data"
            return status
            
        df[f'EMA_High_{ema_period}'] = ta.ema(df['high'], length=ema_period)
        df[f'EMA_Low_{ema_period}'] = ta.ema(df['low'], length=ema_period)
        
        ha_df = ta.ha(df['open'], df['high'], df['low'], df['close'])
        df = pd.concat([df, ha_df], axis=1)

        last_bar = df.iloc[-1]
        lookback_candle = self.config.get("sl_lookback_candle", 5)
        last_n_candle = df.iloc[-lookback_candle:]
        
        ha_color = "green" if last_bar['HA_close'] > last_bar['HA_open'] else "red"
        status['ha_color'] = ha_color.capitalize()

        ema_high = last_bar[f'EMA_High_{ema_period}']
        ema_low = last_bar[f'EMA_Low_{ema_period}']
        status['trend_info'] = f"Channel ({ema_low:.5f} - {ema_high:.5f})"

        if ema_low <= last_bar['close'] <= ema_high:
            status["condition"] = "No-Trade Zone (Price inside Channel)"
            return status

        trade_signal = None
        point = symbol_info.point
        is_spread_ok = self.analyzer.is_spread_tight(symbol_info.spread)

        # [PERUBAHAN] Hitung jarak aman untuk pending order
        stops_level_price = symbol_info.trade_stops_level * point
        entry_buffer = stops_level_price + (2 * point) # Tambah 2 point sebagai buffer
        sl_buffer = max(symbol_info.spread * point, stops_level_price) + (2 * point)

        # Logika Entri Buy
        if last_bar['close'] > ema_high and ha_color == 'green':
            if is_spread_ok:
                status["condition"] = "Valid Sell Signal"
                entry_price = tick.ask + entry_buffer
                sl = last_n_candle['high'].max()
                if sl <= last_bar['high']:
                    sl += 50
                else: 
                    sl += sl_buffer
                tp = entry_price - ((sl - entry_price) * rr_ratio)
                trade_signal = {"signal": "SELL_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Sell Signal (Awaiting Spread)"
        
        # Logika Entri Sell
        elif last_bar['close'] < ema_low and ha_color == 'red':
            if is_spread_ok:
                status["condition"] = "Valid Buy Signal"
                # [PERUBAHAN] Gunakan pending order
                entry_price = tick.bid - entry_buffer
                sl = last_n_candle['low'].min()
                if sl >= last_bar['low']: # <-- Perbaikan kondisi if
                    sl -= 50
                else:
                    sl -= sl_buffer
                tp = entry_price + ((entry_price - sl) * rr_ratio)
                trade_signal = {"signal": "BUY_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}
            else:
                status["condition"] = "Buy Signal (Awaiting Spread)"
        
        else:
             status["condition"] = "No Signal"

        status["trade_signal"] = trade_signal
        return status