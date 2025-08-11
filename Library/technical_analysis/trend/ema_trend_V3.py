# VERSI FINAL - DIPERBAIKI SECARA MENYELURUH
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

def check_ema_trend(symbol: str, timeframe, analyzer: SpreadAnalyzer, config: dict):
    """
    Menganalisis pasar menggunakan pendekatan multi-filter yang lebih kuat dan aman.
    Semua akses config menggunakan .get() untuk mencegah KeyError.
    """
    tick = mt5.symbol_info_tick(symbol)
    df = get_rates(symbol, timeframe, count=250) 
    symbol_info = get_symbol_info(symbol)

    status = {
        "symbol": symbol,
        "price": tick.bid if tick else 0,
        "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {analyzer.average_spread:.1f})",
        "condition": "Menganalisis...", "trend_info": "-", "volume_info": "-",
        "trade_signal": None
    }

    if df.empty or not symbol_info or not tick or len(df) < 200:
        status["condition"] = "Data Tidak Cukup Untuk Analisis"
        return status

    # --- Blok Konfigurasi & Kalkulasi Indikator ---
    # !! PERBAIKAN: Menggunakan .get() untuk semua parameter dengan default yang logis
    ema_fast_period = config.get("ema_fast_period", 50)
    ema_slow_period = config.get("ema_slow_period", 200)
    rsi_period = config.get("rsi_period", 14)
    adx_period = config.get("adx_period", 14)
    atr_period = config.get("atr_period", 14)
    
    rr_ratio = config.get("rr_ratio", 1.5)
    atr_multiplier = config.get("atr_multiplier", 2.5) 
    adx_threshold = config.get("adx_threshold", 25)
    
    # Kalkulasi Indikator
    df.ta.ema(length=ema_fast_period, append=True, col_names=(f'EMA_fast',))
    df.ta.ema(length=ema_slow_period, append=True, col_names=(f'EMA_slow',))
    df.ta.rsi(length=rsi_period, append=True, col_names=(f'RSI',))
    df.ta.atr(length=atr_period, append=True, col_names=(f'ATR',))
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=adx_period)
    if adx_df is not None and not adx_df.empty:
        df[f'ADX'] = adx_df[f'ADX_{adx_period}']
    else:
        df[f'ADX'] = 0 # Default jika ADX gagal dihitung
    
    df['time'] = pd.to_datetime(df['time'], unit='s')
    last_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]

    # --- Logika Sinyal Trading ---
    is_spread_ok = analyzer.is_spread_tight(symbol_info.spread)
    is_trending = last_bar['ADX'] > adx_threshold
    trend_info_text = f"ADX({adx_period}): {last_bar['ADX']:.2f} | EMA({ema_fast_period}) > EMA({ema_slow_period}): {last_bar['EMA_fast'] > last_bar['EMA_slow']}"
    status["trend_info"] = trend_info_text
    
    bar_time_int = int(last_bar['time'].timestamp())

    # Kondisi Bullish (Beli)
    is_bullish_trend = last_bar['EMA_fast'] > last_bar['EMA_slow'] and prev_bar['EMA_fast'] > prev_bar['EMA_slow']
    is_rsi_bullish = last_bar['RSI'] > 50
    
    if is_bullish_trend and is_trending and is_rsi_bullish and is_spread_ok:
        status["condition"] = f"Sinyal Bullish Valid (ADX > {adx_threshold})"
        entry_price = tick.ask
        sl_distance = last_bar['ATR'] * atr_multiplier
        sl = entry_price - sl_distance
        tp = entry_price + (sl_distance * rr_ratio)
        
        status["trade_signal"] = {"signal": "BUY", "entry": entry_price, "sl": sl, "tp": tp, "bar_time": bar_time_int}

    # Kondisi Bearish (Jual)
    is_bearish_trend = last_bar['EMA_fast'] < last_bar['EMA_slow'] and prev_bar['EMA_fast'] < prev_bar['EMA_slow']
    is_rsi_bearish = last_bar['RSI'] < 50

    if is_bearish_trend and is_trending and is_rsi_bearish and is_spread_ok:
        status["condition"] = f"Sinyal Bearish Valid (ADX > {adx_threshold})"
        entry_price = tick.bid
        sl_distance = last_bar['ATR'] * atr_multiplier
        sl = entry_price + sl_distance
        tp = entry_price - (sl_distance * rr_ratio)

        status["trade_signal"] = {"signal": "SELL", "entry": entry_price, "sl": sl, "tp": tp, "bar_time": bar_time_int}

    if not status["trade_signal"] and is_trending:
        status["condition"] = "Menunggu Sinyal Valid di Pasar Trending"
    elif not is_trending:
        status["condition"] = f"DIAM: Pasar Sideways (ADX < {adx_threshold})"

    return status