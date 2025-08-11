import pandas as pd
import pandas_ta as ta
import MetaTrader5 as mt5
from datetime import datetime

# Anggaplah kita memiliki fungsi-fungsi ini dari library internal Anda
# Jika tidak, Anda perlu mengimplementasikannya untuk mengambil data dari MT5
# from Library.data_handler.data_handler import get_rates

# ==============================================================================
# Fungsi Placeholder (Gantilah dengan implementasi MT5 Anda)
# ==============================================================================

def get_rates(symbol: str, timeframe_str: str, count: int):
    """
    Mengambil data harga historis langsung dari MetaTrader 5.
    """
    # Mapping string timeframe ke konstanta MT5
    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    
    timeframe_const = timeframe_map.get(timeframe_str)
    if timeframe_const is None:
        print(f"Error: Timeframe '{timeframe_str}' tidak valid.")
        return pd.DataFrame()

    # Ambil data dari MT5
    rates = mt5.copy_rates_from_pos(symbol, timeframe_const, 0, count)

    # Jika gagal mengambil data, kembalikan DataFrame kosong
    if rates is None or len(rates) == 0:
        # Pesan ini bisa di-uncomment untuk debugging jika perlu
        # print(f"Gagal mengambil data untuk {symbol}, error code: {mt5.last_error()}")
        return pd.DataFrame()
    
    # Konversi ke DataFrame
    df = pd.DataFrame(rates)
    
    # Konversi kolom 'time' ke format datetime yang dapat dibaca
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    return df

# ==============================================================================
# Implementasi Strategi V2 Berdasarkan Riset
# ==============================================================================

def check_new_strategy_v1(symbol: str, config: dict):
    """
    Menerapkan strategi perdagangan baru berdasarkan analisis multi-timeframe
    dan beberapa indikator sesuai dokumen riset V1.

    Args:
        symbol (str): Simbol mata uang, contoh: "EURUSD".
        config (dict): Kamus konfigurasi untuk parameter strategi.

    Returns:
        dict: Status analisis dan sinyal perdagangan jika ada.
    """
    status = {
        "symbol": symbol,
        "condition": "Menganalisis...",
        "macro_trend_info": "-",
        "micro_trend_info": "-",
        "momentum_info": "-",
        "volatility_info": "-",
        "trade_signal": None
    }

    try:
        # --- 1. Analisis Tren Makro pada Timeframe M15 (Kompas Arah) ---
        ema_macro_period = config.get("ema_macro_period", 50)
        df_m15 = get_rates(symbol, "M15", ema_macro_period + 2) # Butuh beberapa bar ekstra
        if df_m15.empty or len(df_m15) < ema_macro_period:
            status["condition"] = "Data M15 tidak cukup untuk analisis tren makro."
            return status

        df_m15['ema_macro'] = ta.ema(df_m15['close'], length=ema_macro_period)
        last_m15_bar = df_m15.iloc[-1]
        
        is_uptrend_macro = last_m15_bar['close'] > last_m15_bar['ema_macro']
        is_downtrend_macro = last_m15_bar['close'] < last_m15_bar['ema_macro']
        
        if is_uptrend_macro:
            status["macro_trend_info"] = f"Bullish (Harga di atas EMA {ema_macro_period} M15)"
        elif is_downtrend_macro:
            status["macro_trend_info"] = f"Bearish (Harga di bawah EMA {ema_macro_period} M15)"
        else:
            status["macro_trend_info"] = "Netral/Chop"


        # --- 2. Analisis Sinyal & Filter pada Timeframe M5 ---
        ema_fast_period = config.get("ema_fast_period", 9)
        ema_slow_period = config.get("ema_slow_period", 21)
        rsi_period = config.get("rsi_period", 14)
        rsi_mid_level = config.get("rsi_mid_level", 50)
        atr_period = config.get("atr_period", 14)
        atr_sma_period = config.get("atr_sma_period", 20)

        required_data_m5 = max(ema_slow_period, rsi_period, atr_period + atr_sma_period) + 5
        df_m5 = get_rates(symbol, "M5", required_data_m5)
        if df_m5.empty or len(df_m5) < required_data_m5:
            status["condition"] = "Data M5 tidak cukup untuk analisis sinyal."
            return status
        status['price'] = df_m5.iloc[-1]['close']

        # Hitung semua indikator M5
        df_m5.ta.ema(length=ema_fast_period, append=True)
        df_m5.ta.ema(length=ema_slow_period, append=True)
        df_m5.ta.rsi(length=rsi_period, append=True)
        df_m5.ta.atr(length=atr_period, append=True)
        df_m5[f'ATRs_{atr_sma_period}'] = ta.sma(df_m5[f'ATRr_{atr_period}'], length=atr_sma_period)

        last_bar_m5 = df_m5.iloc[-1]
        prev_bar_m5 = df_m5.iloc[-2]

        # --- Filter 1: Sinyal Entri Tren Mikro (Pemicu EMA Crossover) ---
        ema_fast_col = f'EMA_{ema_fast_period}'
        ema_slow_col = f'EMA_{ema_slow_period}'
        bullish_crossover = prev_bar_m5[ema_fast_col] <= prev_bar_m5[ema_slow_col] and \
                            last_bar_m5[ema_fast_col] > last_bar_m5[ema_slow_col]
        bearish_crossover = prev_bar_m5[ema_fast_col] >= prev_bar_m5[ema_slow_col] and \
                             last_bar_m5[ema_fast_col] < last_bar_m5[ema_slow_col]
        status["micro_trend_info"] = f"EMA({ema_fast_period})={last_bar_m5[ema_fast_col]:.5f}, EMA({ema_slow_period})={last_bar_m5[ema_slow_col]:.5f}"
        
        # --- Filter 2: Konfirmasi Momentum RSI ---
        rsi_col = f'RSI_{rsi_period}'
        momentum_ok_bullish = last_bar_m5[rsi_col] > rsi_mid_level
        momentum_ok_bearish = last_bar_m5[rsi_col] < rsi_mid_level
        status["momentum_info"] = f"RSI({rsi_period}) = {last_bar_m5[rsi_col]:.2f}"

        # --- Filter 3: Filter Volatilitas Pasar (Kondisi Aktif/Pasif) ---
        atr_val_col = f'ATRr_{atr_period}'
        atr_sma_col = f'ATRs_{atr_sma_period}'
        is_market_active = last_bar_m5[atr_val_col] > last_bar_m5[atr_sma_col]
        status["volatility_info"] = f"ATR({atr_period}) = {last_bar_m5[atr_val_col]:.5f} | Avg = {last_bar_m5[atr_sma_col]:.5f}"

        # --- 3. Pengambilan Keputusan & Sinyal Perdagangan ---
        entry_price = last_bar_m5['close']
        current_atr = last_bar_m5[atr_val_col]
        sl_multiplier = config.get("sl_atr_multiplier", 1.5)
        rrr = config.get("risk_reward_ratio", 2.0)

        # Kondisi untuk Sinyal Beli (BUY)
        if is_uptrend_macro and bullish_crossover and momentum_ok_bullish and is_market_active:
            status["condition"] = "Valid: Sinyal Bullish Terkonfirmasi"
            sl = entry_price - (current_atr * sl_multiplier)
            tp = entry_price + ((entry_price - sl) * rrr)
            status["trade_signal"] = {"signal": "BUY", "entry": entry_price, "sl": sl, "tp": tp}
        
        # Kondisi untuk Sinyal Jual (SELL)
        elif is_downtrend_macro and bearish_crossover and momentum_ok_bearish and is_market_active:
            status["condition"] = "Valid: Sinyal Bearish Terkonfirmasi"
            sl = entry_price + (current_atr * sl_multiplier)
            tp = entry_price - ((sl - entry_price) * rrr)
            status["trade_signal"] = {"signal": "SELL", "entry": entry_price, "sl": sl, "tp": tp}
        
        else:
            status["condition"] = "Menunggu Sinyal Valid (Filter Tidak Terpenuhi)"

        return status

    except Exception as e:
        status["condition"] = f"Terjadi Error: {e}"
        return status

# ==============================================================================
# Contoh Penggunaan
# ==============================================================================
if __name__ == '__main__':
    # Konfigurasi strategi sesuai Tabel 5.1 dari riset
    strategy_config = {
        "ema_macro_period": 50,      # EMA M15 untuk tren makro
        "ema_fast_period": 9,        # EMA Cepat M5 untuk sinyal
        "ema_slow_period": 21,       # EMA Lambat M5 untuk sinyal
        "rsi_period": 14,            # RSI M5 untuk momentum
        "rsi_mid_level": 50,
        "atr_period": 14,            # ATR M5 untuk volatilitas & SL
        "atr_sma_period": 20,        # SMA dari ATR M5 untuk filter volatilitas
        "sl_atr_multiplier": 1.5,    # Kelipatan ATR untuk SL awal
        "risk_reward_ratio": 2.0     # Rasio Risk/Reward untuk TP
    }

    # Jalankan analisis untuk simbol tertentu
    symbol_to_analyze = "EURUSD"
    analysis_result = check_new_strategy_v1(symbol_to_analyze, strategy_config)

    # Cetak hasil analisis dengan format yang rapi
    print("\n--- Hasil Analisis Strategi V2 ---")
    for key, value in analysis_result.items():
        if key == "trade_signal" and value:
            print(f"{key.replace('_', ' ').title()}:")
            for k, v in value.items():
                # Format harga dengan 5 angka desimal
                if isinstance(v, float):
                    print(f"  {k.title()}: {v:.5f}")
                else:
                    print(f"  {k.title()}: {v}")
        else:
            print(f"{key.replace('_', ' ').title()}: {value}")
    print("---------------------------------")