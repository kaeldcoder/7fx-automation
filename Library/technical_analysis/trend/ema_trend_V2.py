# VERSI 2 - FINAL (ATR + Pengecekan Pending Order)
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from Library.data_handler.data_handler import get_rates, get_symbol_info
from Library.utils.market_analyzer import SpreadAnalyzer

def check_ema_trend(symbol: str, timeframe, analyzer: SpreadAnalyzer, config: dict):
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = get_symbol_info(symbol)
    magic_number = config.get("magic_number")

    status = {
        "symbol": symbol,
        "price": tick.bid if tick else 0,
        "spread_info": f"{symbol_info.spread if symbol_info else 0} (Avg: {analyzer.average_spread:.1f})",
        "condition": "Menganalisis...", "trend_info": "-", "volume_info": "-",
        "trade_signal": None
    }
    
    # --- [FILTER BARU] Cek apakah sudah ada pending order untuk pair ini ---
    existing_pending_ticket = None
    orders = mt5.orders_get(symbol=symbol)
    if orders:
        for order in orders:
            if order.magic == magic_number and (order.type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]):
                existing_pending_ticket = order.ticket
                # Jangan 'return', hanya catat tiketnya dan lanjutkan analisis
                break 
    
    # Tambahkan tiket yang ada ke status agar bisa diakses oleh main loop
    status["existing_pending_ticket"] = existing_pending_ticket

    if not symbol_info or not tick:
        status["condition"] = "Data Simbol/Tick Tidak Tersedia"
        return status

    ema_length = config.get("ema_period", 50)
    required_data_count = ema_length + 50
    df = get_rates(symbol, timeframe, count=required_data_count)

    if df.empty:
        status["condition"] = "Gagal mengambil data histori"
        return status

    rr_ratio = config.get("rr_ratio", 1.5)
    
    # Kalkulasi Indikator dengan ATR
    ema_col_name = f'EMA_{ema_length}'
    atr_col_name = 'ATRr_14'
    df.ta.ema(length=ema_length, append=True)
    df.ta.atr(length=14, append=True)

    last_bar = df.iloc[-1]
    status["price"] = tick.bid
    
    is_spread_ok = analyzer.is_spread_tight(symbol_info.spread)
    ema_value = last_bar[ema_col_name]
    is_uptrend = last_bar['close'] > ema_value
    
    # Logika SL/TP dengan ATR
    atr_value = last_bar[atr_col_name]
    atr_multiplier = 2.5 
    
    risk_distance_atr = atr_value * atr_multiplier
    profit_distance_atr = risk_distance_atr * rr_ratio

    if is_uptrend and is_spread_ok:
        status["trend_info"] = "Uptrend, Menunggu Pullback"
        entry_price = ema_value
        
        if tick.ask > entry_price:
            sl = entry_price - risk_distance_atr
            tp = entry_price + profit_distance_atr
            status["condition"] = "Sinyal BUY LIMIT Valid"
            status["trade_signal"] = {"signal": "BUY_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}

    elif not is_uptrend and is_spread_ok:
        status["trend_info"] = "Downtrend, Menunggu Rally"
        entry_price = ema_value
        
        if tick.bid < entry_price:
            sl = entry_price + risk_distance_atr
            tp = entry_price - profit_distance_atr
            status["condition"] = "Sinyal SELL LIMIT Valid"
            status["trade_signal"] = {"signal": "SELL_LIMIT", "entry": entry_price, "sl": sl, "tp": tp}
            
    else:
        status["condition"] = "Tidak ada sinyal / Menunggu Spread"
        if is_uptrend: status["trend_info"] = "Uptrend"
        else: status["trend_info"] = "Downtrend"

    return status