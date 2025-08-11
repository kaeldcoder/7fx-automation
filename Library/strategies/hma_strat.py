import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import math
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

def hma(src_series, length):
    if length <= 1:return src_series
    length_half = int(length/2)
    length_sqrt = int(math.sqrt(length))

    wma1 = ta.wma(src_series, length=length)
    wma2 = ta.wma(src_series, length=length_half)

    raw_hma = (2*wma2) - wma1
    final_hma = ta.wma(raw_hma, length=length_sqrt)
    return final_hma

def hma3(close_series, length):
    if length <= 4: return close_series
    p = int(length/2)
    p_div_2 = int(p/2)
    p_div_3 = int(p/3)

    if p_div_2 <= 1 or p_div_3 <= 1 or p <= 1:
        return pd.Series(index=close_series.index, dtype=float)
    
    wma_p_div_3 = ta.wma(close_series, length=p_div_3)
    wma_p_div_2 = ta.wma(close_series, length=p_div_2)
    wma_p = ta.wma(close_series, length=p)

    raw_hma3 = (wma_p_div_3 * 3) - wma_p_div_2 - wma_p
    final_hma3 = ta.wma(raw_hma3, length=p)
    return final_hma3

class hma_strat:
    strategy_name = "HMA Strategy"

    live_status_labels = {
        "condition": "Market Condition:",
        "trend_info": "HMA Status:"
    }
    
    parameters = {
        "hma_length": {"display_name": "HMA Length", "type": "int", "default": 24, "min": 10, "max": 100},
        "lot_mode": {
            "display_name": "Lot Mode", 
            "type": "option",
            "options": ["Fixed Lot", "By Risk"],
            "default": "Fixed Lot"
        },
        "risk_per_trade": {
            "display_name": "Risk per Trade (%)", 
            "type": "float", 
            "default": 1.0, 
            "step": 0.1,
            "condition": ("lot_mode", "==", "By Risk") 
        },
        "fixed_lot_size": {
            "display_name": "Fixed Lot Size", 
            "type": "float", 
            "default": 0.1, 
            "step": 0.01,
            "condition": ("lot_mode", "==", "Fixed Lot")
        }
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

        status = {
            "symbol": self.symbol,
            "price": tick.bid if tick else 0,
            "condition": "Analyzing...",
            "trend_info": "-",
            "trade_signal": None
        }

        if not symbol_info or not tick:
            status["condition"] = "Symbol/Tick Data Unavailable"
            return status

        hma_length = self.config.get("hma_length", 24)
        required_data_count = hma_length + 50
        df = get_rates(self.symbol, self.timeframe, count=required_data_count)
        df = df[~df.index.duplicated(keep='last')]

        if df is None or df.empty or len(df) < required_data_count:
            status["condition"] = "Not enough data"
            return status

        df['src'] = (df['high'] + df['low']) / 2
        df['a'] = hma(df['src'], length=hma_length)
        df['b'] = hma3(df['close'], length=hma_length)

        df.dropna(inplace=True)
        if len(df) < 2:
            status["condition"] = "Not enough post-indicator data"
            return status

        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]

        is_cross_up = last_bar['b'] > last_bar['a'] and prev_bar['b'] <= prev_bar['a']
        is_cross_down = last_bar['b'] < last_bar['a'] and prev_bar['b'] >= prev_bar['a']

        if is_cross_up:
            status["condition"] = "Bullish Crossover"
            status["trend_info"] = "HMA3 > HMA"
            status["trade_signal"] = {
                "signal": "BUY",
                "entry": tick.ask,
                "force_entry": True
            }
            status["positions_to_close"] = self.get_position_cleanup_instruction("BUY", self.config.get("magic_number"))
        elif is_cross_down:
            status["condition"] = "Bearish Crossover"
            status["trend_info"] = "HMA3 < HMA"
            status["trade_signal"] = {
                "signal": "SELL",
                "entry": tick.bid,
                "force_entry": True
            }
            status["positions_to_close"] = self.get_position_cleanup_instruction("SELL", self.config.get("magic_number"))
        else:
            status["condition"] = "No Crossover Signal"
            if last_bar['b'] > last_bar['a']:
                status["trend_info"] = "Bullish Trend"
            else:
                status["trend_info"] = "Bearish Trend"

        return status

    def get_position_cleanup_instruction(self, signal_type, magic_number):
        """
        Kembalikan daftar posisi yang harus ditutup (posisi lawan).
        """
        all_positions = mt5.positions_get(symbol=self.symbol)
        if not all_positions:
            return []

        lawan_type = mt5.POSITION_TYPE_SELL if signal_type == "BUY" else mt5.POSITION_TYPE_BUY
        to_close = []
        for pos in all_positions:
            if pos.type == lawan_type and pos.magic == magic_number:
                to_close.append(pos)
        return to_close