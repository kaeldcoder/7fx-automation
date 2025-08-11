import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, time
import pytz

# Impor dari library Anda
from Library.data_handler.data_handler import get_rates
from Library.utils.market_analyzer import SpreadAnalyzer
from Library.technical_analysis.smc_analyzer import (find_swing_points, detect_liquidity_sweep, 
                                                     detect_choch, find_fvg, find_order_block)

class SmcLsfr:
    strategy_name = "SMC Liquidity Sweep & FVG"

    live_status_labels = {
        "market_structure": "Market Structure:",
        "last_event": "Last Event:",
        "setup_status": "Setup Status:"
    }
    
    parameters = {
        "risk_per_trade": {"display_name": "Risk per Trade (%)", "type": "float", "default": 1.0},
        "rr_ratio": {"display_name": "Risk/Reward Ratio (TP)", "type": "float", "default": 2.0},
        "session_start": {"display_name": "Session Start (UTC)", "type": "str", "default": "13:00"},
        "session_end": {"display_name": "Session End (UTC)", "type": "str", "default": "17:00"},
        "max_spread": {"display_name": "Max Spread (pips)", "type": "float", "default": 1.5},
    }

    def __init__(self, mt5_instance, config: dict, analyzer: SpreadAnalyzer):
        self.mt5 = mt5_instance
        self.config = config
        self.analyzer = analyzer
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe_int')

    def check_signal(self, open_positions_count: int = 0):
        # [PERBAIKAN 1] Lengkapi kamus status dengan semua key yang dibutuhkan UI
        status = {
            "symbol": self.symbol,
            "price": 0.0,
            "spread_info": "N/A",
            "condition": "Analyzing...",
            "market_structure": "-",
            "last_event": "-",
            "setup_status": "-",
            "trade_signal": None
        }

        # [PERBAIKAN 2] Ambil data live & update status dasar SEBELUM filter apapun
        tick = self.mt5.symbol_info_tick(self.symbol)
        symbol_info = self.mt5.symbol_info(self.symbol)

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        # Update info dasar yang harus selalu tampil
        status['price'] = tick.bid
        self.analyzer.add_spread(symbol_info.spread)
        status['spread_info'] = f"{symbol_info.spread} (Avg: {self.analyzer.average_spread:.1f})"

        # --- 1. FILTER WAJIB ---
        if not self._is_in_session():
            status["condition"] = "Outside Trading Session"
            status["setup_status"] = "Analysis paused until session starts."
            return status
        
        # Konversi spread (dalam points) ke pips untuk perbandingan
        current_spread_pips = symbol_info.spread / 10
        if current_spread_pips > self.config.get('max_spread', 1.5):
            status["condition"] = "Spread Too Wide"
            return status
            
        if open_positions_count > 0:
            status["condition"] = "Position already open"
            return status

        # --- 2. ANALISIS SMC (Sisa fungsi tidak berubah) ---
        df = get_rates(self.symbol, self.timeframe, count=200)

        if df.empty or len(df) < 50:
            status["condition"] = "Insufficient historical data"
            return status

        swing_points = find_swing_points(df, lookback=10)
        if not swing_points['highs'] or not swing_points['lows']:
            status["condition"] = "No market structure found"
            return status

        # --- Skenario Bullish (Beli) ---
        last_swing_low = swing_points['lows'][-1]
        if detect_liquidity_sweep(df, last_swing_low, lookback=5):
            status['last_event'] = f"Liquidity Sweep @ {last_swing_low['price']:.5f}"
            last_lower_high = next((sh for sh in reversed(swing_points['highs']) if sh['index'] < last_swing_low['index']), None)
            if last_lower_high and detect_choch(df, last_lower_high, sweep_low_index=last_swing_low['index']):
                status['market_structure'] = "Bullish CHOCH Confirmed"
                fvg = find_fvg(df, from_index=last_lower_high['index'])
                order_block = find_order_block(df, from_index=last_lower_high['index'])
                
                entry_target = None
                if fvg and fvg['type'] == 'bullish':
                    entry_target = fvg
                    status['setup_status'] = f"FVG found at {fvg['low']:.5f}"
                elif order_block and order_block['type'] == 'bullish':
                    entry_target = order_block
                    status['setup_status'] = f"Order Block at {order_block['low']:.5f}"
                
                if entry_target:
                    entry_price = entry_target.get('level_50', entry_target['high'])
                    sl = last_swing_low['price'] - (symbol_info.point * 10)
                    tp = entry_price + (abs(entry_price - sl) * self.config.get('rr_ratio', 2.0))
                    status['trade_signal'] = {"signal": "BUY_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}
                    status['condition'] = "Buy Setup Ready"
                    
        if not status['trade_signal']:
            last_swing_high = swing_points['highs'][-1]
            
            recent_candles = df.tail(5)
            wick_above_swing_high = (recent_candles['high'] > last_swing_high['price']).any()
            last_candle_closed_below = recent_candles.iloc[-1]['close'] < last_swing_high['price']
            
            if wick_above_swing_high and last_candle_closed_below:
                status['last_event'] = f"Liquidity Sweep @ {last_swing_high['price']:.5f}"
                
                last_higher_low = next((sl for sl in reversed(swing_points['lows']) if sl['index'] < last_swing_high['index']), None)

                if last_higher_low:
                    candles_after_sweep = df[df.index > last_swing_high['index']]
                    if not candles_after_sweep.empty and (candles_after_sweep['low'] < last_higher_low['price']).any():
                        status['market_structure'] = "Bearish CHOCH Confirmed"
                        
                        fvg = find_fvg(df, from_index=last_higher_low['index'])
                        order_block = find_order_block(df, from_index=last_higher_low['index'])
                        
                        entry_target = None
                        if fvg and fvg['type'] == 'bearish':
                            entry_target = fvg
                            status['setup_status'] = f"FVG found at {fvg['high']:.5f}"
                        elif order_block and order_block['type'] == 'bearish':
                            entry_target = order_block
                            status['setup_status'] = f"Order Block at {order_block['high']:.5f}"
                        
                        if entry_target:
                            entry_price = entry_target.get('level_50', entry_target['low'])
                            sl = last_swing_high['price'] + (symbol_info.point * 10)
                            tp = entry_price - (abs(sl - entry_price) * self.config.get('rr_ratio', 2.0))
                            status['trade_signal'] = {"signal": "SELL_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}
                            status['condition'] = "Sell Setup Ready"

        if not status['trade_signal'] and status['condition'] == "Analyzing...":
            status['condition'] = "No SMC setup"

        return status

    def _is_in_session(self):
        """Memeriksa apakah waktu saat ini berada dalam sesi trading yang diizinkan (UTC)."""
        start_str = self.config.get("session_start", "13:00")
        end_str = self.config.get("session_end", "17:00")
        
        try:
            start_time = time(int(start_str.split(':')[0]), int(start_str.split(':')[1]))
            end_time = time(int(end_str.split(':')[0]), int(end_str.split(':')[1]))
            now_utc = datetime.now(pytz.utc).time()
            return start_time <= now_utc <= end_time
        except (ValueError, pytz.UnknownTimeZoneError):
            return False