# D:\7FX Automation\Library\technical_analysis\trend\ema_trend.py

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

def check_ema_trend(symbol: str, timeframe, analyzer: SpreadAnalyzer, config: dict):
    """
    Menganalisis kondisi pasar dan sinyal.
    Kalkulasi SL kini memperhitungkan spread.
    """
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = get_symbol_info(symbol)

    if symbol_info:
        analyzer.add_spread(symbol_info.spread)

    status = {
        "symbol": symbol,
        "price": tick.bid if tick else 0,
        "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {analyzer.average_spread:.1f})",
        "condition": "Menganalisis...", "trend_info": "-", "volume_info": "-",
        "trade_signal": None
    }

    # 1. Lakukan pengecekan untuk variabel yang sudah ada DULU
    if not symbol_info or not tick:
        status["condition"] = "Data Simbol/Tick Tidak Tersedia"
        return status

    # 2. Ambil ema_length untuk menentukan jumlah data
    ema_length = config.get("ema_period", 50)
    required_data_count = ema_length + 50 
    df = get_rates(symbol, timeframe, count=required_data_count)

    # 3. SEKARANG baru periksa df setelah dibuat
    if df.empty:
        status["condition"] = "Gagal mengambil data histori"
        return status
        
    # Lanjutkan sisa kode...
    rr_ratio = config.get("rr_ratio", 1.5)
    sl_lookback = config.get("sl_lookback", 3)

    ema_col_name = f'EMA_{ema_length}'
    df.ta.ema(length=ema_length, append=True)
    df.ta.obv(volume=df['tick_volume'], append=True)
    df['tick_volume_ma_short'] = df['tick_volume'].rolling(window=10).mean()
    df['tick_volume_ma_long'] = df['tick_volume'].rolling(window=50).mean()
    # --- Akhir Blok Kalkulasi ---

    # SEKARANG baru definisikan last_bar dan prev_bar dari DataFrame yang sudah lengkap
    last_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]
    point = symbol_info.point
    
    current_spread_price = symbol_info.spread * point
    stops_level_price = symbol_info.trade_stops_level * point
    sl_buffer = max(current_spread_price, stops_level_price) + (2 * point)

    status["price"] = tick.bid
    if last_bar['close'] > last_bar[ema_col_name]: status["trend_info"] = f"Uptrend (di atas EMA)"
    else: status["trend_info"] = f"Downtrend (di bawah EMA)"
    if last_bar['OBV'] > prev_bar['OBV']: status["volume_info"] = "Akumulasi (Naik)"
    else: status["volume_info"] = "Distribusi (Turun)"

    is_uptrend = "Uptrend" in status["trend_info"]
    is_accumulation = "Akumulasi" in status["volume_info"]
    is_volume_increasing = last_bar['tick_volume_ma_short'] > last_bar['tick_volume_ma_long']
    is_spread_ok = analyzer.is_spread_tight(symbol_info.spread)

    if is_uptrend and is_accumulation and is_volume_increasing:
        if is_spread_ok:
            status["condition"] = "Sinyal Bullish Valid"
            entry_price = last_bar['high'] + stops_level_price + (2 * point)
            
            lowest_low = min(df['low'].tail(sl_lookback))
            sl = lowest_low - sl_buffer

            tp = entry_price + ((entry_price - sl) * rr_ratio)
            status["trade_signal"] = {"signal": "BUY_STOP", "entry": entry_price, "sl": sl, "tp": tp}
        else:
            status["condition"] = "Sinyal Bullish (Menunggu Spread)"
            
    elif not is_uptrend and not is_accumulation and is_volume_increasing:
        if is_spread_ok:
            status["condition"] = "Sinyal Bearish Valid"
            entry_price = last_bar['low'] - stops_level_price - (2 * point)

            highest_high = max(df['high'].tail(sl_lookback))
            sl = highest_high + sl_buffer
            
            tp = entry_price - ((sl - entry_price) * rr_ratio)
            status["trade_signal"] = {"signal": "SELL_STOP", "entry": entry_price, "sl": sl, "tp": tp}
        else:
            status["condition"] = "Sinyal Bearish (Menunggu Spread)"
    else:
        status["condition"] = "Transisi / Ranging"

    return status