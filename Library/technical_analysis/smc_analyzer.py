# Library/technical_analysis/smc_analyzer.py

import pandas as pd

def find_swing_points(df: pd.DataFrame, lookback: int = 5):
    """
    Mendeteksi titik swing high dan swing low pada DataFrame harga.

    Args:
        df (pd.DataFrame): DataFrame yang harus memiliki kolom 'high' dan 'low'.
        lookback (int): Jumlah candle di kiri dan kanan untuk mengonfirmasi sebuah swing point.
                         Nilai yang lebih tinggi akan menghasilkan lebih sedikit swing point (lebih signifikan).

    Returns:
        dict: Sebuah dictionary berisi {'highs': [...], 'lows': [...]}.
              Setiap titik di dalam list adalah dictionary {'index': timestamp, 'price': harga}.
    """
    swing_highs = []
    swing_lows = []
    
    # Loop dari 'lookback' hingga 'panjang_df - lookback' untuk menghindari error index
    for i in range(lookback, len(df) - lookback):
        # --- Cek Swing High ---
        # Asumsikan candle saat ini adalah swing high
        is_swing_high = True
        # Periksa candle di kiri dan kanan
        for j in range(1, lookback + 1):
            if df['high'].iloc[i] < df['high'].iloc[i-j] or df['high'].iloc[i] < df['high'].iloc[i+j]:
                # Jika ada satu saja candle yang lebih tinggi, batalkan asumsi
                is_swing_high = False
                break
        
        if is_swing_high:
            # Jika asumsi benar, catat sebagai swing high
            swing_point = {'index': df.index[i], 'price': df['high'].iloc[i]}
            swing_highs.append(swing_point)

        # --- Cek Swing Low (logika serupa) ---
        is_swing_low = True
        for j in range(1, lookback + 1):
            if df['low'].iloc[i] > df['low'].iloc[i-j] or df['low'].iloc[i] > df['low'].iloc[i+j]:
                is_swing_low = False
                break

        if is_swing_low:
            swing_point = {'index': df.index[i], 'price': df['low'].iloc[i]}
            swing_lows.append(swing_point)
            
    return {'highs': swing_highs, 'lows': swing_lows}

def detect_liquidity_sweep(df: pd.DataFrame, last_swing_low: dict, lookback: int = 3):
    """
    Mendeteksi jika terjadi liquidity sweep di bawah swing low terakhir.

    Args:
        df (pd.DataFrame): DataFrame harga.
        last_swing_low (dict): Titik swing low terakhir dari find_swing_points().
                               Format: {'index': ..., 'price': ...}
        lookback (int): Berapa banyak candle ke belakang yang perlu diperiksa untuk sweep.

    Returns:
        bool: True jika liquidity sweep terdeteksi, False jika tidak.
    """
    if not last_swing_low:
        return False
        
    # Ambil beberapa candle terakhir untuk dianalisis
    recent_candles = df.tail(lookback)
    
    # Dapatkan harga swing low yang akan diuji
    swing_low_price = last_swing_low['price']
    
    # Cek apakah ada candle dalam periode lookback yang 'low'-nya menembus swing low
    wick_below_swing_low = (recent_candles['low'] < swing_low_price).any()
    
    # Cek apakah candle terakhir ditutup KEMBALI di atas swing low
    last_candle_closed_above = recent_candles.iloc[-1]['close'] > swing_low_price
    
    # Kondisi sweep terpenuhi jika ada wick di bawah DAN candle terakhir ditutup di atas
    if wick_below_swing_low and last_candle_closed_above:
        return True
        
    return False

def detect_choch(df: pd.DataFrame, last_lower_high: dict, sweep_low_index):
    """
    Mendeteksi jika terjadi Change of Character (CHOCH) setelah liquidity sweep.

    Args:
        df (pd.DataFrame): DataFrame harga.
        last_lower_high (dict): Titik swing high terakhir yang relevan sebelum sweep.
                                Format: {'index': ..., 'price': ...}
        sweep_low_index: Index (waktu) dari candle terendah saat sweep terjadi.
                         Ini untuk memastikan CHOCH terjadi SETELAH sweep.

    Returns:
        bool: True jika CHOCH terdeteksi, False jika tidak.
    """
    if not last_lower_high:
        return False
        
    choch_price_level = last_lower_high['price']
    
    # Ambil semua candle yang terjadi SETELAH sweep low
    candles_after_sweep = df[df.index > sweep_low_index]
    
    if candles_after_sweep.empty:
        return False
        
    # Cek apakah ada candle setelah sweep yang 'high'-nya berhasil menembus level CHOCH
    price_broke_structure = (candles_after_sweep['high'] > choch_price_level).any()
    
    return price_broke_structure

def find_fvg(df: pd.DataFrame, from_index):
    """
    Mencari Fair Value Gap (FVG) bullish atau bearish setelah titik tertentu.

    Args:
        df (pd.DataFrame): DataFrame harga.
        from_index: Index (waktu) untuk memulai pencarian FVG.

    Returns:
        dict: Dictionary berisi detail FVG jika ditemukan, atau None.
              Format: {'type': 'bullish'/'bearish', 'high': ..., 'low': ..., 'level_50': ...}
    """
    candles_to_check = df[df.index > from_index]
    
    # Perlu setidaknya 3 candle untuk mendeteksi FVG
    if len(candles_to_check) < 3:
        return None

    # Loop melalui candle setelah CHOCH untuk menemukan FVG pertama
    for i in range(len(candles_to_check) - 2):
        candle1 = candles_to_check.iloc[i]
        candle2 = candles_to_check.iloc[i+1]
        candle3 = candles_to_check.iloc[i+2]

        # Cek FVG Bullish (celah antara high candle 1 dan low candle 3)
        if candle1['high'] < candle3['low']:
            fvg_high = candle3['low']
            fvg_low = candle1['high']
            return {
                'type': 'bullish',
                'high': fvg_high,
                'low': fvg_low,
                'level_50': (fvg_high + fvg_low) / 2
            }
            
        # Cek FVG Bearish (celah antara low candle 1 dan high candle 3)
        elif candle1['low'] > candle3['high']:
            fvg_high = candle1['low']
            fvg_low = candle3['high']
            return {
                'type': 'bearish',
                'high': fvg_high,
                'low': fvg_low,
                'level_50': (fvg_high + fvg_low) / 2
            }
            
    return None

def find_order_block(df: pd.DataFrame, from_index):
    """
    Mencari Order Block (OB) bullish atau bearish setelah titik tertentu.

    Args:
        df (pd.DataFrame): DataFrame harga.
        from_index: Index (waktu) untuk memulai pencarian OB.

    Returns:
        dict: Dictionary berisi detail OB jika ditemukan, atau None.
              Format: {'type': 'bullish'/'bearish', 'high': ..., 'low': ...}
    """
    candles_to_check = df[df.index > from_index]
    
    if len(candles_to_check) < 2:
        return None

    # Loop melalui candle setelah CHOCH untuk menemukan OB
    # Kita cari candle terakhir dengan arah berlawanan sebelum pergerakan besar
    for i in range(1, len(candles_to_check)):
        prev_candle = candles_to_check.iloc[i-1]
        current_candle = candles_to_check.iloc[i]

        # Cek OB Bullish (candle bearish terakhir sebelum candle bullish besar)
        if prev_candle['close'] < prev_candle['open'] and current_candle['close'] > current_candle['open']:
             # Periksa apakah candle saat ini adalah pergerakan impulsif (misal: bodynya besar)
            if abs(current_candle['close'] - current_candle['open']) > (current_candle['high'] - current_candle['low']) * 0.6:
                return {
                    'type': 'bullish',
                    'high': prev_candle['high'],
                    'low': prev_candle['low']
                }

        # Cek OB Bearish (candle bullish terakhir sebelum candle bearish besar)
        elif prev_candle['close'] > prev_candle['open'] and current_candle['close'] < current_candle['open']:
            if abs(current_candle['close'] - current_candle['open']) > (current_candle['high'] - current_candle['low']) * 0.6:
                return {
                    'type': 'bearish',
                    'high': prev_candle['high'],
                    'low': prev_candle['low']
                }

    return None